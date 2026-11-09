"""Exercise the dashboard's HTTP workflow route against a running local server."""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def request(url, token, body=None, method='POST'):
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers = {'Authorization': f'Bearer {token}'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers,
                                                        method=method), timeout=90) as response:
        return response.status, json.loads(response.read())


def template(templates, exercise):
    pattern = rf"(?ms)^  (?:'{re.escape(exercise)}'|{re.escape(exercise)}): \{{.*?^    source: `(.*?)`,\s+payload: `(.*?)`,"
    match = re.search(pattern, templates)
    if match is None:
        raise ValueError(f'UI template unavailable: {exercise}')
    source, payload = match.groups()
    return source, json.loads(payload)


def burst(base, tokens, source, payload, count):
    def run(index):
        tenant = 'tenant-a' if index % 2 == 0 else 'tenant-b'
        token = tokens[tenant]
        started = time.monotonic()
        queued = False
        try:
            _, created = request(base + '/v1/sessions', token,
                                 {'exercise': 'orders-cents'})
            session = created['session']
            endpoint = base + f'/v1/sessions/{session}/python'
            for _ in range(180):
                try:
                    status, result = request(endpoint, token,
                                             {'source': source, 'payload': payload})
                    checks = result.get('grade', {}).get('deterministic_results', [])
                    return {'index': index, 'tenant': tenant, 'session': session,
                            'queued': queued, 'latency_seconds': round(time.monotonic() - started, 2),
                            'pass': (status == 200 and result.get('execution', {}).get('status') == 'ok'
                                     and result.get('execution', {}).get('backend') == 'firecracker'
                                     and bool(checks) and all(check.get('passed') for check in checks)),
                            'grade': result.get('grade', {}).get('status')}
                except urllib.error.HTTPError as exc:
                    detail = json.loads(exc.read()).get('error', '')
                    if exc.code != 409 or 'queued for execution' not in detail:
                        raise
                    queued = True
                    time.sleep(1)
            raise TimeoutError('session did not leave the admission queue')
        except (OSError, ValueError, TimeoutError) as exc:
            return {'index': index, 'tenant': tenant, 'queued': queued,
                    'latency_seconds': round(time.monotonic() - started, 2),
                    'pass': False, 'error': f'{type(exc).__name__}: {exc}'}

    with ThreadPoolExecutor(max_workers=count) as pool:
        entries = sorted(pool.map(run, range(count)), key=lambda item: item['index'])
    return {'scope': f'{count} simultaneous API requests across two tenants; '
            'server worker capacity remains configured separately',
            'all_pass': len(entries) == count and all(entry['pass'] for entry in entries),
            'queued_count': sum(entry['queued'] for entry in entries),
            'results': entries}


def main(args):
    root = Path(__file__).resolve().parents[1]
    tokens = json.loads(Path(args.credentials).read_text(encoding='utf-8'))
    base = args.base_url.rstrip('/')
    templates = (root / 'web/src/App.jsx').read_text(encoding='utf-8')
    if args.burst:
        source, payload = template(templates, 'orders-cents')
        report = burst(base, tokens, source, payload, args.burst)
        Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        return 0 if report['all_pass'] else 1
    exercises = ('orders-cents', 'inventory', 'daily-revenue', 'stock-reorder',
                 'inventory-brief', 'order-explainer')
    selected = exercises if args.exercise == 'all' else (args.exercise,)
    results = {}
    try:
        for exercise in selected:
            source, payload = template(templates, exercise)
            endpoint = 'agent' if exercise in ('inventory', 'stock-reorder',
                                               'inventory-brief', 'order-explainer') else 'python'
            _, created = request(base + '/v1/sessions', tokens['tenant-a'],
                                 {'exercise': exercise})
            started = time.monotonic()
            status, result = request(base + f"/v1/sessions/{created['session']}/{endpoint}",
                                     tokens['tenant-a'], {
                                         'source': source,
                                         'payload': payload,
                                     })
            checks = result.get('grade', {}).get('deterministic_results', [])
            entry = {
                'http_status': status,
                'session': created['session'],
                'execution_status': result.get('execution', {}).get('status'),
                'backend': result.get('execution', {}).get('backend'),
                'snapshot_restored': bool(result.get('execution', {}).get('snapshot', {}).get('restored')),
                'grade': result.get('grade', {}).get('status'),
                'deterministic_checks_passed': bool(checks) and all(
                    check.get('passed') for check in checks),
                'latency_seconds': round(time.monotonic() - started, 2),
                'output': result.get('output'),
            }
            entry['pass'] = (status == 200 and entry['execution_status'] == 'ok'
                             and entry['backend'] == 'firecracker'
                             and entry['deterministic_checks_passed']
                             and (endpoint == 'python' or entry['snapshot_restored']))
            results[exercise] = entry
        report = {'all_pass': all(entry['pass'] for entry in results.values()),
                  'results': results}
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        report = {'all_pass': False, 'results': results,
                  'error': f'{type(exc).__name__}: {exc}'}
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--credentials', default='config/tenants.local.json')
    parser.add_argument('--exercise', default='inventory', choices=['all', 'orders-cents',
        'inventory', 'daily-revenue', 'stock-reorder', 'inventory-brief', 'order-explainer'])
    parser.add_argument('--burst', type=int, choices=range(1, 11),
                        help='run up to ten simultaneous order submissions across two tenants')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

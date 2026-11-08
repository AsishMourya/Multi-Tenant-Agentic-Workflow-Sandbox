"""Exercise the dashboard's HTTP workflow route against a running local server."""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def request(url, token, body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers = {'Authorization': f'Bearer {token}'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers,
                                                        method='POST'), timeout=90) as response:
        return response.status, json.loads(response.read())


def main(args):
    root = Path(__file__).resolve().parents[1]
    tokens = json.loads(Path(args.credentials).read_text(encoding='utf-8'))
    source = (root / args.source).read_text(encoding='utf-8')
    base = args.base_url.rstrip('/')
    try:
        _, created = request(base + '/v1/sessions', tokens['tenant-a'],
                             {'exercise': 'inventory'})
        status, result = request(base + f"/v1/sessions/{created['session']}/agent",
                                 tokens['tenant-a'], {
                                     'source': source,
                                     'payload': {'sku': 'apple', 'quantity': 2},
                                 })
        report = {
            'http_status': status,
            'session': created['session'],
            'execution_status': result.get('execution', {}).get('status'),
            'backend': result.get('execution', {}).get('backend'),
            'snapshot_restored': bool(result.get('execution', {}).get('snapshot', {}).get('restored')),
            'output': result.get('output'),
        }
        report['all_pass'] = (status == 200 and report['execution_status'] == 'ok'
                              and report['backend'] == 'firecracker'
                              and report['snapshot_restored'])
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        report = {'all_pass': False, 'error': f'{type(exc).__name__}: {exc}'}
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--credentials', default='config/tenants.local.json')
    parser.add_argument('--source', default='examples/inventory_langgraph_submission.py')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

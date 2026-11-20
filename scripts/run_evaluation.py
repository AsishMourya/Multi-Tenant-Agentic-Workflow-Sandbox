"""Execute a frozen submission bank through the isolated authenticated API.

Does not execute source on the host, assign human labels, or estimate accuracy.
Append-only output supports resuming interrupted runs without overwriting evidence.
"""
import argparse
import json
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.exercise_registry import EXERCISES, PYTHON_EXERCISES, validate_input
from scripts.build_regression_bank import bank_digest
from scripts.live_api_workflow_probe import request


def validate_bank(bank, split):
    if split.get('bank_sha256') != bank_digest(bank):
        raise ValueError('bank content does not match the frozen split digest')
    rows = bank.get('submissions', [])
    assignments = split.get('assignments', [])
    by_id = {row['id']: row for row in assignments}
    if len(by_id) != len(assignments) or len(rows) != len(by_id):
        raise ValueError('bank and split IDs must match exactly')
    seen = set()
    families = {}
    sources = {}
    for row in rows:
        sid = row['id']
        if sid in seen or sid not in by_id:
            raise ValueError('duplicate or missing submission ID')
        seen.add(sid)
        assignment = by_id[sid]
        if any(row[key] != assignment[key] for key in ('family', 'exercise_id')):
            raise ValueError('assignment changed')
        if row['exercise_id'] not in EXERCISES:
            raise ValueError('unknown exercise')
        if not isinstance(row['source'], str) or not 1 <= len(row['source'].encode()) <= 32768:
            raise ValueError('invalid source')
        validate_input(row['exercise_id'], row['payload'])
        partition = assignment['split']
        if partition not in {'calibration', 'held_out'}:
            raise ValueError('invalid split')
        for groups, key in ((families, row['family']), (sources, row['source'])):
            if key in groups and groups[key] != partition:
                raise ValueError('family or identical source leaks across split')
            groups[key] = partition
    return by_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', required=True)
    parser.add_argument('--split', required=True)
    parser.add_argument('--partition', choices=['calibration', 'held_out', 'all'], default='calibration')
    parser.add_argument('--credentials', default='config/tenants.local.json')
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--output', required=True)
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()
    bank = json.loads(Path(args.bank).read_text(encoding='utf-8'))
    split = json.loads(Path(args.split).read_text(encoding='utf-8'))
    assignments = validate_bank(bank, split)
    token = json.loads(Path(args.credentials).read_text(encoding='utf-8'))['tenant-a']
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    failures = 0
    if destination.exists():
        for line in destination.read_text(encoding='utf-8').splitlines():
            recorded = json.loads(line)
            if recorded['bank_sha256'] != split['bank_sha256']:
                raise ValueError('existing output belongs to a different bank')
            completed.add((recorded['id'], recorded['repeat']))
            failures += bool(recorded.get('infrastructure_error'))
    base = args.base_url.rstrip('/')
    for row in bank['submissions']:
        assignment = assignments[row['id']]
        if args.partition != 'all' and assignment['split'] != args.partition:
            continue
        for repeat in range(1, args.repeats + 1):
            if (row['id'], repeat) in completed:
                continue
            started = time.monotonic()
            record = {'id': row['id'], 'repeat': repeat, 'split': assignment['split'],
                      'bank_sha256': split['bank_sha256'],
                      'at_utc': datetime.now(timezone.utc).isoformat()}
            try:
                _, created = request(base + '/v1/sessions', token, {'exercise': row['exercise_id']})
                sid = created['session']
                record['session'] = sid
                mode = 'python' if row['exercise_id'] in PYTHON_EXERCISES else 'agent'
                for attempt in range(90):
                    try:
                        _, result = request(f'{base}/v1/sessions/{sid}/{mode}', token,
                                            {'source': row['source'], 'payload': row['payload']})
                        record['result'] = result
                        break
                    except urllib.error.HTTPError as exc:
                        detail = json.loads(exc.read()).get('error', '')
                        if exc.code != 409 or 'queued for execution' not in detail:
                            raise RuntimeError(f'HTTP {exc.code}: {detail}') from exc
                        time.sleep(1)
                else:
                    request(f'{base}/v1/sessions/{sid}/cancel', token, {})
                    raise TimeoutError('admission wait exhausted')
            except (OSError, ValueError, RuntimeError) as exc:
                record['infrastructure_error'] = str(exc)
            record['end_to_end_latency_ms'] = round((time.monotonic() - started) * 1000, 2)
            with destination.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record) + '\n')
                stream.flush()
            status = record.get('result', {}).get('grade', {}).get('status', 'RETRY_ERROR')
            failures += bool(record.get('infrastructure_error'))
            print(json.dumps({'id': row['id'], 'repeat': repeat, 'status': status}), flush=True)
    print(json.dumps({'infrastructure_errors': failures, 'output': str(destination)}), flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())

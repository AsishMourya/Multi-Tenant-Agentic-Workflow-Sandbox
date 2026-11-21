"""Repeat live two-tenant API bursts; report latency and throughput by offered load."""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.live_api_workflow_probe import burst, template


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def benchmark(base, tokens, source, payload, *, repeats, capacities):
    trials = []
    for capacity in capacities:
        for repeat in range(1, repeats + 1):
            started = time.monotonic()
            result = burst(base, tokens, source, payload, capacity)
            elapsed = time.monotonic() - started
            trials.append({'concurrency': capacity, 'repeat': repeat,
                           'wall_seconds': round(max(elapsed, .001), 3), **result})
    summary = {}
    for capacity in capacities:
        group = [trial for trial in trials if trial['concurrency'] == capacity]
        latencies = [entry['latency_seconds'] for trial in group for entry in trial['results']]
        summary[str(capacity)] = {'requests': len(latencies),
                                  'successful': sum(entry['pass'] for trial in group for entry in trial['results']),
                                  'queued': sum(trial['queued_count'] for trial in group),
                                  'median_latency_seconds': round(statistics.median(latencies), 3),
                                  'p95_latency_seconds': percentile(latencies, .95),
                                  'throughput_requests_per_second': round(
                                      sum(len(trial['results']) for trial in group) /
                                      sum(trial['wall_seconds'] for trial in group), 3)}
    return {'scope': 'Live orders-cents Firecracker API bursts, two alternating tenants; '
                     'offered request concurrency, not proof of simultaneous VM count.',
            'repeats': repeats, 'summary': summary, 'trials': trials,
            'all_pass': all(trial['all_pass'] for trial in trials)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--credentials', default='config/tenants.local.json')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error('--repeats must be 1-10')
    output = Path(args.output)
    if output.exists():
        parser.error('output already exists; refusing to overwrite')
    root = Path(__file__).resolve().parents[1]
    tokens = json.loads(Path(args.credentials).read_text(encoding='utf-8'))
    source, payload = template((root / 'web/src/App.jsx').read_text(encoding='utf-8'), 'orders-cents')
    report = benchmark(args.base_url.rstrip('/'), tokens, source, payload,
                       repeats=args.repeats, capacities=(1, 2, 4))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'all_pass': report['all_pass'], 'summary': report['summary'],
                      'output': str(output)}, indent=2))
    return 0 if report['all_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

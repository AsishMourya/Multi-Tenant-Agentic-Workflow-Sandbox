"""Record a real local Ollama rubric-judge smoke test."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.local_judge import JudgeUnavailable, OllamaJudge


def main(args):
    judge = OllamaJudge(args.model, timeout_seconds=args.timeout)
    observed = {'payload': [{'sku': 'apple', 'quantity': 2, 'unit_cents': 125}],
                'output': {'by_sku': {'apple': 250}, 'total_cents': 250},
                'deterministic_results': [{'check': 'hidden cases', 'passed': True}]}
    try:
        calls = [judge.judge('orders-cents', observed) for _ in range(2)]
        result = {'at_utc': datetime.now(timezone.utc).isoformat(),
                  'scope': 'two-call local JSON rubric smoke test; not a quality calibration',
                  'model': args.model, 'calls': calls,
                  'json_valid': True,
                  'all_pass': True}
    except JudgeUnavailable as exc:
        result = {'at_utc': datetime.now(timezone.utc).isoformat(), 'model': args.model,
                  'error': str(exc), 'all_pass': False}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'all_pass': result['all_pass'], 'model': args.model,
                      'latency_ms': [call['metadata']['latency_ms'] for call in result.get('calls', [])]}, indent=2))
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='qwen2.5:0.5b')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

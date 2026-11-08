import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sandbox.firecracker_backend import FirecrackerBackend


def broker_call(request):
    if request != {
        'operation': 'inventory.lookup',
        'args': {'sku': 'apple'},
        'request': 'lookup-1',
    }:
        raise PermissionError('unexpected scoped tool request')
    return {'sku': 'apple', 'available': 7}


def main(args):
    source = Path(args.source).read_text(encoding='utf-8')
    backend = FirecrackerBackend(args.backend_root)
    result = backend.run_workflow('workflow-probe', 'workflow-probe-1', source,
                                  {'sku': 'apple', 'quantity': 2}, broker_call)
    expected = {
        'sku': 'apple', 'quantity': 2, 'available': 7, 'accepted': True,
        'explanation': 'Requested 2; available 7; accepted True.',
    }
    output = json.loads(result['stdout']) if result['status'] == 'ok' else None
    report = {
        'execution': result,
        'output_matches_expected': output == expected,
        'full_vm_snapshot': bool(result.get('snapshot', {}).get('restored')),
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['output_matches_expected'] and report['full_vm_snapshot'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend-root', default='/root/dat-backend')
    parser.add_argument('--source', default='examples/inventory_langgraph_submission.py')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

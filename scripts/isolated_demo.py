"""Two-tenant Firecracker submission and workflow restore demonstration.

Run under Linux root with working KVM and the prepared pinned guest image.
Judgments are fixtures for integration only, not evidence of a real local judge.
"""
import argparse
import json
import secrets
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.firecracker_backend import FirecrackerBackend
from sandbox.platform import Platform
from sandbox.tenant_gateway import TenantGateway


def judge():
    return {'criteria': {name: {'level': 4, 'status': 'APPLICABLE',
                                'evidence': 'integration fixture', 'reason': 'bounded demo'}
                         for name in ('correctness', 'clarity')},
            'conflicts_with_tests': False, 'confidence': .9}


def exercise(root, backend, tenant, bearer, credentials, name, source, payload):
    started = time.monotonic()
    platform = Platform(root, backend=backend)
    gateway = TenantGateway(platform, credentials)
    try:
        session = gateway.create(bearer, name)
        if name == 'orders-cents':
            result = gateway.submit_python(bearer, session, source, payload,
                                           [judge(), judge()], pause_resume=True)
        else:
            result = gateway.submit_workflow(bearer, session, source, payload,
                                             [judge(), judge()])
        foreign_denied = False
        try:
            other = 'tenant-b' if tenant == 'tenant-a' else 'tenant-a'
            gateway.status(credentials[other], session)
        except PermissionError:
            foreign_denied = True
        return {'tenant': tenant, 'session': session, 'exercise': name,
                'start_monotonic': started, 'end_monotonic': time.monotonic(),
                'foreign_denied': foreign_denied, 'result': result,
                'lifecycle': gateway.status(bearer, session)}
    finally:
        platform.close()


def main(args):
    repo = Path(__file__).resolve().parents[1]
    backend = FirecrackerBackend(args.root)
    backend._preflight()
    before = set(backend.root.glob('submission-*'))
    credentials = {tenant: secrets.token_urlsafe(32)
                   for tenant in ('tenant-a', 'tenant-b')}
    orders_source = (repo / 'examples/orders_checkpoint_submission.py').read_text(encoding='utf-8')
    workflow_source = (repo / 'examples/inventory_langgraph_submission.py').read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='platform-demo-', dir=backend.root) as directory:
        root = Path(directory)
        with ThreadPoolExecutor(max_workers=2) as pool:
            orders_future = pool.submit(exercise, root / 'tenant-a', backend, 'tenant-a',
                                        credentials['tenant-a'], credentials,
                                        'orders-cents', orders_source,
                                        [{'sku': 'apple', 'quantity': 2, 'unit_cents': 125}])
            workflow_future = pool.submit(exercise, root / 'tenant-b', backend, 'tenant-b',
                                          credentials['tenant-b'], credentials,
                                          'inventory', workflow_source,
                                          {'sku': 'apple', 'quantity': 2})
            try:
                orders = orders_future.result()
            except Exception as exc:
                orders = {'error': f'{type(exc).__name__}: {exc}'}
            try:
                workflow = workflow_future.result()
            except Exception as exc:
                workflow = {'error': f'{type(exc).__name__}: {exc}'}
    after = set(backend.root.glob('submission-*'))
    succeeded = 'result' in orders and 'result' in workflow
    overlap = succeeded and max(orders['start_monotonic'], workflow['start_monotonic']) < min(
        orders['end_monotonic'], workflow['end_monotonic'])
    checks = {
        'orders_output': succeeded and orders['result']['output'] is not None
        and orders['result']['output'].get('total_cents') == 250,
        'python_snapshot_restored': succeeded and orders['result']['execution'].get('snapshot', {}).get('restored') is True,
        'workflow_output': succeeded and workflow['result']['output'] is not None
        and workflow['result']['output'].get('accepted') is True,
        'workflow_snapshot_restored': succeeded and workflow['result']['execution'].get('snapshot', {}).get('restored') is True,
        'foreign_access_denied': succeeded and orders['foreign_denied'] and workflow['foreign_denied'],
        'both_guest_runs_ok': succeeded and all(item['result']['execution']['status'] == 'ok'
                                                 for item in (orders, workflow)),
        'runtime_directories_cleaned': before == after,
        'runs_overlapped': overlap,
    }
    result = {'at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'live two-tenant Firecracker integration; mock judge fixtures only',
              'checks': checks, 'all_pass': all(checks.values()),
              'orders': orders, 'workflow': workflow}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'checks': checks, 'all_pass': result['all_pass'],
                      'output': str(output)}, indent=2))
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

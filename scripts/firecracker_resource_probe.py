"""Live guest resource and direct-network denial checks."""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.firecracker_backend import FirecrackerBackend


CASES = {
    'control': 'import json\nprint(json.dumps({"value": 42}))\n',
    'memory': 'x = bytearray(512 * 1024 * 1024)\nprint(len(x))\n',
    'output': 'print("x" * 200000)\n',
    'wall': 'import time\ntime.sleep(60)\n',
    'processes': (
        'import json, subprocess, time\n'
        'children=[]\nblocked=False\n'
        'try:\n'
        '    for _ in range(50):\n'
        '        children.append(subprocess.Popen(["sleep", "5"]))\n'
        'except OSError:\n'
        '    blocked=True\n'
        'finally:\n'
        '    for child in children: child.terminate()\n'
        '    for child in children: child.wait()\n'
        'print(json.dumps({"blocked": blocked, "started": len(children)}))\n'
    ),
    'file_size': (
        'import json\nblocked=False\n'
        'try:\n'
        '    with open("/tmp/flood.bin", "wb") as f: f.write(b"x" * 200000)\n'
        'except OSError:\n'
        '    blocked=True\n'
        'print(json.dumps({"blocked": blocked}))\n'
    ),
    'ipv4': (
        'import json, socket\nblocked=False\n'
        'try:\n'
        '    socket.create_connection(("1.1.1.1", 80), timeout=2)\n'
        'except OSError:\n'
        '    blocked=True\n'
        'print(json.dumps({"blocked": blocked}))\n'
    ),
    'ipv6': (
        'import json, socket\nblocked=False\n'
        'try:\n'
        '    s=socket.socket(socket.AF_INET6)\n'
        '    s.settimeout(2)\n'
        '    s.connect(("2606:4700:4700::1111", 80))\n'
        'except OSError:\n'
        '    blocked=True\n'
        'print(json.dumps({"blocked": blocked}))\n'
    ),
    'dns': (
        'import json, socket\nblocked=False\n'
        'try:\n'
        '    socket.getaddrinfo("example.com", 80)\n'
        'except OSError:\n'
        '    blocked=True\n'
        'print(json.dumps({"blocked": blocked}))\n'
    ),
}


def _timed_run(backend, tenant, session, source):
    started = time.monotonic()
    try:
        result = backend.run_python(tenant, session, source, {})
    except Exception as exc:
        result = {'status': 'infrastructure_error',
                  'error': f'{type(exc).__name__}: {exc}',
                  'stdout': '', 'stderr': ''}
    return {'start_monotonic': started, 'end_monotonic': time.monotonic(),
            'result': result}


def cpu_limited_backend(backend):
    attack_policy = dict(backend.policy)
    if attack_policy['wall_seconds'] <= 1:
        raise ValueError('concurrent CPU probe requires wall_seconds greater than one')
    attack_policy['cpu_seconds'] = min(2, attack_policy['wall_seconds'] - 1)
    return FirecrackerBackend(
        backend.root, policy=attack_policy, image=backend.base_disk.name)


def concurrent_benign_probe(backend, attack_backend):
    """Run a bounded CPU stressor beside a low-cost task in another tenant."""
    cpu_loop = 'while True: pass\n'
    benign = ('import json, time\n'
              'time.sleep(2)\n'
              'print(json.dumps({"value": 42}))\n')
    with ThreadPoolExecutor(max_workers=2) as pool:
        attack_future = pool.submit(_timed_run, attack_backend, 'tenant-a',
                                    'resource-concurrent-cpu', cpu_loop)
        benign_future = pool.submit(_timed_run, backend, 'tenant-b',
                                    'resource-concurrent-control', benign)
        attack = attack_future.result()
        control = benign_future.result()
    overlap = max(attack['start_monotonic'], control['start_monotonic']) < min(
        attack['end_monotonic'], control['end_monotonic'])
    try:
        control_output = json.loads(control['result']['stdout'])
    except (KeyError, TypeError, ValueError):
        control_output = None
    checks = {
        'cpu_limit_enforced': (attack['result']['status'] == 'error'
                               and attack['result'].get('exit_code') in {-24, -9}),
        'attack_bounded': attack['result']['status'] in {'error', 'timeout'},
        'benign_control_ok': control['result']['status'] == 'ok'
        and control_output == {'value': 42},
        'runs_overlapped': overlap,
    }
    return {'attack': attack, 'benign_control': control,
            'overlapped': overlap, 'checks': checks,
            'all_pass': all(checks.values())}


def main(args):
    backend = FirecrackerBackend(args.root)
    observations = {}
    for name, source in CASES.items():
        try:
            observations[name] = backend.run_python('tenant-a', 'resource-' + name,
                                                    source, {})
        except Exception as exc:
            observations[name] = {'status': 'infrastructure_error',
                                  'error': f'{type(exc).__name__}: {exc}',
                                  'stdout': '', 'stderr': ''}
    concurrent = concurrent_benign_probe(backend, cpu_limited_backend(backend))
    observations['concurrent_cpu_attack'] = concurrent['attack']['result']
    observations['concurrent_benign_control'] = concurrent['benign_control']['result']
    parsed = {}
    for name in ('control', 'processes', 'file_size', 'ipv4', 'ipv6', 'dns'):
        try:
            parsed[name] = json.loads(observations[name]['stdout'])
        except ValueError:
            parsed[name] = None
    checks = {
        'control': observations['control']['status'] == 'ok' and parsed['control'] == {'value': 42},
        'cpu_limit': concurrent['checks']['cpu_limit_enforced'],
        'concurrent_benign_control': concurrent['all_pass'],
        'memory_limit': 'MemoryError' in observations['memory']['stderr'],
        'output_limit': observations['output']['status'] == 'output_limit',
        'wall_limit': observations['wall']['status'] == 'timeout',
        'process_limit': bool(parsed['processes'] and parsed['processes']['blocked']),
        'file_limit': bool(parsed['file_size'] and parsed['file_size']['blocked']),
        'ipv4_denied': bool(parsed['ipv4'] and parsed['ipv4']['blocked']),
        'ipv6_denied': bool(parsed['ipv6'] and parsed['ipv6']['blocked']),
        'dns_denied': bool(parsed['dns'] and parsed['dns']['blocked']),
    }
    result = {'at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'live Firecracker resource stress with concurrent cross-tenant benign control',
              'checks': checks, 'observations': observations,
              'concurrent_probe': concurrent,
              'all_pass': all(checks.values())}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'checks': checks, 'all_pass': result['all_pass'],
                      'output': str(path)}, indent=2))
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

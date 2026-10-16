"""Live guest resource and direct-network denial checks."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.firecracker_backend import FirecrackerBackend


CASES = {
    'control': 'import json\nprint(json.dumps({"value": 42}))\n',
    'cpu_loop': 'while True: pass\n',
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
    parsed = {}
    for name in ('control', 'processes', 'file_size', 'ipv4', 'ipv6', 'dns'):
        try:
            parsed[name] = json.loads(observations[name]['stdout'])
        except ValueError:
            parsed[name] = None
    checks = {
        'control': observations['control']['status'] == 'ok' and parsed['control'] == {'value': 42},
        'cpu_limit': observations['cpu_loop']['status'] in {'error', 'timeout'},
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
              'scope': 'live Firecracker single-session stress; no concurrent benign control',
              'checks': checks, 'observations': observations,
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

"""Bounded live guest security probes against the Firecracker backend.

These are evidence for this defined corpus only. They do not claim universal
sandbox security or attempt any external network access.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.firecracker_backend import FirecrackerBackend


CASES = {
    'protected_runtime_files': '''import json
paths = ['/root/dat_input.json', '/root/dat_config.json', '/root/dat_runner.py']
blocked = []
for path in paths:
    try:
        open(path).read()
    except OSError:
        blocked.append(path)
print(json.dumps({'blocked': blocked}))
''',
    'host_mount_absent': '''import json, os
print(json.dumps({'host_mount_present': os.path.exists('/mnt/c')}))
''',
    'direct_broker_bypass': '''import json, socket
try:
    socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).connect('/tmp/dat-broker.sock')
    blocked = False
except OSError:
    blocked = True
print(json.dumps({'blocked': blocked}))
''',
    'environment_canary_absent': '''import json, os
canary = 'DUMMY_UPSTREAM_CANARY_NOT_A_REAL_SECRET'
print(json.dumps({'canary_present': any(canary in value for value in os.environ.values())}))
''',
}


def main(args):
    backend = FirecrackerBackend(args.root)
    observed = {name: backend.run_python('security-tenant', 'security-' + name, source, {})
                for name, source in CASES.items()}
    parsed = {name: json.loads(result['stdout']) if result['status'] == 'ok' else None
              for name, result in observed.items()}
    checks = {
        'protected_runtime_files': parsed['protected_runtime_files'] and
            len(parsed['protected_runtime_files']['blocked']) == 3,
        'host_mount_absent': parsed['host_mount_absent'] == {'host_mount_present': False},
        'direct_broker_bypass': parsed['direct_broker_bypass'] == {'blocked': True},
        'environment_canary_absent': parsed['environment_canary_absent'] == {'canary_present': False},
    }
    result = {'at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'defined live guest filesystem/environment/broker corpus only',
              'checks': checks, 'observations': observed, 'all_pass': all(checks.values())}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'checks': checks, 'all_pass': result['all_pass'], 'output': str(output)}, indent=2))
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

"""Read-only Linux/KVM preflight. Does not claim a VM boot or limit enforcement."""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def kvm_probe():
    device = Path('/dev/kvm')
    result = {'present': device.exists(), 'read_write_access': os.access(device, os.R_OK | os.W_OK)}
    if not result['read_write_access']:
        result['api_version'] = None
        return result
    try:
        import fcntl
        with device.open('rb+', buffering=0) as handle:
            result['api_version'] = fcntl.ioctl(handle.fileno(), 0xAE00, 0)
    except OSError as exc:
        result['api_version'] = None
        result['error'] = f'{type(exc).__name__}: {exc.strerror}'
    return result


def memory_kib():
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemTotal:'):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def main(output):
    started = time.monotonic()
    child = subprocess.run([sys.executable, '-c', 'print(6 * 7)'],
                           capture_output=True, text=True, timeout=10)
    result = {
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'host preflight only; no guest boot, resource enforcement, or snapshot restore',
        'host': {'system': platform.system(), 'release': platform.release(),
                 'machine': platform.machine(), 'cpu_count': os.cpu_count(),
                 'memory_total_kib': memory_kib()},
        'python': {'version': platform.python_version(), 'path': sys.executable,
                   'child_exit_code': child.returncode, 'child_stdout': child.stdout.strip(),
                   'child_stderr': child.stderr.strip()},
        'kvm': kvm_probe() if platform.system() == 'Linux' else {'status': 'Linux only'},
        'tools': {name: shutil.which(name) for name in ('firecracker', 'jailer', 'docker')},
        'cgroup_v2': Path('/sys/fs/cgroup/cgroup.controllers').is_file(),
        'elapsed_seconds': round(time.monotonic() - started, 3),
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if child.returncode == 0 and child.stdout.strip() == '42' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.output))

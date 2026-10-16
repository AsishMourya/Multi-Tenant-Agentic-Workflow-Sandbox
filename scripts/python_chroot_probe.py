"""Offline Python safe-point protocol check; chroot is not a sandbox test."""
import argparse
import base64
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.guest_chroot_probe import LineReader
from sandbox.firecracker_backend import FirecrackerBackend


def main(args):
    backend = FirecrackerBackend(args.root)
    source = (Path(__file__).resolve().parents[1] /
              'examples/orders_checkpoint_submission.py').read_text(encoding='utf-8')
    nonce = 'offline-python-checkpoint'
    with tempfile.TemporaryDirectory(prefix='python-chroot-', dir=backend.root) as directory:
        run = Path(directory)
        disk = run / 'disk.ext4'
        subprocess.run(['cp', '--reflink=auto', '--sparse=always',
                        str(backend.base_disk), str(disk)], check=True)
        backend._stage(disk, run, source,
                       [{'sku': 'apple', 'quantity': 2, 'unit_cents': 125}],
                       nonce, 'python', checkpoint_enabled=True)
        mount = run / 'mount-again'
        mount.mkdir()
        subprocess.run(['mount', '-o', 'loop', str(disk), str(mount)], check=True)
        try:
            child = subprocess.Popen(['chroot', str(mount), '/usr/bin/python3',
                                      '/root/dat_runner.py'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     bufsize=0)
            try:
                reader = LineReader(child.stdout)
                ready = reader.read_until('DAT_CHECKPOINT_READY:' + nonce)
                child.stdin.write(('DAT_CONTINUE:' + nonce + '\n').encode())
                child.stdin.flush()
                lines = reader.read_until('DAT_RESULT_END:' + nonce)
                prefix = 'DAT_RESULT:' + nonce + ':'
                execution = json.loads(base64.b64decode(next(
                    line[len(prefix):] for line in lines if line.startswith(prefix))))
                child.wait(timeout=5)
                stderr = child.stderr.read().decode('utf-8', errors='replace')
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        finally:
            subprocess.run(['umount', str(mount)], check=True)
    output = json.loads(execution['stdout'])
    continuity = json.loads(execution['stderr'])
    result = {'at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'chroot Python safe-point protocol only; no VM restore',
              'checkpoint_ready': ready[-1] == 'DAT_CHECKPOINT_READY:' + nonce,
              'execution': execution, 'wrapper_stderr': stderr,
              'all_pass': execution['status'] == 'ok'
              and output['total_cents'] == 250
              and continuity == {'counter_after_restore': 78,
                                 'disk_value_after_restore': '77'}}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

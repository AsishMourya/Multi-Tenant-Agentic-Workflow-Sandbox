"""Offline LangGraph and broker protocol check inside the prepared rootfs.

Chroot is only a package/protocol check. It is not an isolation demonstration.
"""
import argparse
import base64
import json
import os
import select
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.firecracker_backend import FirecrackerBackend


class LineReader:
    def __init__(self, stream):
        self.stream = stream
        self.pending = bytearray()

    def read_until(self, marker, timeout=25):
        lines = []
        deadline = time.monotonic() + timeout
        while True:
            while b'\n' in self.pending:
                line, _, remainder = self.pending.partition(b'\n')
                self.pending = bytearray(remainder)
                decoded = line.decode('utf-8', errors='replace').rstrip('\r')
                lines.append(decoded)
                if decoded == marker:
                    return lines
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(marker)
            ready, _, _ = select.select([self.stream], [], [], remaining)
            if not ready:
                raise TimeoutError(marker)
            chunk = os.read(self.stream.fileno(), 4096)
            if not chunk:
                raise RuntimeError('guest runtime closed before ' + marker +
                                   '; observed=' + repr(lines[-5:]))
            self.pending.extend(chunk)


def main(args):
    backend = FirecrackerBackend(args.root)
    source = (Path(__file__).resolve().parents[1] /
              'examples/inventory_langgraph_submission.py').read_text(encoding='utf-8')
    nonce = 'offline-chroot-probe'
    with tempfile.TemporaryDirectory(prefix='chroot-probe-', dir=backend.root) as directory:
        run = Path(directory)
        disk = run / 'disk.ext4'
        subprocess.run(['cp', '--reflink=auto', '--sparse=always',
                        str(backend.base_disk), str(disk)], check=True)
        backend._stage(disk, run, source, {'sku': 'apple', 'quantity': 2},
                       nonce, 'workflow')
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
                first = reader.read_until('DAT_BROKER_END:' + nonce)
                prefix = 'DAT_BROKER:' + nonce + ':'
                request = json.loads(base64.b64decode(next(
                    line[len(prefix):] for line in first if line.startswith(prefix))))
                response = {'sku': 'apple', 'available': 7}
                encoded = base64.b64encode(json.dumps(response).encode()).decode()
                child.stdin.write(('DAT_BROKER_REPLY:' + nonce + ':' + encoded + '\n').encode())
                child.stdin.flush()
                checkpoint = reader.read_until('DAT_CHECKPOINT_READY:' + nonce)
                child.stdin.write(('DAT_CONTINUE:' + nonce + '\n').encode())
                child.stdin.flush()
                second = reader.read_until('DAT_RESULT_END:' + nonce)
                prefix = 'DAT_RESULT:' + nonce + ':'
                execution = json.loads(base64.b64decode(next(
                    line[len(prefix):] for line in second if line.startswith(prefix))))
                child.wait(timeout=5)
                stderr = child.stderr.read().decode('utf-8', errors='replace')
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        finally:
            subprocess.run(['umount', str(mount)], check=True)
    result = {'at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'chroot package and serial broker protocol only; no VM isolation',
              'broker_request': request, 'execution': execution,
              'checkpoint_ready': checkpoint[-1] == 'DAT_CHECKPOINT_READY:' + nonce,
              'wrapper_stderr': stderr,
              'all_pass': request == {'operation': 'inventory.lookup',
                                      'args': {'sku': 'apple'}, 'request': 'lookup-1'}
              and execution['status'] == 'ok'
              and checkpoint[-1] == 'DAT_CHECKPOINT_READY:' + nonce
              and json.loads(execution['stdout'])['accepted'] is True}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

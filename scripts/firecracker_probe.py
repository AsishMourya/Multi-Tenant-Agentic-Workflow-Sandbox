"""Reproducible Firecracker boot, limit, network, and full-restore spike.

Run as WSL root after preparing a pinned Firecracker binary, kernel, and ext4
rootfs. This is a feasibility experiment, not the multi-tenant submission API.
"""
import argparse
import hashlib
import hashlib
import http.client
import json
import os
import pty
import select
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.vm_snapshot import verify_manifest, write_manifest


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=15)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def api(sock, method, route, body=None):
    connection = UnixHTTPConnection(str(sock))
    payload = json.dumps(body) if body is not None else None
    connection.request(method, route, payload,
                       {'Content-Type': 'application/json'} if payload else {})
    response = connection.getresponse()
    data = response.read().decode('utf-8', errors='replace')
    connection.close()
    if response.status >= 300:
        raise RuntimeError(f'{method} {route}: HTTP {response.status}: {data}')
    return {'status': response.status, 'body': data}


def digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


class Guest:
    def __init__(self, binary, sock, config=None):
        master, slave = pty.openpty()
        args = [str(binary), '--api-sock', str(sock)]
        if config is not None:
            args += ['--config-file', str(config)]
        self.proc = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave,
                                     start_new_session=True)
        os.close(slave)
        self.master = master
        self.transcript = bytearray()
        self.pending = bytearray()
        deadline = time.monotonic() + 15
        while not sock.exists():
            if self.proc.poll() is not None:
                raise RuntimeError('Firecracker exited before API socket became ready')
            if time.monotonic() >= deadline:
                raise TimeoutError('Firecracker API socket did not appear')
            time.sleep(.05)

    def read_until(self, marker, timeout=30):
        return self.read_until_any((marker,), timeout)[0]

    def read_until_any(self, markers, timeout=30):
        encoded = tuple(marker.encode() for marker in markers)
        deadline = time.monotonic() + timeout
        while True:
            matches = [(self.pending.find(marker), marker, markers[index])
                       for index, marker in enumerate(encoded)]
            matches = [item for item in matches if item[0] >= 0]
            if matches:
                position, marker, label = min(matches, key=lambda item: item[0])
                end = position + len(marker)
                output = bytes(self.pending[:end])
                del self.pending[:end]
                return output.decode('utf-8', errors='replace'), label
            if time.monotonic() >= deadline:
                raise TimeoutError(f'guest output marker not seen: {markers!r}')
            ready, _, _ = select.select([self.master], [], [], min(.5, deadline-time.monotonic()))
            if ready:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError:
                    chunk = b''
                if not chunk:
                    tail = self.transcript[-2000:].decode('utf-8', errors='replace')
                    raise RuntimeError(f'guest console closed before marker; console tail: {tail}')
                self.transcript.extend(chunk)
                self.pending.extend(chunk.replace(b'\r', b''))
                if len(self.pending) > 512 * 1024:
                    raise ValueError('guest console output exceeded capture limit')

    def command(self, command, marker):
        os.write(self.master, (command + '\necho ' + marker + '\n').encode())
        return self.read_until('\n' + marker + '\n', timeout=30)

    def stop(self):
        if self.proc.poll() is None:
            os.write(self.master, b'reboot\n')
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                self.proc.wait(timeout=10)
        os.close(self.master)


def main(args):
    root = Path(args.root).resolve()
    binary = root / 'firecracker'
    kernel = root / 'vmlinux-6.1.188'
    source_disk = root / 'ubuntu.ext4'
    for path in (binary, kernel, source_disk):
        if not path.is_file():
            raise FileNotFoundError(path)
    run = root / ('probe-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    run.mkdir(mode=0o700)
    disk = run / 'disk.ext4'
    subprocess.run(['cp', '--reflink=auto', '--sparse=always', str(source_disk), str(disk)], check=True)
    config = run / 'boot.json'
    config.write_text(json.dumps({
        'boot-source': {'kernel_image_path': str(kernel),
                        'boot_args': 'console=ttyS0 reboot=k panic=1 root=/dev/vda rw'},
        'drives': [{'drive_id': 'rootfs', 'path_on_host': str(disk),
                    'is_root_device': True, 'is_read_only': False}],
        'machine-config': {'vcpu_count': 1, 'mem_size_mib': 128,
                           'smt': False, 'track_dirty_pages': False},
        'network-interfaces': [],
    }, indent=2), encoding='utf-8')
    runtime_sha256 = hashlib.sha256((digest(binary) + digest(kernel)).encode()).hexdigest()
    policy_sha256 = digest(config)
    sock = run / 'firecracker.sock'
    snapshot = run / 'snapshot'
    snapshot.mkdir()
    observations = {}
    first = Guest(binary, sock, config)
    try:
        first.read_until('root@ubuntu-fc-uvm:~#', timeout=45)
        output = first.command("python3 -c 'print(6 * 7)'", 'PY_DONE_44')
        observations['python_42'] = '\n42\n' in output
        output = first.command("python3 -c 'x=bytearray(200*1024*1024); print(len(x))'", 'MEM_DONE_44')
        observations['memory_error_200_mib'] = 'MemoryError' in output
        output = first.command("python3 -c 'import socket; s=socket.socket(); s.settimeout(2); s.connect((\"1.1.1.1\", 80))'", 'NET_DONE_44')
        observations['network_unreachable'] = 'Network is unreachable' in output
        output = first.command('echo 77 > /root/counter.txt; sync; cat /root/counter.txt', 'PRE_DONE_44')
        observations['pre_snapshot_77'] = '\n77\n' in output
        observations['pause_http'] = api(sock, 'PATCH', '/vm', {'state': 'Paused'})['status']
        observations['snapshot_http'] = api(sock, 'PUT', '/snapshot/create', {
            'snapshot_type': 'Full', 'snapshot_path': str(snapshot / 'machine.vmstate'),
            'mem_file_path': str(snapshot / 'memory.mem')})['status']
        shutil.copyfile(disk, snapshot / 'disk.ext4')
        with open(snapshot / 'disk.ext4', 'rb') as stream:
            os.fsync(stream.fileno())
        manifest = write_manifest(snapshot, tenant='probe', session=run.name,
                                  runtime_sha256=runtime_sha256,
                                  policy_sha256=policy_sha256)
        observations['manifest_created'] = bool(manifest['created_at_utc'])
        observations['resume_http'] = api(sock, 'PATCH', '/vm', {'state': 'Resumed'})['status']
        output = first.command('echo 99 > /root/counter.txt; sync; cat /root/counter.txt', 'POST_DONE_44')
        observations['post_snapshot_99'] = '\n99\n' in output
    finally:
        first.stop()
        (run / 'first-console.log').write_bytes(first.transcript)
    observations['manifest_verified'] = verify_manifest(
        snapshot, tenant='probe', session=run.name,
        runtime_sha256=runtime_sha256, policy_sha256=policy_sha256) == manifest
    subprocess.run(['cp', '--reflink=auto', str(snapshot / 'disk.ext4'), str(disk)], check=True)
    sock.unlink(missing_ok=True)
    second = Guest(binary, sock)
    try:
        observations['load_http'] = api(sock, 'PUT', '/snapshot/load', {
            'snapshot_path': str(snapshot / 'machine.vmstate'),
            'mem_backend': {'backend_type': 'File',
                            'backend_path': str(snapshot / 'memory.mem')},
            'track_dirty_pages': False, 'resume_vm': True})['status']
        output = second.command('cat /root/counter.txt', 'RESTORE_DONE_44')
        observations['restored_77'] = '\n77\n' in output
        output = second.command("python3 -c 'print(7 * 6)'", 'RESTORED_PY_DONE_44')
        observations['restored_python_42'] = '\n42\n' in output
    finally:
        second.stop()
        (run / 'restored-console.log').write_bytes(second.transcript)
    result = {
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'single-host Firecracker feasibility; no tenant submission integration or broker transport',
        'firecracker_version': subprocess.check_output([str(binary), '--version'], text=True).strip(),
        'kernel_sha256': digest(kernel),
        'binary_sha256': digest(binary),
        'snapshot_artifacts': {name: {'bytes': (snapshot / name).stat().st_size,
                                      'sha256': digest(snapshot / name)}
                               for name in ('machine.vmstate', 'memory.mem', 'disk.ext4')},
        'observations': observations,
        'run_directory': str(run),
    }
    passed = all(value is True if isinstance(value, bool) else value == 204
                 for value in observations.values())
    result['all_pass'] = passed
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

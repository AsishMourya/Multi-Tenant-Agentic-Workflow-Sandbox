"""Fail-closed single-machine Firecracker runner for submitted Python code.

Linux root and working KVM are required. A separate ext4 copy is used for each
submission. The guest has no network interface and learner code runs as nobody.
"""
import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from sandbox.vm_snapshot import (acquire_resume_lease, release_resume_lease,
                                 sha256, verify_manifest, write_manifest)


DEFAULT_POLICY = {
    'vcpu_count': 1, 'mem_size_mib': 512, 'cpu_seconds': 5,
    'address_bytes': 256 * 1024 * 1024, 'processes': 16,
    'output_bytes': 65536, 'wall_seconds': 15,
    'snapshot_wall_seconds': 120,
}


class BackendUnavailable(RuntimeError):
    pass


class FirecrackerBackend:
    def __init__(self, root='/root/dat-backend', policy=None,
                 image='ubuntu-langgraph-2026-10-16-v2.ext4'):
        self.root = Path(root).resolve()
        self.binary = self.root / 'firecracker'
        self.kernel = self.root / 'vmlinux-6.1.188'
        self.base_disk = self.root / image
        self.policy = dict(DEFAULT_POLICY if policy is None else policy)
        limits = {'vcpu_count': (1, 2), 'mem_size_mib': (128, 512),
                  'cpu_seconds': (1, 5), 'address_bytes': (64 * 1024 * 1024,
                                                        512 * 1024 * 1024),
                  'processes': (1, 16), 'output_bytes': (1024, 65536),
                  'wall_seconds': (1, 30), 'snapshot_wall_seconds': (30, 180)}
        if set(self.policy) != set(limits) or any(
            type(self.policy[key]) is not int or not low <= self.policy[key] <= high
            for key, (low, high) in limits.items()
        ):
            raise ValueError('invalid or excessive resource policy')

    def _preflight(self):
        if os.name != 'posix' or os.geteuid() != 0:
            raise BackendUnavailable('Firecracker backend requires Linux root')
        for path in (self.binary, self.kernel, self.base_disk):
            if not path.is_file():
                raise BackendUnavailable(f'missing backend artifact: {path}')
        try:
            import fcntl
            with open('/dev/kvm', 'rb+', buffering=0) as device:
                version = fcntl.ioctl(device.fileno(), 0xAE00, 0)
        except OSError as exc:
            raise BackendUnavailable(f'KVM is unavailable: {exc}') from exc
        if version != 12:
            raise BackendUnavailable(f'unsupported KVM API version: {version}')
        lock_path = Path(__file__).resolve().parents[1] / 'config/firecracker_backend_lock.json'
        lock = json.loads(lock_path.read_text(encoding='utf-8'))
        observed = {'image_name': self.base_disk.name,
                    'image_sha256': sha256(self.base_disk),
                    'firecracker_sha256': sha256(self.binary),
                    'kernel_sha256': sha256(self.kernel)}
        if any(lock.get(key) != value for key, value in observed.items()):
            raise BackendUnavailable('backend artifact does not match pinned lock')
        return observed['image_sha256']

    def _stage(self, disk, run, source, payload, nonce, mode='python',
               checkpoint_enabled=False):
        mount = run / 'mount'
        mount.mkdir()
        subprocess.run(['mount', '-o', 'loop', str(disk), str(mount)], check=True)
        try:
            (mount / 'tmp').chmod(0o1777)
            submission = mount / 'tmp' / 'dat_submission.py'
            submission.write_text(source, encoding='utf-8')
            submission.chmod(0o644)
            runner = mount / 'root' / 'dat_runner.py'
            shutil.copyfile(Path(__file__).with_name('guest_runtime.py'), runner)
            runner.chmod(0o600)
            broker_client = mount / 'tmp' / 'guest_broker_client.py'
            shutil.copyfile(Path(__file__).with_name('guest_broker_client.py'), broker_client)
            broker_client.chmod(0o644)
            checkpoint_client = mount / 'tmp' / 'guest_checkpoint_client.py'
            shutil.copyfile(Path(__file__).with_name('guest_checkpoint_client.py'),
                            checkpoint_client)
            checkpoint_client.chmod(0o644)
            input_file = mount / 'root' / 'dat_input.json'
            input_file.write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')
            input_file.chmod(0o600)
            config = mount / 'root' / 'dat_config.json'
            settings = {**self.policy, 'nonce': nonce, 'mode': mode,
                        'checkpoint_enabled': checkpoint_enabled or mode == 'workflow'}
            if checkpoint_enabled or mode == 'workflow':
                settings['wall_seconds'] = self.policy['snapshot_wall_seconds']
            config.write_text(json.dumps(settings), encoding='utf-8')
            config.chmod(0o600)
            subprocess.run(['sync'], check=True)
        finally:
            subprocess.run(['umount', str(mount)], check=True)
            mount.rmdir()

    def run_python(self, tenant, session, source, payload, *, checkpoint=False,
                   on_pause=None, on_resume=None):
        if (on_pause is None) != (on_resume is None):
            raise ValueError('pause and resume callbacks must be paired')
        return self._run(tenant, session, source, payload, mode='python',
                         checkpoint_enabled=checkpoint, on_pause=on_pause,
                         on_resume=on_resume)

    def run_workflow(self, tenant, session, source, payload, broker_call,
                     on_pause=None, on_resume=None):
        if not callable(broker_call):
            raise TypeError('broker callback required')
        if (on_pause is None) != (on_resume is None):
            raise ValueError('pause and resume callbacks must be paired')
        return self._run(tenant, session, source, payload, mode='workflow',
                         broker_call=broker_call, on_pause=on_pause,
                         on_resume=on_resume)

    @staticmethod
    def _stop_guest(guest):
        if guest.proc.poll() is None:
            guest.proc.terminate()
            try:
                guest.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                guest.proc.kill()
                guest.proc.wait(timeout=5)
        os.close(guest.master)

    def _snapshot_restore(self, guest, *, run, disk, config, tenant, session,
                          image_digest, on_pause, on_resume, Guest, api):
        snapshot = run / 'snapshot'
        snapshot.mkdir()
        sock = run / 'firecracker.sock'
        restored = None
        lease = None
        try:
            api(sock, 'PATCH', '/vm', {'state': 'Paused'})
            api(sock, 'PUT', '/snapshot/create', {
                'snapshot_type': 'Full',
                'snapshot_path': str(snapshot / 'machine.vmstate'),
                'mem_file_path': str(snapshot / 'memory.mem'),
            })
            shutil.copyfile(disk, snapshot / 'disk.ext4')
            binary_digest = sha256(self.binary)
            kernel_digest = sha256(self.kernel)
            runtime_sha256 = hashlib.sha256(
                (binary_digest + kernel_digest + image_digest).encode()).hexdigest()
            policy_sha256 = hashlib.sha256(
                config.read_bytes() + json.dumps(self.policy, sort_keys=True).encode()).hexdigest()
            runtime = {'firecracker_version': 'v1.17.0',
                       'firecracker_sha256': binary_digest,
                       'kernel_sha256': kernel_digest,
                       'image_sha256': image_digest,
                       'python_version': '3.12', 'langgraph_version': '1.2.2'}
            manifest = write_manifest(snapshot, tenant=tenant, session=session,
                                      runtime_sha256=runtime_sha256,
                                      policy_sha256=policy_sha256,
                                      runtime=runtime, resource_policy=self.policy)
            if on_pause is not None:
                on_pause(manifest)
            self._stop_guest(guest)
            guest = None
            verify_manifest(snapshot, tenant=tenant, session=session,
                            runtime_sha256=runtime_sha256,
                            policy_sha256=policy_sha256,
                            runtime=runtime, resource_policy=self.policy)
            lease = acquire_resume_lease(snapshot)
            shutil.copyfile(snapshot / 'disk.ext4', disk)
            sock.unlink(missing_ok=True)
            restored = Guest(self.binary, sock)
            api(sock, 'PUT', '/snapshot/load', {
                'snapshot_path': str(snapshot / 'machine.vmstate'),
                'mem_backend': {'backend_type': 'File',
                                'backend_path': str(snapshot / 'memory.mem')},
                'track_dirty_pages': False, 'resume_vm': True,
            })
            if on_resume is not None:
                on_resume()
            return restored, {'manifest': manifest, 'compute_released': True,
                              'restored': True}, lease
        except Exception:
            if restored is not None:
                self._stop_guest(restored)
            if lease is not None:
                release_resume_lease(lease)
            raise
        finally:
            if guest is not None:
                self._stop_guest(guest)

    def _run(self, tenant, session, source, payload, *, mode, broker_call=None,
             checkpoint_enabled=False, on_pause=None, on_resume=None):
        if not tenant or not session:
            raise ValueError('tenant and session required')
        if not isinstance(source, str) or not 1 <= len(source.encode('utf-8')) <= 32768:
            raise ValueError('source must be 1-32768 UTF-8 bytes')
        encoded_payload = json.dumps(payload, allow_nan=False).encode()
        if len(encoded_payload) > 65536:
            raise ValueError('input exceeds 65536 bytes')
        image_digest = self._preflight()
        from scripts.firecracker_probe import Guest, api

        nonce = secrets.token_hex(16)
        run = self.root / ('submission-' + secrets.token_hex(12))
        run.mkdir(mode=0o700)
        guest = None
        resume_lease = None
        snapshot_info = None
        started = time.monotonic()
        try:
            disk = run / 'disk.ext4'
            subprocess.run(['cp', '--reflink=auto', '--sparse=always',
                            str(self.base_disk), str(disk)], check=True)
            self._stage(disk, run, source, payload, nonce, mode,
                        checkpoint_enabled=checkpoint_enabled)
            config = run / 'boot.json'
            config.write_text(json.dumps({
                'boot-source': {'kernel_image_path': str(self.kernel),
                                'boot_args': 'console=ttyS0 reboot=k panic=1 root=/dev/vda rw'},
                'drives': [{'drive_id': 'rootfs', 'path_on_host': str(disk),
                            'is_root_device': True, 'is_read_only': False}],
                'machine-config': {'vcpu_count': self.policy['vcpu_count'],
                                   'mem_size_mib': self.policy['mem_size_mib'],
                                   'smt': False, 'track_dirty_pages': False},
                'network-interfaces': [],
            }), encoding='utf-8')
            guest = Guest(self.binary, run / 'firecracker.sock', config)
            guest.read_until('root@ubuntu-fc-uvm:~#', timeout=45)
            os.write(guest.master, b'python3 /root/dat_runner.py\n')
            result_marker = 'DAT_RESULT_END:' + nonce + '\n'
            checkpoint_marker = 'DAT_CHECKPOINT_READY:' + nonce + '\n'
            if mode == 'workflow':
                broker_marker = 'DAT_BROKER_END:' + nonce + '\n'
                output, event = guest.read_until_any((broker_marker, result_marker), timeout=25)
                if event == broker_marker:
                    broker_prefix = 'DAT_BROKER:' + nonce + ':'
                    broker_line = next((line for line in output.splitlines()
                                        if line.startswith(broker_prefix)), None)
                    if broker_line is None:
                        raise RuntimeError('guest broker marker missing')
                    request = json.loads(base64.b64decode(broker_line[len(broker_prefix):], validate=True))
                    try:
                        response = broker_call(request)
                    except (PermissionError, ValueError, KeyError, TypeError):
                        response = {'error': 'denied'}
                    encoded = base64.b64encode(json.dumps(response).encode()).decode()
                    os.write(guest.master, ('DAT_BROKER_REPLY:' + nonce + ':' + encoded + '\n').encode())
                    output, event = guest.read_until_any((checkpoint_marker, result_marker), timeout=25)
            elif checkpoint_enabled:
                output, event = guest.read_until_any((checkpoint_marker, result_marker),
                                                     timeout=25)
            else:
                output = guest.read_until(result_marker, timeout=30)
                event = result_marker
            if event == checkpoint_marker:
                old_guest = guest
                guest = None
                guest, snapshot_info, resume_lease = self._snapshot_restore(
                    old_guest, run=run, disk=disk, config=config,
                    tenant=tenant, session=session, image_digest=image_digest,
                    on_pause=on_pause, on_resume=on_resume, Guest=Guest, api=api)
                os.write(guest.master, ('DAT_CONTINUE:' + nonce + '\n').encode())
                output = guest.read_until(result_marker, timeout=30)
            prefix = 'DAT_RESULT:' + nonce + ':'
            line = next((line for line in output.splitlines() if line.startswith(prefix)), None)
            if line is None:
                raise RuntimeError('guest result marker missing')
            result = json.loads(base64.b64decode(line[len(prefix):], validate=True))
            result['backend'] = 'firecracker'
            result['runtime_image_digest'] = image_digest
            result['resource_policy'] = dict(self.policy)
            result['tenant'] = tenant
            result['session'] = session
            result['total_wall_seconds'] = round(time.monotonic() - started, 3)
            if snapshot_info is not None:
                result['snapshot'] = snapshot_info
            return result
        finally:
            if guest is not None:
                self._stop_guest(guest)
            if resume_lease is not None:
                release_resume_lease(resume_lease)
            shutil.rmtree(run)

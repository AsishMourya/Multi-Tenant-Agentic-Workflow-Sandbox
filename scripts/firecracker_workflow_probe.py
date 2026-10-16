"""Guest-to-host broker and pause/restore protocol feasibility spike.

The guest uses a serial request/response bridge. This is deliberately a protocol
probe, not the final authenticated transport or a LangGraph guest image.
"""
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.broker import Broker
from sandbox.vm_snapshot import verify_manifest, write_manifest
from firecracker_probe import Guest, api, digest


GUEST_CODE = '''import json, os
request = {'request': 'lookup-1', 'operation': 'inventory.lookup', 'args': {'sku': 'apple'}}
print('BROKER_REQUEST:' + json.dumps(request, sort_keys=True), flush=True)
print('BROKER_REQUEST_END', flush=True)
answer = json.loads(input())
os.sync()
print('CHECKPOINT_READY', flush=True)
input()
print('WORKFLOW_RESULT:' + json.dumps({'accepted': 2 <= answer['available'], 'available': answer['available']}), flush=True)
print('WORKFLOW_RESULT_END', flush=True)
'''


def main(args):
    root = Path(args.root).resolve()
    binary, kernel, base_disk = (root / 'firecracker', root / 'vmlinux-6.1.188', root / 'ubuntu.ext4')
    run = root / ('workflow-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    run.mkdir(mode=0o700)
    disk = run / 'disk.ext4'
    subprocess.run(['cp', '--reflink=auto', '--sparse=always', str(base_disk), str(disk)], check=True)
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
    snapshot = run / 'snapshot'
    snapshot.mkdir()
    sock = run / 'firecracker.sock'
    broker = Broker(str(run / 'broker.sqlite3'))
    tenant, session, exercise = 'tenant-a', 'guest-workflow-1', 'inventory-v1'
    broker.register(tenant, session, exercise)
    principal = (tenant, session, exercise)
    old_token = broker.issue(*principal)
    evidence = {}
    first = Guest(binary, sock, config)
    try:
        first.read_until('root@ubuntu-fc-uvm:~#', timeout=45)
        encoded = base64.b64encode(GUEST_CODE.encode()).decode()
        os.write(first.master, ("python3 -c 'import base64; exec(base64.b64decode(\"" +
                                encoded + "\"))'\n").encode())
        output = first.read_until('BROKER_REQUEST_END\n', timeout=20)
        request_line = next(line for line in output.splitlines() if line.startswith('BROKER_REQUEST:'))
        request = json.loads(request_line.removeprefix('BROKER_REQUEST:'))
        result = broker.call(principal, old_token, request['operation'], request['args'], request['request'])
        evidence['guest_request'] = request
        evidence['broker_response'] = result
        os.write(first.master, (json.dumps(result) + '\n').encode())
        output = first.read_until('CHECKPOINT_READY\n', timeout=20)
        evidence['checkpoint_ready'] = 'CHECKPOINT_READY\n' in output
        evidence['pause_http'] = api(sock, 'PATCH', '/vm', {'state': 'Paused'})['status']
        evidence['snapshot_http'] = api(sock, 'PUT', '/snapshot/create', {
            'snapshot_type': 'Full', 'snapshot_path': str(snapshot / 'machine.vmstate'),
            'mem_file_path': str(snapshot / 'memory.mem')})['status']
        shutil.copyfile(disk, snapshot / 'disk.ext4')
        manifest = write_manifest(snapshot, tenant=tenant, session=session,
                                  runtime_sha256=runtime_sha256,
                                  policy_sha256=policy_sha256)
        evidence['manifest_created'] = bool(manifest['created_at_utc'])
        try:
            verify_manifest(snapshot, tenant='tenant-b', session=session,
                            runtime_sha256=runtime_sha256,
                            policy_sha256=policy_sha256)
            evidence['foreign_owner_denied'] = False
        except ValueError:
            evidence['foreign_owner_denied'] = True
        broker.revoke(session)
        try:
            broker.call(principal, old_token, request['operation'], request['args'], request['request'])
            evidence['old_capability_denied'] = False
        except PermissionError:
            evidence['old_capability_denied'] = True
    finally:
        if first.proc.poll() is None:
            first.proc.terminate()
            first.proc.wait(timeout=10)
        os.close(first.master)
        (run / 'first-console.log').write_bytes(first.transcript)
    verified = verify_manifest(snapshot, tenant=tenant, session=session,
                               runtime_sha256=runtime_sha256,
                               policy_sha256=policy_sha256)
    evidence['manifest_verified'] = verified == manifest
    subprocess.run(['cp', '--reflink=auto', str(snapshot / 'disk.ext4'), str(disk)], check=True)
    sock.unlink(missing_ok=True)
    second = Guest(binary, sock)
    try:
        evidence['load_http'] = api(sock, 'PUT', '/snapshot/load', {
            'snapshot_path': str(snapshot / 'machine.vmstate'),
            'mem_backend': {'backend_type': 'File',
                            'backend_path': str(snapshot / 'memory.mem')},
            'track_dirty_pages': False, 'resume_vm': True})['status']
        broker.resume(*principal)
        fresh_token = broker.issue(*principal)
        evidence['fresh_epoch'] = fresh_token['cap']['epoch'] > old_token['cap']['epoch']
        retry = broker.call(principal, fresh_token, request['operation'], request['args'], request['request'])
        evidence['replay_cached'] = retry == result and broker.db.execute(
            'SELECT count(*) FROM calls WHERE session=?', (session,)).fetchone()[0] == 1
        os.write(second.master, b'continue\n')
        output = second.read_until('WORKFLOW_RESULT_END\n', timeout=20)
        result_line = next(line for line in output.splitlines() if line.startswith('WORKFLOW_RESULT:'))
        evidence['restored_result'] = json.loads(result_line.removeprefix('WORKFLOW_RESULT:'))
    finally:
        second.stop()
        (run / 'restored-console.log').write_bytes(second.transcript)
        broker.db.close()
    result_record = {
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'single guest serial broker protocol probe; no production transport or LangGraph guest',
        'firecracker_binary_sha256': digest(binary),
        'snapshot_files': {name: {'bytes': (snapshot / name).stat().st_size,
                                  'sha256': digest(snapshot / name)}
                           for name in ('machine.vmstate', 'memory.mem', 'disk.ext4')},
        'observations': evidence,
        'run_directory': str(run),
    }
    expected = (evidence.get('checkpoint_ready') and evidence.get('pause_http') == 204
                and evidence.get('snapshot_http') == 204 and evidence.get('load_http') == 204
                and evidence.get('old_capability_denied') and evidence.get('fresh_epoch')
                and evidence.get('manifest_created') and evidence.get('manifest_verified')
                and evidence.get('foreign_owner_denied')
                and evidence.get('replay_cached') and evidence.get('restored_result') ==
                {'accepted': True, 'available': 7})
    result_record['all_pass'] = bool(expected)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_record, indent=2), encoding='utf-8')
    print(json.dumps(result_record, indent=2))
    return 0 if expected else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))

"""Integrity and compatibility checks for same-host Firecracker snapshots.

The host and its snapshot store are trusted. Hashes detect incomplete or changed
artifacts; this is not an authentication mechanism against a malicious host.
"""
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


ARTIFACTS = ('machine.vmstate', 'memory.mem', 'disk.ext4')
SCHEMA = 'firecracker-full-snapshot-1'


def sha256(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def _artifact(path):
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size == 0:
        raise ValueError(f'invalid snapshot artifact: {path.name}')
    return {'bytes': metadata.st_size, 'sha256': sha256(path)}


def write_manifest(directory, *, tenant, session, runtime_sha256, policy_sha256,
                   runtime=None, resource_policy=None):
    """Publish the manifest only after all three snapshot files are durable."""
    directory = Path(directory)
    if not all(isinstance(value, str) and value for value in
               (tenant, session, runtime_sha256, policy_sha256)):
        raise ValueError('snapshot identity is incomplete')
    artifacts = {name: _artifact(directory / name) for name in ARTIFACTS}
    for name in ARTIFACTS:
        with (directory / name).open('rb+') as stream:
            os.fsync(stream.fileno())
    manifest = {
        'schema': SCHEMA, 'tenant': tenant, 'session': session,
        'runtime_sha256': runtime_sha256, 'policy_sha256': policy_sha256,
        'runtime': runtime or {}, 'resource_policy': resource_policy or {},
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'artifacts': artifacts,
    }
    temporary = directory / 'manifest.json.tmp'
    destination = directory / 'manifest.json'
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)
    if hasattr(os, 'O_DIRECTORY'):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return manifest


def verify_manifest(directory, *, tenant, session, runtime_sha256, policy_sha256,
                    runtime=None, resource_policy=None):
    directory = Path(directory)
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('snapshot manifest missing or invalid') from exc
    expected = {'schema': SCHEMA, 'tenant': tenant, 'session': session,
                'runtime_sha256': runtime_sha256, 'policy_sha256': policy_sha256}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError('snapshot identity or compatibility mismatch')
    if runtime is not None and manifest.get('runtime') != runtime:
        raise ValueError('snapshot runtime mismatch')
    if resource_policy is not None and manifest.get('resource_policy') != resource_policy:
        raise ValueError('snapshot resource policy mismatch')
    recorded = manifest.get('artifacts')
    if not isinstance(recorded, dict) or set(recorded) != set(ARTIFACTS):
        raise ValueError('snapshot artifact list is incomplete')
    for name in ARTIFACTS:
        try:
            actual = _artifact(directory / name)
        except (OSError, ValueError) as exc:
            raise ValueError(f'snapshot artifact missing or invalid: {name}') from exc
        if recorded[name] != actual:
            raise ValueError(f'snapshot artifact changed: {name}')
    return manifest


def acquire_resume_lease(directory):
    """Hold a kernel-released exclusive lock while a restored VM is active."""
    import fcntl
    descriptor = os.open(Path(directory) / 'resume.lock',
                         os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise ValueError('snapshot already has an active resume') from exc
    return descriptor


def release_resume_lease(descriptor):
    import fcntl
    fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)

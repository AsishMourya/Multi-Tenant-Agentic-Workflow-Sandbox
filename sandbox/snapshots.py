"""Atomic trusted snapshot bundles. Capture callback runs while the VMM stays paused.
Linux fsync/rename/flock provide the durability path; Windows is for fixture tests only.
No student-controlled serialization or arbitrary artifact paths are loaded.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ARTIFACTS = ('machine.vmstate', 'memory.mem', 'disk.ext4')
ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')

class SnapshotError(ValueError): pass

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def sync_file(path):
    with open(path, 'r+b' if os.name == 'nt' else 'rb') as f: os.fsync(f.fileno())

def sync_dir(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

class SnapshotStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt': self.root.chmod(0o700)

    @contextmanager
    def lock(self):
        with open(self.root / '.lock', 'a+b') as f:
            if os.name == 'nt':
                import msvcrt
                if f.tell() == 0: f.write(b'0'); f.flush()
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try: yield
            finally:
                if os.name == 'nt':
                    f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else: fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def path(self, snapshot_id):
        if not isinstance(snapshot_id, str) or not ID.fullmatch(snapshot_id): raise SnapshotError('invalid snapshot ID')
        return self.root / snapshot_id

    def publish(self, snapshot_id, tenant, session, compatibility, policy, disk, capture, interrupt=None):
        """capture(state_path, memory_path); interrupt phases only for trusted fault fixtures."""
        target = self.path(snapshot_id)
        phase = interrupt or (lambda name: None)
        with self.lock():
            if target.exists(): raise SnapshotError('immutable snapshot ID already exists')
            staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=self.root))
            # An interrupted creation deliberately leaves staging for recovery to discard.
            capture(staging / ARTIFACTS[0], staging / ARTIFACTS[1])
            phase('after-capture')
            sync_file(disk)
            shutil.copyfile(disk, staging / ARTIFACTS[2])
            phase('after-disk')
            for name in ARTIFACTS:
                p = staging / name
                if p.is_symlink() or not p.is_file() or p.stat().st_size == 0: raise SnapshotError('missing/empty artifact')
                sync_file(p)
            manifest = {'schema_version': '1.0.0', 'complete': True, 'snapshot_id': snapshot_id,
                        'tenant': tenant, 'session': session, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                        'compatibility': compatibility, 'policy': policy,
                        'artifacts': {name: {'bytes': (staging/name).stat().st_size, 'sha256': sha256(staging/name)} for name in ARTIFACTS}}
            m = staging / 'manifest.json'
            m.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
            sync_file(m); sync_dir(staging)
            phase('after-manifest')
            if os.name != 'nt':
                for p in staging.iterdir(): p.chmod(0o400)
                staging.chmod(0o500)
            os.rename(staging, target)  # Same filesystem: complete bundle becomes visible once.
            sync_dir(self.root)
            phase('after-publish')
            return manifest

    def validate(self, snapshot_id, tenant, session, compatibility, policy):
        bundle = self.path(snapshot_id)
        if bundle.is_symlink() or not bundle.is_dir(): raise SnapshotError('unpublished snapshot')
        try:
            mp = bundle / 'manifest.json'
            if mp.is_symlink() or mp.stat().st_size > 65536: raise SnapshotError('invalid manifest')
            m = json.loads(mp.read_text(encoding='utf-8'))
            expected = {'schema_version','complete','snapshot_id','tenant','session','created_at_utc','compatibility','policy','artifacts'}
            if set(m) != expected or m['schema_version'] != '1.0.0' or m['complete'] is not True or m['snapshot_id'] != snapshot_id: raise SnapshotError('incomplete or malformed manifest')
            if (m['tenant'],m['session']) != (tenant,session): raise SnapshotError('ownership mismatch')
            if m['compatibility'] != compatibility or m['policy'] != policy: raise SnapshotError('compatibility/policy mismatch')
            if set(m['artifacts']) != set(ARTIFACTS) or set(p.name for p in bundle.iterdir()) != set(ARTIFACTS)|{'manifest.json'}: raise SnapshotError('artifact set mismatch')
            for name in ARTIFACTS:
                p = bundle / name; info = m['artifacts'][name]
                if p.is_symlink() or not p.is_file() or p.stat().st_size == 0 or p.stat().st_size != info['bytes'] or sha256(p) != info['sha256']: raise SnapshotError('artifact integrity mismatch')
            return m
        except (OSError,KeyError,TypeError,json.JSONDecodeError) as e: raise SnapshotError('invalid snapshot bundle') from e

    def restore_copies(self, snapshot_id, tenant, session, compatibility, policy, directory, disk_path):
        self.validate(snapshot_id, tenant, session, compatibility, policy)
        source = self.path(snapshot_id); destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=False)
        for name in ARTIFACTS[:2]: shutil.copyfile(source/name, destination/name)
        # Snapshot records this trusted VMM's original drive path. Replace only after VMM exit.
        shutil.copyfile(source/ARTIFACTS[2], disk_path)
        return destination/ARTIFACTS[0], destination/ARTIFACTS[1]

    def recover(self):
        """Lock excludes active publishers; crashed publishers release lock automatically."""
        discarded = []
        with self.lock():
            for p in self.root.iterdir():
                if p.name.startswith('.staging-') and p.is_dir() and not p.is_symlink():
                    if os.name != 'nt':
                        p.chmod(0o700)
                        for item in p.iterdir(): item.chmod(0o600)
                    shutil.rmtree(p); discarded.append(p.name)
            sync_dir(self.root)
        return discarded

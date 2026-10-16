import os
import tempfile
import unittest
from pathlib import Path

from sandbox.vm_snapshot import (ARTIFACTS, acquire_resume_lease,
                                 release_resume_lease, verify_manifest,
                                 write_manifest)


class VmSnapshotManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        for name in ARTIFACTS:
            (self.directory / name).write_bytes(name.encode())
        self.identity = {'tenant': 'tenant-a', 'session': 'session-1',
                         'runtime_sha256': 'runtime-digest', 'policy_sha256': 'policy-digest'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_verified_complete_snapshot(self):
        created = write_manifest(self.directory, **self.identity)
        self.assertEqual(verify_manifest(self.directory, **self.identity), created)

    def test_rejects_foreign_owner_and_incompatible_policy(self):
        write_manifest(self.directory, **self.identity,
                       runtime={'python_version': '3.12'},
                       resource_policy={'mem_size_mib': 512})
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            verify_manifest(self.directory, **{**self.identity, 'tenant': 'tenant-b'})
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            verify_manifest(self.directory, **{**self.identity, 'policy_sha256': 'different'})
        with self.assertRaisesRegex(ValueError, 'resource policy mismatch'):
            verify_manifest(self.directory, **self.identity,
                            resource_policy={'mem_size_mib': 1024})

    def test_rejects_changed_or_missing_artifact(self):
        write_manifest(self.directory, **self.identity)
        (self.directory / 'memory.mem').write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'changed'):
            verify_manifest(self.directory, **self.identity)
        (self.directory / 'memory.mem').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            verify_manifest(self.directory, **self.identity)

    def test_does_not_publish_incomplete_snapshot(self):
        (self.directory / 'disk.ext4').unlink()
        with self.assertRaises(FileNotFoundError):
            write_manifest(self.directory, **self.identity)
        self.assertFalse((self.directory / 'manifest.json').exists())

    @unittest.skipUnless(os.name == 'posix', 'resume lease uses Linux file locks')
    def test_only_one_active_resume_lease(self):
        first = acquire_resume_lease(self.directory)
        try:
            with self.assertRaisesRegex(ValueError, 'active resume'):
                acquire_resume_lease(self.directory)
        finally:
            release_resume_lease(first)
        second = acquire_resume_lease(self.directory)
        release_resume_lease(second)


if __name__ == '__main__':
    unittest.main()

import importlib
import os
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from sandbox.firecracker_backend import FirecrackerBackend

if os.name == 'nt':
    with patch.dict(sys.modules, {'resource': Mock()}):
        guest_runtime = importlib.import_module('sandbox.guest_runtime')
else:
    guest_runtime = importlib.import_module('sandbox.guest_runtime')
_prepare_writable_space = guest_runtime._prepare_writable_space


class DiskLimitTests(unittest.TestCase):
    def test_guest_mounts_share_bounded_scratch_and_seal_root(self):
        settings = {'writable_disk_bytes': 32 * 1024 * 1024}
        with patch('sandbox.guest_runtime.subprocess.run') as run, \
             patch('sandbox.guest_runtime.os.makedirs') as makedirs:
            _prepare_writable_space(settings)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0], ['mount', '-t', 'tmpfs', '-o',
                                       'size=33554432,mode=1777,nosuid,nodev',
                                       'tmpfs', '/tmp'])
        self.assertEqual(commands[1:4], [
            ['mount', '--bind', '/tmp', directory]
            for directory in ('/var/tmp', '/dev/shm', '/run/lock')])
        self.assertEqual(commands[-1], ['mount', '-o', 'remount,ro', '/'])
        self.assertEqual([call.args[0] for call in makedirs.call_args_list],
                         ['/var/tmp', '/dev/shm', '/run/lock'])
        self.assertTrue(all(call.kwargs['check'] for call in run.call_args_list))

    def test_invalid_quota_and_mount_failure_fail_closed(self):
        for value in (True, 0, 33 * 1024 * 1024):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _prepare_writable_space({'writable_disk_bytes': value})
        with patch('sandbox.guest_runtime.subprocess.run',
                   side_effect=subprocess.CalledProcessError(1, 'mount')):
            with self.assertRaises(subprocess.CalledProcessError):
                _prepare_writable_space({'writable_disk_bytes': 32 * 1024 * 1024})

    def test_backend_rejects_policy_above_disk_ceiling(self):
        policy = dict(FirecrackerBackend().policy)
        policy['writable_disk_bytes'] = 33 * 1024 * 1024
        with self.assertRaisesRegex(ValueError, 'resource policy'):
            FirecrackerBackend(policy=policy)


if __name__ == '__main__':
    unittest.main()

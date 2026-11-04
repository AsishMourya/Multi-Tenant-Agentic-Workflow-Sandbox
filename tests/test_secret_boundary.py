import unittest

from sandbox.process_env import safe_firecracker_env


class SecretBoundaryTests(unittest.TestCase):
    def test_firecracker_process_does_not_inherit_controller_secrets(self):
        dummy = 'DUMMY_UPSTREAM_CANARY_NOT_A_REAL_SECRET'
        environment = {'PATH': '/safe/bin', 'PLATFORM_TOKEN': dummy,
                       'AWS_SECRET_ACCESS_KEY': dummy}
        clean = safe_firecracker_env(environment)
        self.assertEqual(clean, {'PATH': '/safe/bin', 'LANG': 'C', 'LC_ALL': 'C'})
        self.assertNotIn(dummy, repr(clean))
        self.assertNotIn('PLATFORM_TOKEN', clean)


if __name__ == '__main__':
    unittest.main()

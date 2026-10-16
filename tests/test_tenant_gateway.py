import tempfile
import unittest
from pathlib import Path

from sandbox.platform import Platform
from sandbox.tenant_gateway import TenantGateway


class TenantGatewayTests(unittest.TestCase):
    def test_token_derives_owner_for_create_status_and_delete(self):
        with tempfile.TemporaryDirectory() as root:
            platform = Platform(Path(root) / 'platform')
            gateway = TenantGateway(platform, {'tenant-a': 'a' * 32,
                                               'tenant-b': 'b' * 32})
            try:
                session = gateway.create('a' * 32, 'orders-cents')
                self.assertEqual(gateway.status('a' * 32, session)['state'], 'running')
                with self.assertRaises(PermissionError):
                    gateway.status('b' * 32, session)
                with self.assertRaises(PermissionError):
                    gateway.status('wrong', session)
                with self.assertRaises(ValueError):
                    gateway.delete('a' * 32, session)
            finally:
                platform.close()


if __name__ == '__main__':
    unittest.main()

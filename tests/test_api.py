import json
import tempfile
import unittest
from pathlib import Path

from exercises.python.reference import solve
from sandbox.api import SandboxService, bearer
from sandbox.platform import Platform
from sandbox.tenant_gateway import TenantGateway


class Backend:
    def run_python(self, _tenant, _session, _source, payload):
        return {'status': 'ok', 'stdout': json.dumps(solve(payload)), 'stderr': '', 'exit_code': 0}


class ApiTests(unittest.TestCase):
    def test_bearer_and_service_never_accept_client_tenant_or_judgments(self):
        with tempfile.TemporaryDirectory() as directory:
            platform = Platform(Path(directory) / 'platform', backend=Backend())
            try:
                gateway = TenantGateway(platform, {'learner-1': 'a' * 32, 'learner-2': 'b' * 32})
                service = SandboxService(gateway)
                session = service.create('a' * 32, {'exercise': 'orders-cents', 'tenant': 'learner-2'})['session']
                self.assertTrue(session.startswith('learner-1-'))
                result = service.submit_python('a' * 32, session, {
                    'source': 'print(1)', 'payload': [],
                    'judges': [{'score': 100}], 'tenant': 'learner-2'})
                self.assertEqual(result['grade']['status'], 'REVIEW')
                with self.assertRaises(PermissionError):
                    service.status('b' * 32, session)
            finally:
                platform.close()

    def test_bearer_parser_rejects_missing_or_malformed_values(self):
        self.assertEqual(bearer({'Authorization': 'Bearer token'}), 'token')
        for value in ('', 'token', 'Bearer '):
            with self.assertRaises(PermissionError):
                bearer({'Authorization': value})


if __name__ == '__main__':
    unittest.main()

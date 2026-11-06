import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from exercises.python.reference import solve
from sandbox.api import SandboxService, bearer, handler_for
from sandbox.platform import Platform
from sandbox.tenant_gateway import TenantGateway


class Backend:
    def run_python(self, _tenant, _session, _source, payload):
        return {'status': 'ok', 'stdout': json.dumps(solve(payload)), 'stderr': '', 'exit_code': 0}

    def run_workflow(self, _tenant, _session, _source, payload, broker_call,
                     on_pause, on_resume):
        request = {'operation': 'inventory.lookup', 'args': {'sku': payload['sku']},
                   'request': 'lookup-1'}
        result = broker_call(request)
        on_pause({'schema': 'test-snapshot'})
        on_resume()
        broker_call(request)
        output = {'sku': payload['sku'], 'quantity': payload['quantity'],
                  'available': result['available'],
                  'accepted': payload['quantity'] <= result['available'],
                  'explanation': f"Requested {payload['quantity']}; available "
                  f"{result['available']}; accepted {payload['quantity'] <= result['available']}."}
        return {'status': 'ok', 'stdout': json.dumps(output), 'stderr': '',
                'exit_code': 0, 'snapshot': {'restored': True}}


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


    def test_http_dashboard_and_authenticated_session_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            platform = Platform(Path(directory) / 'platform', backend=Backend())
            gateway = TenantGateway(
                platform, {'learner-1': 'a' * 32, 'learner-2': 'b' * 32})
            server = ThreadingHTTPServer(
                ('127.0.0.1', 0), handler_for(SandboxService(gateway)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f'http://127.0.0.1:{server.server_port}'

            def request(path, *, token=None, method='GET', body=None):
                headers = {}
                if token is not None:
                    headers['Authorization'] = f'Bearer {token}'
                data = None if body is None else json.dumps(body).encode()
                if data is not None:
                    headers['Content-Type'] = 'application/json'
                req = urllib.request.Request(base_url + path, data=data,
                                             headers=headers, method=method)
                try:
                    with urllib.request.urlopen(req, timeout=3) as response:
                        return response.status, response.read()
                except urllib.error.HTTPError as error:
                    return error.code, error.read()

            try:
                status, page = request('/')
                self.assertEqual(status, 200)
                self.assertIn(b'Sandbox Studio', page)
                self.assertIn(b'id="root"', page)
                script = re.search(rb'<script[^>]+src="([^"]+\.js)"', page)
                if script:
                    status, bundle = request(script.group(1).decode())
                    self.assertEqual(status, 200)
                    self.assertTrue(bundle)

                status, raw = request('/v1/sessions', token='a' * 32, method='POST',
                                      body={'exercise': 'orders-cents',
                                            'tenant': 'learner-2'})
                self.assertEqual(status, 201)
                session = json.loads(raw)['session']
                self.assertTrue(session.startswith('learner-1-'))

                status, raw = request(
                    f'/v1/sessions/{session}/python', token='a' * 32, method='POST',
                    body={'source': 'print(1)', 'payload': [
                        {'sku': 'apple', 'quantity': 2, 'unit_cents': 125}],
                        'tenant': 'learner-2'})
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(raw)['output']['total_cents'], 250)

                status, raw = request('/v1/sessions', token='b' * 32, method='POST',
                                      body={'exercise': 'inventory'})
                self.assertEqual(status, 201)
                agent_session = json.loads(raw)['session']
                status, raw = request(
                    f'/v1/sessions/{agent_session}/agent', token='b' * 32,
                    method='POST', body={
                        'source': 'untrusted source',
                        'payload': {'sku': 'apple', 'quantity': 2}})
                self.assertEqual(status, 200)
                self.assertTrue(json.loads(raw)['output']['accepted'])

                status, raw = request(f'/v1/sessions/{session}', token='b' * 32)
                self.assertEqual(status, 403)
                self.assertIn(b'error', raw)
            finally:
                server.shutdown()
                thread.join(timeout=3)
                server.server_close()
                platform.close()


if __name__ == '__main__':
    unittest.main()

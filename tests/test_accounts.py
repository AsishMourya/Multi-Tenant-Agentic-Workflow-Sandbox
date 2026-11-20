import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from sandbox.api import SandboxService, handler_for
from sandbox.auth import LocalAuth
from sandbox.platform import Platform
from sandbox.tenant_gateway import TenantGateway
from tests.test_isolated_submission import RecordingBackend


class AccountTests(unittest.TestCase):
    def test_account_cookie_history_logout_and_tenant_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            platform = Platform(Path(root) / 'platform', backend=RecordingBackend())
            auth = LocalAuth(Path(root) / 'accounts.db')
            gateway = TenantGateway(platform, {'tenant-a': 'a' * 32})
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(SandboxService(gateway, auth=auth)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def request(path, body=None, method=None):
                data = None if body is None else json.dumps(body).encode()
                req = urllib.request.Request(base + path, data=data, method=method,
                                             headers={'Content-Type': 'application/json'})
                with browser.open(req, timeout=5) as response:
                    return json.loads(response.read()), response.headers
            try:
                user, headers = request('/v1/auth/register', {'username': 'alice', 'password': 'alice-password-123'})
                self.assertEqual(user['username'], 'alice')
                self.assertIn('HttpOnly', headers['Set-Cookie'])
                self.assertIn('SameSite=Strict', headers['Set-Cookie'])
                identity, _ = request('/v1/auth/me')
                self.assertTrue(identity['tenant'].startswith('tenant-'))
                created, _ = request('/v1/sessions', {'exercise': 'orders-cents'})
                sid = created['session']
                result, _ = request(f'/v1/sessions/{sid}/python', {'source': 'source', 'payload': []})
                history, _ = request('/v1/sessions')
                self.assertEqual(history['sessions'][0]['session'], sid)
                saved, _ = request(f'/v1/sessions/{sid}')
                self.assertEqual(saved['result'], result)
                request('/v1/auth/logout', {})
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    request('/v1/sessions')
                self.assertEqual(denied.exception.code, 403)
                request('/v1/auth/register', {'username': 'bob', 'password': 'bob-password-123'})
                history, _ = request('/v1/sessions')
                self.assertEqual(history['sessions'], [])
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    request(f'/v1/sessions/{sid}')
                self.assertEqual(denied.exception.code, 403)
                request('/v1/auth/login', {'username': 'alice', 'password': 'alice-password-123'})
                request(f'/v1/sessions/{sid}', method='DELETE')
                history, _ = request('/v1/sessions')
                self.assertEqual(history['sessions'], [])
            finally:
                server.shutdown(); server.server_close(); thread.join()
                auth.db.close(); platform.close()

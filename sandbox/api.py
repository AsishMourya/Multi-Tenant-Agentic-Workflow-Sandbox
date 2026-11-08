"""Small authenticated JSON API for the single-machine sandbox control plane.

It intentionally accepts no tenant field and no client-supplied semantic grades.
Transport is stdlib-only so the service can run from a clean checkout.
"""
import json
import mimetypes
import traceback
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def bearer(headers):
    value = headers.get('Authorization', '')
    prefix = 'Bearer '
    if not value.startswith(prefix) or not value[len(prefix):]:
        raise PermissionError('bearer credential required')
    return value[len(prefix):]


class SandboxService:
    def __init__(self, gateway, *, judge_provider=None, auth=None):
        self.gateway = gateway
        # Server-owned provider only. Browser payloads never influence it.
        self.judge_provider = judge_provider
        self.auth = auth

    def sign_up(self, body):
        if self.auth is None:
            raise RuntimeError('local registration is unavailable')
        token, tenant, _ = self.auth.register(body['username'], body['password'])
        self.gateway.bind_browser_session(tenant, token)
        return token, {'username': body['username']}

    def sign_in(self, body):
        if self.auth is None:
            raise RuntimeError('local sign-in is unavailable')
        token, tenant, _ = self.auth.login(body['username'], body['password'])
        self.gateway.bind_browser_session(tenant, token)
        return token, {'username': body['username']}

    def cookie_credential(self, header):
        if self.auth is None:
            raise PermissionError('bearer credential required')
        cookies = SimpleCookie(); cookies.load(header or '')
        morsel = cookies.get('sandbox_session')
        if morsel is None:
            raise PermissionError('sign in required')
        token = morsel.value
        tenant = self.auth.tenant_for(token)
        self.gateway.bind_browser_session(tenant, token)
        return token

    def create(self, credential, body):
        return {'session': self.gateway.create(credential, body['exercise'])}

    def status(self, credential, session):
        return self.gateway.status(credential, session)

    def delete(self, credential, session):
        self.gateway.delete(credential, session)
        return {'deleted': session}

    def submit_python(self, credential, session, body):
        return self.gateway.submit_python(credential, session, body['source'], body['payload'],
                                          self.judge_provider or (),
                                          pause_resume=bool(body.get('pause_resume', False)))

    def submit_agent(self, credential, session, body):
        return self.gateway.submit_workflow(credential, session, body['source'], body['payload'],
                                            self.judge_provider or ())

    def pause(self, credential, session, body):
        return self.gateway.pause(credential, session, body['payload'])

    def resume(self, credential, session):
        output, trace = self.gateway.resume(credential, session)
        return {'output': output, 'trace': trace}


def handler_for(service):
    static_root = Path(__file__).resolve().parents[1] / 'web' / 'dist'
    class Handler(BaseHTTPRequestHandler):
        def _body(self):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 131072:
                raise ValueError('invalid request size')
            return json.loads(self.rfile.read(length))

        def _send(self, status, data, headers=None):
            encoded = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)

        def _send_html(self, content):
            self._send_bytes(HTTPStatus.OK, content.encode('utf-8'),
                             'text/html; charset=utf-8')

        def _send_bytes(self, status, encoded, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(encoded)

        def _static(self):
            requested = unquote(urlsplit(self.path).path)
            root = static_root.resolve()
            candidate = (root / 'index.html' if requested == '/' else
                         (root / requested.lstrip('/')).resolve())
            try:
                candidate.relative_to(root)
            except ValueError:
                return self._send(HTTPStatus.NOT_FOUND, {'error': 'not found'})
            if candidate.is_file():
                content_type = mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
                if content_type == 'text/html':
                    content_type += '; charset=utf-8'
                return self._send_bytes(HTTPStatus.OK, candidate.read_bytes(), content_type)
            if requested == '/' and not (root / 'index.html').is_file():
                return self._send_html(
                    '<!doctype html><meta charset="utf-8"><title>Sandbox Studio setup</title>'
                    '<div id="root"></div><h1>Sandbox Studio is not built yet</h1>'
                    '<p>From the WSL repository directory, run <code>./start-demo.sh</code>.</p>')
            return self._send(HTTPStatus.NOT_FOUND, {'error': 'not found'})

        def _dispatch(self):
            parts = self.path.strip('/').split('/')
            if self.command == 'POST' and parts == ['v1', 'auth', 'register']:
                token, result = service.sign_up(self._body())
                return HTTPStatus.CREATED, result, token
            if self.command == 'POST' and parts == ['v1', 'auth', 'login']:
                token, result = service.sign_in(self._body())
                return HTTPStatus.OK, result, token
            try:
                credential = bearer(self.headers)
            except PermissionError:
                credential = service.cookie_credential(self.headers.get('Cookie'))
            if self.command == 'POST' and parts == ['v1', 'sessions']:
                return HTTPStatus.CREATED, service.create(credential, self._body())
            if len(parts) >= 3 and parts[:2] == ['v1', 'sessions']:
                session = parts[2]
                if self.command == 'GET' and len(parts) == 3:
                    return HTTPStatus.OK, service.status(credential, session)
                if self.command == 'DELETE' and len(parts) == 3:
                    return HTTPStatus.OK, service.delete(credential, session)
                if self.command == 'POST' and parts[3:] == ['python']:
                    return HTTPStatus.OK, service.submit_python(credential, session, self._body())
                if self.command == 'POST' and parts[3:] == ['agent']:
                    return HTTPStatus.OK, service.submit_agent(credential, session, self._body())
                if self.command == 'POST' and parts[3:] == ['pause']:
                    return HTTPStatus.OK, service.pause(credential, session, self._body())
                if self.command == 'POST' and parts[3:] == ['resume']:
                    return HTTPStatus.OK, service.resume(credential, session)
            raise ValueError('unknown endpoint')

        def _handle(self):
            try:
                if self.command == 'GET' and not urlsplit(self.path).path.startswith('/v1/'):
                    return self._static()
                dispatched = self._dispatch()
                if len(dispatched) == 3:
                    status, result, token = dispatched
                    return self._send(status, result, {'Set-Cookie':
                        f'sandbox_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'})
                status, result = dispatched
                self._send(status, result)
            except PermissionError as exc:
                self._send(HTTPStatus.FORBIDDEN, {'error': str(exc)})
            except (KeyError, TypeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {'error': str(exc)})
            except RuntimeError as exc:
                self._send(HTTPStatus.CONFLICT, {'error': str(exc)})
            except Exception:
                # A backend failure must be observable to the browser as an
                # infrastructure error, not as a dropped connection. Keep the
                # traceback on the trusted server console and avoid exposing
                # host paths or implementation details to learner clients.
                traceback.print_exc()
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR,
                           {'error': 'internal infrastructure error'})

        do_GET = _handle
        do_POST = _handle
        do_DELETE = _handle

        def log_message(self, _format, *_args):
            pass
    return Handler


def serve(service, host='127.0.0.1', port=8080):
    server = ThreadingHTTPServer((host, port), handler_for(service))
    try:
        server.serve_forever()
    finally:
        server.server_close()

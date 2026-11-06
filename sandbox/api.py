"""Small authenticated JSON API for the single-machine sandbox control plane.

It intentionally accepts no tenant field and no client-supplied semantic grades.
Transport is stdlib-only so the service can run from a clean checkout.
"""
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def bearer(headers):
    value = headers.get('Authorization', '')
    prefix = 'Bearer '
    if not value.startswith(prefix) or not value[len(prefix):]:
        raise PermissionError('bearer credential required')
    return value[len(prefix):]


class SandboxService:
    def __init__(self, gateway, *, judge_provider=None):
        self.gateway = gateway
        # Server-owned provider only. Browser payloads never influence it.
        self.judge_provider = judge_provider

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
    dashboard = (Path(__file__).resolve().parents[1] / 'web' / 'index.html')
    class Handler(BaseHTTPRequestHandler):
        def _body(self):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 131072:
                raise ValueError('invalid request size')
            return json.loads(self.rfile.read(length))

        def _send(self, status, data):
            encoded = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_html(self, content):
            encoded = content.encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _dispatch(self):
            credential = bearer(self.headers)
            parts = self.path.strip('/').split('/')
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
                if self.command == 'GET' and self.path == '/':
                    return self._send_html(dashboard.read_text(encoding='utf-8'))
                status, result = self._dispatch()
                self._send(status, result)
            except PermissionError as exc:
                self._send(HTTPStatus.FORBIDDEN, {'error': str(exc)})
            except (KeyError, TypeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {'error': str(exc)})
            except RuntimeError as exc:
                self._send(HTTPStatus.CONFLICT, {'error': str(exc)})

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

"""Trusted entry point inside a disposable Firecracker guest.

The learner owns /tmp/dat_submission.py and its imports. This entry point is
root-owned and runs the learner process as uid 65534 with no guest network.
"""
import base64
import json
import os
import resource
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


SOURCE = '/tmp/dat_submission.py'
INPUT = '/root/dat_input.json'
CONFIG = '/root/dat_config.json'
BROKER_SOCKET = '/tmp/dat-broker.sock'
CHECKPOINT_SOCKET = '/tmp/dat-checkpoint.sock'


def _limits(settings):
    os.setsid()
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (settings['cpu_seconds'],) * 2)
    resource.setrlimit(resource.RLIMIT_AS, (settings['address_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_NPROC, (settings['processes'],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (settings['output_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _broker_once(settings):
    path = Path(BROKER_SOCKET)
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    path.chmod(0o666)
    server.listen(1)
    server.settimeout(settings['wall_seconds'])

    def serve():
        try:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(settings['wall_seconds'])
                message = bytearray()
                while b'\n' not in message:
                    chunk = connection.recv(4096)
                    if not chunk or len(message) + len(chunk) > 4096:
                        raise ValueError('broker request too large or incomplete')
                    message.extend(chunk)
                request = json.loads(bytes(message).split(b'\n', 1)[0])
                encoded = base64.b64encode(json.dumps(request).encode()).decode()
                nonce = settings['nonce']
                print('DAT_BROKER:' + nonce + ':' + encoded, flush=True)
                print('DAT_BROKER_END:' + nonce, flush=True)
                reply = input().strip()
                prefix = 'DAT_BROKER_REPLY:' + nonce + ':'
                if not reply.startswith(prefix):
                    raise ValueError('broker reply marker mismatch')
                response = base64.b64decode(reply[len(prefix):], validate=True)
                connection.sendall(response + b'\n')
        except (OSError, ValueError, EOFError):
            pass
        finally:
            server.close()
            path.unlink(missing_ok=True)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return thread


def _checkpoint_once(settings):
    path = Path(CHECKPOINT_SOCKET)
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    path.chmod(0o666)
    server.listen(1)
    server.settimeout(settings['wall_seconds'] + 30)

    def serve():
        try:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(settings['wall_seconds'] + 30)
                request = bytearray()
                while b'\n' not in request and len(request) <= 64:
                    chunk = connection.recv(64)
                    if not chunk:
                        break
                    request.extend(chunk)
                if bytes(request).split(b'\n', 1)[0] != b'ready':
                    raise ValueError('invalid checkpoint request')
                os.sync()
                nonce = settings['nonce']
                print('DAT_CHECKPOINT_READY:' + nonce, flush=True)
                if input().strip() != 'DAT_CONTINUE:' + nonce:
                    raise ValueError('invalid continuation marker')
                connection.sendall(b'continue\n')
        except (OSError, ValueError, EOFError):
            pass
        finally:
            server.close()
            path.unlink(missing_ok=True)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return thread


def execute(settings, payload):
    started = time.monotonic()
    broker_thread = _broker_once(settings) if settings.get('mode') == 'workflow' else None
    checkpoint_thread = _checkpoint_once(settings) if settings.get('checkpoint_enabled') else None
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        child = subprocess.Popen(
            [sys.executable, SOURCE], stdin=subprocess.PIPE,
            stdout=stdout, stderr=stderr, cwd='/tmp',
            preexec_fn=lambda: _limits(settings),
        )
        try:
            child.communicate(json.dumps(payload).encode(), timeout=settings['wall_seconds'])
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read(settings['output_bytes'] + 1)
        err = stderr.read(settings['output_bytes'] + 1)
    exceeded = len(out) >= settings['output_bytes'] or len(err) >= settings['output_bytes']
    if broker_thread is not None:
        broker_thread.join(timeout=0.1)
    if checkpoint_thread is not None:
        checkpoint_thread.join(timeout=0.1)
    result = {'exit_code': child.returncode, 'wall_seconds': round(time.monotonic() - started, 3),
              'stdout': out.decode('utf-8', errors='replace'),
              'stderr': err.decode('utf-8', errors='replace')}
    if timed_out:
        result['status'] = 'timeout'
    elif exceeded:
        result['status'] = 'output_limit'
    elif child.returncode:
        result['status'] = 'error'
    else:
        result['status'] = 'ok'
    return result


def main():
    settings = json.loads(Path(CONFIG).read_text(encoding='utf-8'))
    payload = json.loads(Path(INPUT).read_text(encoding='utf-8'))
    result = execute(settings, payload)
    encoded = base64.b64encode(json.dumps(result, separators=(',', ':')).encode()).decode()
    nonce = settings['nonce']
    print('DAT_RESULT:' + nonce + ':' + encoded, flush=True)
    print('DAT_RESULT_END:' + nonce, flush=True)


if __name__ == '__main__':
    main()

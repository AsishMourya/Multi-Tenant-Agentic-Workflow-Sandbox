"""Declared safe point for supported full-VM pause and resume cases."""
import socket


def checkpoint():
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(120)
        connection.connect('/tmp/dat-checkpoint.sock')
        connection.sendall(b'ready\n')
        response = bytearray()
        while b'\n' not in response and len(response) <= 64:
            chunk = connection.recv(64)
            if not chunk:
                break
            response.extend(chunk)
        if bytes(response).split(b'\n', 1)[0] != b'continue':
            raise RuntimeError('checkpoint continuation denied')

"""Learner-visible client for the single scoped inventory lookup."""
import json
import socket

from guest_checkpoint_client import checkpoint


def lookup(sku, request='lookup-1'):
    message = {'operation': 'inventory.lookup', 'args': {'sku': sku}, 'request': request}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(15)
        connection.connect('/tmp/dat-broker.sock')
        connection.sendall((json.dumps(message) + '\n').encode())
        chunks = bytearray()
        while b'\n' not in chunks:
            chunk = connection.recv(4096)
            if not chunk or len(chunks) + len(chunk) > 4096:
                raise RuntimeError('broker response unavailable')
            chunks.extend(chunk)
    result = json.loads(bytes(chunks).split(b'\n', 1)[0])
    if 'error' in result:
        raise PermissionError('broker request denied')
    checkpoint()
    return result

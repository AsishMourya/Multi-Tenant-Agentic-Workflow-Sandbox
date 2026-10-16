"""Small Unix-socket client for the pinned local Firecracker feasibility spike."""
import argparse
import http.client
import json
import socket


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=10)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def request(socket_path, method, route, payload=None):
    connection = UnixHTTPConnection(socket_path)
    body = None if payload is None else json.dumps(payload)
    headers = {'Content-Type': 'application/json'} if body else {}
    connection.request(method, route, body=body, headers=headers)
    response = connection.getresponse()
    text = response.read().decode('utf-8', errors='replace')
    connection.close()
    print(json.dumps({'status': response.status, 'body': text, 'route': route}))
    if not 200 <= response.status < 300:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('status', 'pause', 'resume', 'snapshot', 'load'))
    parser.add_argument('--socket', default='/root/dat-backend/firecracker.sock')
    parser.add_argument('--snapshot-dir', default='/root/dat-backend/snapshot')
    args = parser.parse_args()
    if args.action == 'status':
        request(args.socket, 'GET', '/')
    elif args.action in ('pause', 'resume'):
        request(args.socket, 'PATCH', '/vm', {'state': args.action.capitalize() + 'd' if args.action == 'pause' else 'Resumed'})
    elif args.action == 'snapshot':
        request(args.socket, 'PUT', '/snapshot/create', {
            'snapshot_type': 'Full',
            'snapshot_path': args.snapshot_dir + '/machine.vmstate',
            'mem_file_path': args.snapshot_dir + '/memory.mem',
        })
    else:
        request(args.socket, 'PUT', '/snapshot/load', {
            'snapshot_path': args.snapshot_dir + '/machine.vmstate',
            'mem_backend': {'backend_type': 'File',
                            'backend_path': args.snapshot_dir + '/memory.mem'},
            'track_dirty_pages': False,
            'resume_vm': True,
        })

"""Observe denied guest access at owned local destinations, with benign controls."""
import argparse
import json
import socket
import socketserver
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.firecracker_backend import FirecrackerBackend
from scripts.firecracker_resource_probe import _timed_run


class TCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.observed.set()
        self.request.sendall(b'observed')


class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.observed.set()
        self.request[1].sendto(b'observed', self.client_address)


class IPv6Server(socketserver.TCPServer):
    address_family = socket.AF_INET6


def probe(backend, name, family, datagram=False):
    address = '::1' if family == socket.AF_INET6 else '127.0.0.1'
    server_type = socketserver.UDPServer if datagram else (IPv6Server if family == socket.AF_INET6 else socketserver.TCPServer)
    with server_type((address, 0), UDPHandler if datagram else TCPHandler) as server:
        server.observed = threading.Event()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with socket.socket(family, socket.SOCK_DGRAM if datagram else socket.SOCK_STREAM) as control:
                control.settimeout(2)
                control.connect((address, port))
                if datagram:
                    control.send(b'owned-local-observer-control')
                control.recv(64)
            positive = server.observed.wait(2)
            server.observed.clear()
            source = ('import socket, json\nblocked=False\n'
                      f's=socket.socket({int(family)}, {int(socket.SOCK_DGRAM if datagram else socket.SOCK_STREAM)})\n'
                      's.settimeout(2)\ntry:\n'
                      f'    s.connect(({address!r}, {port}))\n'
                      + ('    s.send(b"\\x12\\x34\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00")\n' if datagram else '')
                      + '    s.recv(64)\nexcept OSError:\n    blocked=True\nfinally:\n    s.close()\n'
                      'print(json.dumps({"blocked": blocked}))\n')
            with ThreadPoolExecutor(max_workers=2) as pool:
                attack = pool.submit(_timed_run, backend, 'network-tenant-a', name, source)
                benign = pool.submit(_timed_run, backend, 'network-tenant-b', name + '-control',
                                     'import json,time\ntime.sleep(2)\nprint(json.dumps({"value":42}))\n')
                attack, benign = attack.result(), benign.result()
            result = attack['result']
            overlap = max(attack['start_monotonic'], benign['start_monotonic']) < min(attack['end_monotonic'], benign['end_monotonic'])
            checks = {'guest_denied': result.get('status') == 'ok' and json.loads(result['stdout']) == {'blocked': True},
                      'observer_positive_control': positive,
                      'destination_observed_no_guest_traffic': not server.observed.is_set(),
                      'benign_passed': benign['result'].get('status') == 'ok' and json.loads(benign['result']['stdout']) == {'value': 42},
                      'overlapped': overlap}
            return {'destination': {'address': address, 'port': port, 'transport': 'UDP' if datagram else 'TCP'},
                    'checks': checks, 'attack': attack, 'benign': benign, 'all_pass': all(checks.values())}
        finally:
            server.shutdown()
            thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    backend = FirecrackerBackend(args.root)
    results = {}
    for name, family, udp in [('NET-01', socket.AF_INET, False), ('NET-02', socket.AF_INET6, False), ('NET-03', socket.AF_INET, True)]:
        try:
            results[name] = probe(backend, name, family, udp)
        except Exception as exc:
            results[name] = {'all_pass': False, 'error': f'{type(exc).__name__}: {exc}'}
    report = {'at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'host-local IPv4/IPv6 TCP and UDP DNS-formatted probes; not universal egress proof',
              'results': results, 'all_pass': all(value['all_pass'] for value in results.values())}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'all_pass': report['all_pass'], 'checks': {key: value.get('checks', value) for key, value in results.items()}}))
    return 0 if report['all_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

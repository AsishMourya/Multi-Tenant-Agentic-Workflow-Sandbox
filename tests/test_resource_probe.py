import json
import threading
import unittest

from scripts.firecracker_resource_probe import concurrent_benign_probe


class ConcurrentProbeBackend:
    def __init__(self):
        self.attack_started = threading.Event()
        self.control_started = threading.Event()

    def run_python(self, tenant, _session, _source, _payload):
        if tenant == 'tenant-a':
            self.attack_started.set()
            if not self.control_started.wait(timeout=2):
                raise TimeoutError('benign control did not start')
            return {'status': 'error', 'exit_code': -24, 'stdout': '', 'stderr': ''}
        self.control_started.set()
        if not self.attack_started.wait(timeout=2):
            raise TimeoutError('CPU attack did not start')
        return {'status': 'ok', 'stdout': json.dumps({'value': 42}), 'stderr': ''}


class ResourceProbeTests(unittest.TestCase):
    def test_concurrent_probe_requires_bounded_attack_and_successful_control(self):
        backend = ConcurrentProbeBackend()
        result = concurrent_benign_probe(backend, backend)

        self.assertTrue(result['all_pass'])
        self.assertTrue(result['overlapped'])
        self.assertEqual(result['checks'], {
            'cpu_limit_enforced': True,
            'attack_bounded': True,
            'benign_control_ok': True,
            'runs_overlapped': True,
        })


if __name__ == '__main__':
    unittest.main()

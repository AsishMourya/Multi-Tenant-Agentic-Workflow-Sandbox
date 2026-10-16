import json
import tempfile
import unittest
from pathlib import Path

from exercises.python.reference import solve
from sandbox.firecracker_backend import BackendUnavailable
from sandbox.platform import Platform


class RecordingBackend:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def run_python(self, *args):
        self.calls.append(args)
        return {'status': 'ok', 'stdout': json.dumps(self.output), 'stderr': '', 'exit_code': 0}


class WorkflowBackend:
    def run_workflow(self, tenant, session, source, payload, broker_call,
                     on_pause, on_resume):
        request = {'operation': 'inventory.lookup', 'args': {'sku': payload['sku']},
                   'request': 'lookup-1'}
        result = broker_call(request)
        on_pause({'schema': 'test-full-snapshot'})
        try:
            broker_call(request)
        except PermissionError:
            self.stale_denied = True
        else:
            self.stale_denied = False
        on_resume()
        self.retry_cached = broker_call(request) == result
        accepted = payload['quantity'] <= result['available']
        output = {'accepted': accepted,
                  'explanation': f"Requested {payload['quantity']}; available {result['available']}; accepted {accepted}."}
        return {'status': 'ok', 'stdout': json.dumps(output), 'stderr': '', 'exit_code': 0,
                'snapshot': {'compute_released': True, 'restored': True}}


class PythonCheckpointBackend:
    def __init__(self, output):
        self.output = output

    def run_python(self, tenant, session, source, payload, *, checkpoint,
                   on_pause, on_resume):
        assert checkpoint
        on_pause({'schema': 'test-full-snapshot'})
        on_resume()
        return {'status': 'ok', 'stdout': json.dumps(self.output), 'stderr': '',
                'exit_code': 0, 'snapshot': {'compute_released': True, 'restored': True}}


class UnavailableBackend:
    def run_python(self, *args):
        raise BackendUnavailable('KVM unavailable')

    def run_workflow(self, *args):
        raise BackendUnavailable('KVM unavailable')


def judge():
    return {'criteria': {name: {'level': 4, 'evidence': 'observed', 'reason': 'matches'}
                         for name in ('correctness', 'clarity')},
            'conflicts_with_tests': False, 'confidence': .9}


class IsolatedSubmissionContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.payload = [{'sku': 'apple', 'quantity': 2, 'unit_cents': 125}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_backend_and_owned_session(self):
        platform = Platform(Path(self.tmp.name) / 'platform')
        try:
            session = platform.create_session('tenant-a', 'orders-cents')
            with self.assertRaisesRegex(RuntimeError, 'isolated backend'):
                platform.submit_code('tenant-a', session, 'print(1)', self.payload, [judge(), judge()])
            with self.assertRaises(PermissionError):
                platform.submit_code('tenant-b', session, 'print(1)', self.payload, [judge(), judge()])
        finally:
            platform.close()

    def test_grades_observed_guest_output(self):
        backend = RecordingBackend(solve(self.payload))
        platform = Platform(Path(self.tmp.name) / 'platform', backend=backend)
        try:
            session = platform.create_session('tenant-a', 'orders-cents')
            result = platform.submit_code('tenant-a', session, 'print(1)', self.payload,
                                          [judge(), judge()])
            self.assertEqual(backend.calls[0][:2], ('tenant-a', session))
            self.assertEqual(result['execution']['status'], 'ok')
            self.assertTrue(result['trace'][0]['passed'])
            self.assertEqual(result['grade']['status'], 'PASS')
        finally:
            platform.close()

    def test_workflow_pause_revokes_and_restore_renews(self):
        backend = WorkflowBackend()
        platform = Platform(Path(self.tmp.name) / 'platform', backend=backend)
        try:
            session = platform.create_session('tenant-a', 'inventory')
            result = platform.submit_workflow_code(
                'tenant-a', session, 'source', {'sku': 'apple', 'quantity': 2},
                [judge(), judge()])
            self.assertTrue(backend.stale_denied)
            self.assertTrue(backend.retry_cached)
            self.assertEqual(platform.lifecycle.get('tenant-a', session)['state'], 'completed')
            self.assertEqual(result['grade']['status'], 'PASS')
            self.assertEqual(platform.broker.db.execute(
                'SELECT count(*) FROM calls WHERE session=?', (session,)).fetchone()[0], 1)
        finally:
            platform.close()

    def test_persisted_status_and_delete_keep_owner_boundary(self):
        root = Path(self.tmp.name) / 'platform'
        backend = RecordingBackend(solve(self.payload))
        platform = Platform(root, backend=backend)
        session = platform.create_session('tenant-a', 'orders-cents')
        platform.submit_code('tenant-a', session, 'source', self.payload,
                             [judge(), judge()])
        platform.close()
        restarted = Platform(root)
        try:
            self.assertEqual(restarted.status('tenant-a', session)['result']['output'],
                             solve(self.payload))
            with self.assertRaises(PermissionError):
                restarted.status('tenant-b', session)
            restarted.delete('tenant-a', session)
            with self.assertRaises(PermissionError):
                restarted.status('tenant-a', session)
        finally:
            restarted.close()

    def test_python_checkpoint_lifecycle(self):
        platform = Platform(Path(self.tmp.name) / 'platform',
                            backend=PythonCheckpointBackend(solve(self.payload)))
        try:
            session = platform.create_session('tenant-a', 'orders-cents')
            result = platform.submit_code('tenant-a', session, 'source', self.payload,
                                          [judge(), judge()], pause_resume=True)
            self.assertEqual(platform.lifecycle.get('tenant-a', session)['state'], 'completed')
            self.assertTrue(result['grade']['metrics']['full_vm_snapshot'])
            self.assertEqual(result['grade']['status'], 'PASS')
        finally:
            platform.close()

    def test_backend_failure_is_retry_not_student_failure(self):
        platform = Platform(Path(self.tmp.name) / 'platform',
                            backend=UnavailableBackend())
        try:
            python_session = platform.create_session('tenant-a', 'orders-cents')
            workflow_session = platform.create_session('tenant-b', 'inventory')
            for tenant, session, method, payload in (
                ('tenant-a', python_session, platform.submit_code, self.payload),
                ('tenant-b', workflow_session, platform.submit_workflow_code,
                 {'sku': 'apple', 'quantity': 2}),
            ):
                result = method(tenant, session, 'source', payload, [judge(), judge()])
                self.assertEqual(result['grade']['status'], 'RETRY_ERROR')
                self.assertEqual(result['execution']['status'], 'infrastructure_error')
                self.assertEqual(platform.lifecycle.get(tenant, session)['state'], 'failed')
        finally:
            platform.close()


if __name__ == '__main__':
    unittest.main()

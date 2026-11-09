import importlib.util
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from exercises.python.reference import solve
from sandbox.firecracker_backend import BackendUnavailable
from sandbox.local_judge import JudgeInvalid, JudgeUnavailable
from sandbox.platform import Platform
from exercises.python.daily_revenue.reference import solve as solve_daily_revenue
from sandbox.deterministic_runner import solve_python


class RecordingBackend:
    def __init__(self, output=None):
        self.output = output
        self.calls = []

    def run_python(self, *args):
        self.calls.append(args)
        output = solve(args[3]) if self.output is None else self.output
        return {'status': 'ok', 'stdout': json.dumps(output), 'stderr': '', 'exit_code': 0}


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
        output = {'sku': payload['sku'], 'quantity': payload['quantity'], 'available': result['available'], 'accepted': accepted,
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


class BlockingBackend:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def run_python(self, tenant, session, source, payload, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            if not self.release.wait(timeout=3):
                raise TimeoutError('test backend release was not signalled')
        return {'status': 'ok', 'stdout': json.dumps(solve(payload)),
                'stderr': '', 'exit_code': 0}

class RegistryBackend:
    def run_python(self, _tenant, _session, _source, payload):
        return {'status': 'ok', 'stdout': json.dumps(solve_daily_revenue(payload)),
                'stderr': '', 'exit_code': 0}

    def run_workflow(self, _tenant, _session, source, payload, broker_call,
                     on_pause, on_resume):
        request = {'operation': 'inventory.lookup', 'args': {'sku': payload['sku']},
                   'request': 'lookup-1'}
        available = broker_call(request)['available']
        on_pause({'snapshot': True})
        on_resume()
        broker_call(request)
        exercise = source
        reference_path = (Path(__file__).resolve().parents[1] / 'exercises' / 'workflow'
                          / ('reference.py' if exercise == 'inventory' else exercise)
                          / 'reference.py')
        spec = importlib.util.spec_from_file_location(
            'workflow_' + exercise.replace('-', '_'), reference_path)
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        output = reference.solve(payload, available)
        return {'status': 'ok', 'stdout': json.dumps(output), 'stderr': '', 'exit_code': 0,
                'snapshot': {'compute_released': True, 'restored': True}}


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
        backend = RecordingBackend()
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
        backend = RecordingBackend()
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

    def test_review_decision_survives_controller_restart(self):
        root = Path(self.tmp.name) / 'platform'
        platform = Platform(root, backend=RecordingBackend())
        try:
            session = platform.create_session('tenant-a', 'orders-cents')
            def judgment(level):
                return {'criteria': {name: {'level': level, 'evidence': 'observed', 'reason': 'needs review'}
                                     for name in ('correctness', 'clarity')},
                        'conflicts_with_tests': False, 'confidence': .9}
            result = platform.submit_code('tenant-a', session, 'source', self.payload,
                                          [judgment(4), judgment(1)])
            grade_id = result['grade']['grade_id']
            self.assertEqual(result['grade']['status'], 'REVIEW')
            platform.add_review(grade_id, 'mentor-1', 'PASS', 'reviewed evidence')
        finally:
            platform.close()
        restarted = Platform(root)
        try:
            restored = restarted.status('tenant-a', session)['result']['grade']
            self.assertEqual(restored['review_history'][0]['decision'], 'PASS')
            self.assertEqual(restored['review_history'][0]['reviewer'], 'mentor-1')
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

    def test_concurrent_submissions_for_one_session_execute_once(self):
        backend = BlockingBackend()
        platform = Platform(Path(self.tmp.name) / 'platform', backend=backend)
        try:
            session = platform.create_session('tenant-a', 'orders-cents')
            def submit():
                try:
                    return platform.submit_code('tenant-a', session, 'source',
                                                self.payload, [judge(), judge()])
                except RuntimeError as exc:
                    return exc

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(submit)
                self.assertTrue(backend.started.wait(timeout=3))
                second = pool.submit(submit)
                backend.release.set()
                results = [first.result(timeout=3), second.result(timeout=3)]

            self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
            self.assertEqual(sum(isinstance(result, RuntimeError) for result in results), 1)
            self.assertEqual(backend.calls, 5)
        finally:
            backend.release.set()
            platform.close()

    def test_new_python_and_workflow_exercises_are_registered_and_graded(self):
        platform = Platform(Path(self.tmp.name) / 'platform', backend=RegistryBackend())
        try:
            python_session = platform.create_session('tenant-a', 'daily-revenue')
            daily = {'sales': [{'day': '2026-01-01', 'amount_cents': 125}]}
            python_result = platform.submit_code('tenant-a', python_session, 'student source',
                                                  daily, [judge(), judge()])
            self.assertEqual(python_result['output']['total_cents'], 125)
            self.assertEqual(python_result['grade']['status'], 'PASS')

            cases = [
                ('stock-reorder', {'sku': 'apple', 'target_quantity': 10}),
                ('inventory-brief', {'sku': 'pear', 'quantity': 4}),
                ('order-explainer', {'sku': 'apple', 'quantity': 2, 'unit_cents': 125}),
            ]
            for tenant_index, (exercise, payload) in enumerate(cases):
                tenant = f'tenant-workflow-{tenant_index}'
                session = platform.create_session(tenant, exercise)
                result = platform.submit_workflow_code(tenant, session, exercise, payload,
                                                       [judge(), judge()])
                self.assertEqual(result['grade']['status'], 'PASS', exercise)
                self.assertTrue(result['execution']['snapshot']['restored'])
                self.assertEqual(len(result['trace']), 3)
        finally:
            platform.close()

    def test_judge_infrastructure_failure_records_retry_and_releases_worker(self):
        platform = Platform(Path(self.tmp.name) / 'platform',
                            backend=RecordingBackend())
        try:
            session = platform.create_session('tenant-a', 'orders-cents')

            def unavailable(_evidence):
                raise JudgeUnavailable('local judge unavailable')

            result = platform.submit_code('tenant-a', session, 'source',
                                          self.payload, unavailable)

            self.assertEqual(result['grade']['status'], 'RETRY_ERROR')
            self.assertEqual(result['grade']['metrics']['judge_error'],
                             'local judge unavailable')
            self.assertEqual(platform.lifecycle.get('tenant-a', session)['state'],
                             'completed')
            self.assertTrue(any(check['check'] == 'semantic judge availability'
                                for check in result['trace']))
        finally:
            platform.close()

    def test_invalid_model_answer_enters_review_not_infrastructure_retry(self):
        platform = Platform(Path(self.tmp.name) / 'platform', backend=RecordingBackend())
        try:
            session = platform.create_session('tenant-a', 'orders-cents')

            def malformed(_evidence):
                raise JudgeInvalid('local judge returned invalid rubric')

            result = platform.submit_code('tenant-a', session, 'source',
                                          self.payload, malformed)
            self.assertEqual(result['grade']['status'], 'REVIEW')
            self.assertTrue(any(check['check'] == 'semantic judge response validity'
                                for check in result['trace']))
        finally:
            platform.close()


if __name__ == '__main__':
    unittest.main()

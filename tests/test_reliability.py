import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sandbox.api import SandboxService
from sandbox.auth import LocalAuth
from sandbox.firecracker_backend import BackendUnavailable
from sandbox.platform import Platform
from sandbox.tenant_gateway import TenantGateway
from tests.test_isolated_submission import RecordingBackend
from sandbox.reviews import record_review


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.platform = Platform(Path(self.tmp.name) / 'platform',
                                 backend=RecordingBackend(), worker_capacity=1)

    def tearDown(self):
        self.platform.close()
        self.tmp.cleanup()

    def test_hidden_backend_failure_releases_worker_and_records_retry(self):
        backend = self.platform.backend
        original = backend.run_python
        def fail_hidden(*args):
            if backend.calls:
                raise BackendUnavailable('hidden VM failed')
            return original(*args)
        backend.run_python = fail_hidden
        session = self.platform.create_session('tenant-a', 'orders-cents')
        result = self.platform.submit_code('tenant-a', session, 'source', [], ())
        self.assertEqual(result['grade']['status'], 'RETRY_ERROR')
        self.assertEqual(self.platform.status('tenant-a', session)['state'], 'failed')
        self.assertFalse(self.platform.lifecycle.is_enqueued(session))
        self.platform.backend = RecordingBackend()
        next_session = self.platform.create_session('tenant-b', 'orders-cents')
        result = self.platform.submit_code('tenant-b', next_session, 'source', [], ())
        self.assertEqual(result['execution']['status'], 'ok')

    def test_wrong_endpoint_does_not_consume_worker(self):
        session = self.platform.create_session('tenant-a', 'inventory')
        with self.assertRaises(ValueError):
            self.platform.submit_code('tenant-a', session, 'source', {}, ())
        self.assertEqual(self.platform.status('tenant-a', session)['state'], 'queued')
        self.assertFalse(self.platform.lifecycle.is_enqueued(session))

    def test_execution_evidence_survives_restart(self):
        session = self.platform.create_session('tenant-a', 'orders-cents')
        result = self.platform.submit_code('tenant-a', session, 'source', [], ())
        self.assertEqual(self.platform.status('tenant-a', session)['result'], result)
        self.platform.close()
        self.platform = Platform(Path(self.tmp.name) / 'platform')
        self.assertEqual(self.platform.status('tenant-a', session)['result'], result)
        self.assertEqual(result['grade']['reason'], 'exactly two judgments required')

    def test_expired_browser_token_rejected_as_bearer_after_binding(self):
        auth = LocalAuth(Path(self.tmp.name) / 'auth.sqlite3')
        gateway = TenantGateway(self.platform, {'tenant-a': 'a' * 32})
        service = SandboxService(gateway, auth=auth)
        try:
            token, _ = service.sign_up({'username': 'learner', 'password': 'long-password-123'})
            session = gateway.create(token, 'orders-cents')
            auth.db.execute("UPDATE browser_sessions SET expires_at='2000-01-01T00:00:00+00:00'")
            with self.assertRaises(PermissionError):
                gateway.status(token, session)
        finally:
            auth.db.close()

    def test_unexpected_judge_failure_releases_worker(self):
        session = self.platform.create_session('tenant-a', 'orders-cents')
        def broken(_):
            raise RuntimeError('unexpected provider failure')
        with self.assertRaises(RuntimeError):
            self.platform.submit_code('tenant-a', session, 'source', [], broken)
        self.assertEqual(self.platform.status('tenant-a', session)['state'], 'failed')
        self.assertFalse(self.platform.lifecycle.is_enqueued(session))

    def test_janitor_expires_abandoned_admission_and_preserves_inflight(self):
        abandoned = self.platform.create_session('tenant-a', 'orders-cents')
        self.platform._ensure_admitted('tenant-a', abandoned)
        self.platform.lifecycle.db.execute('UPDATE admission SET expires_at=0')
        self.platform._executing.add(abandoned)
        self.assertEqual(self.platform.reap_expired(), [])
        self.platform._executing.remove(abandoned)
        self.assertEqual(self.platform.reap_expired(), [abandoned])
        self.assertEqual(self.platform.status('tenant-a', abandoned)['state'], 'expired')

    def test_cancel_waiting_session_preserves_owner_boundary(self):
        sid = self.platform.create_session('tenant-a', 'inventory')
        with self.assertRaises(PermissionError):
            self.platform.cancel('tenant-b', sid)
        result = self.platform.cancel('tenant-a', sid)
        self.assertTrue(result['cancelled'])
        self.assertEqual(self.platform.status('tenant-a', sid)['state'], 'failed')
        self.assertEqual(self.platform.list_sessions('tenant-b'), [])
        self.platform.delete('tenant-a', sid)
        self.assertEqual(self.platform.list_sessions('tenant-a'), [])

    def test_resume_respects_worker_capacity_and_keeps_checkpoint_retryable(self):
        paused = self.platform.create_session('tenant-a', 'inventory')
        self.platform.pause('tenant-a', paused, {'sku': 'apple', 'quantity': 1})
        other = self.platform.create_session('tenant-b', 'orders-cents')
        self.platform._ensure_admitted('tenant-b', other)
        with self.assertRaisesRegex(RuntimeError, 'no worker available'):
            self.platform.resume('tenant-a', paused)
        self.assertEqual(self.platform.status('tenant-a', paused)['state'], 'paused')
        self.platform.cancel('tenant-b', other)
        output, trace = self.platform.resume('tenant-a', paused)
        self.assertTrue(output['accepted'])
        self.assertTrue(trace['resumed'])

    def test_vm_snapshot_pause_retains_capacity_until_same_request_restores(self):
        active = self.platform.create_session('tenant-a', 'orders-cents')
        self.platform._ensure_admitted('tenant-a', active)
        current = self.platform.lifecycle.get('tenant-a', active)
        self.platform.lifecycle.transition('tenant-a', active, 'checkpointing', 'p', current['version'])
        current = self.platform.lifecycle.get('tenant-a', active)
        self.platform.lifecycle.transition('tenant-a', active, 'paused', 's', current['version'], durable=True)
        waiting = self.platform.create_session('tenant-b', 'orders-cents')
        with self.assertRaisesRegex(RuntimeError, 'queued for execution'):
            self.platform._ensure_admitted('tenant-b', waiting)

    def test_input_schema_rejected_before_admission(self):
        sid = self.platform.create_session('tenant-a', 'inventory')
        with self.assertRaisesRegex(ValueError, 'invalid exercise input'):
            self.platform.submit_workflow_code('tenant-a', sid, 'source',
                                               {'sku': 'apple', 'quantity': True}, ())
        self.assertFalse(self.platform.lifecycle.is_enqueued(sid))

    def test_api_safe_point_resume_completes_and_releases_worker(self):
        gateway = TenantGateway(self.platform, {'tenant-a': 'a' * 32})
        service = SandboxService(gateway)
        sid = gateway.create('a' * 32, 'inventory')
        service.pause('a' * 32, sid, {'payload': {'sku': 'apple', 'quantity': 2}})
        result = service.resume('a' * 32, sid)
        self.assertEqual(result['state'], 'completed')
        self.assertFalse(self.platform.lifecycle.is_enqueued(sid))

    def test_concurrent_reviews_preserve_both_records_and_machine_grade(self):
        sid = self.platform.create_session('tenant-a', 'orders-cents')
        result = self.platform.submit_code('tenant-a', sid, 'source', [], ())
        grade_id = result['grade']['grade_id']
        def review(name):
            return record_review(self.platform.root / 'platform.sqlite3', grade_id,
                                 name, 'ESCALATE', 'independent test review')
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(review, ['rater-a', 'rater-b']))
        grade = self.platform.status('tenant-a', sid)['result']['grade']
        self.assertEqual(grade['status'], 'REVIEW')
        self.assertEqual({row['reviewer'] for row in grade['review_history']}, {'rater-a', 'rater-b'})


if __name__ == '__main__':
    unittest.main()

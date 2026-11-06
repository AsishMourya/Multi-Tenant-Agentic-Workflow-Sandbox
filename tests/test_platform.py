import tempfile
import unittest
from pathlib import Path

from sandbox.platform import Platform
from sandbox.state import StateStore


def judge(level=4):
    return {'criteria': {name: {'level': level, 'evidence': 'observed', 'reason': 'matches'}
                         for name in ('correctness', 'clarity')},
            'conflicts_with_tests': False, 'confidence': .9}


class PlatformFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.platform = Platform(Path(self.tmp.name) / 'platform')

    def tearDown(self):
        self.platform.close()
        self.tmp.cleanup()

    def test_two_tenant_two_exercise_flow(self):
        orders = self.platform.create_session('tenant-a', 'orders-cents')
        inventory = self.platform.create_session('tenant-b', 'inventory')
        result = self.platform.submit('tenant-a', orders,
                                      [{'sku': 'apple', 'quantity': 2, 'unit_cents': 125}],
                                      [judge(), judge()])
        self.assertEqual(result['output']['total_cents'], 250)
        self.assertEqual(result['grade']['status'], 'PASS')
        result = self.platform.submit('tenant-b', inventory, {'sku': 'apple', 'quantity': 5},
                                      [judge(), judge()])
        self.assertTrue(result['output']['accepted'])
        self.assertTrue(result['trace'][0]['compute_released'])
        self.assertEqual(result['trace'][0]['effects'][0]['available'], 7)
        with self.assertRaises(PermissionError):
            self.platform.submit('tenant-a', inventory, {'sku': 'apple', 'quantity': 1},
                                 [judge(), judge()])

    def test_idle_sessions_do_not_reserve_worker_capacity(self):
        platform = Platform(Path(self.tmp.name) / 'limited', worker_capacity=1,
                            tenant_worker_capacity=1)
        try:
            first = platform.create_session('tenant-a', 'orders-cents')
            second = platform.create_session('tenant-b', 'orders-cents')
            self.assertEqual(platform.lifecycle.get('tenant-a', first)['state'], 'queued')
            self.assertEqual(platform.lifecycle.get('tenant-b', second)['state'], 'queued')
            self.assertEqual(platform.lifecycle.db.execute(
                'SELECT count(*) FROM admission').fetchone()[0], 0)
            result = platform.submit('tenant-a', first, [], [judge(), judge()])
            self.assertEqual(result['grade']['status'], 'PASS')
            self.assertEqual(platform.lifecycle.get('tenant-b', second)['state'], 'queued')
        finally:
            platform.close()

    def test_queued_submission_is_admitted_when_capacity_frees(self):
        platform = Platform(Path(self.tmp.name) / 'queued', worker_capacity=1,
                            tenant_worker_capacity=1)
        try:
            active = platform.create_session('tenant-a', 'orders-cents')
            waiting = platform.create_session('tenant-b', 'orders-cents')
            platform._ensure_admitted('tenant-a', active)
            with self.assertRaisesRegex(RuntimeError, 'queued for execution'):
                platform.submit('tenant-b', waiting, [], [judge(), judge()])
            self.assertEqual(platform.lifecycle.get('tenant-b', waiting)['state'], 'queued')

            current = platform.lifecycle.get('tenant-a', active)
            platform.lifecycle.transition('tenant-a', active, 'completed',
                                          'test-completed', current['version'])
            platform._complete_execution(active)
            self.assertEqual(platform.lifecycle.get('tenant-b', waiting)['state'], 'running')
            result = platform.submit('tenant-b', waiting, [], [judge(), judge()])
            self.assertEqual(result['grade']['status'], 'PASS')
        finally:
            platform.close()

    def test_borderline_grade_is_reviewable(self):
        session = self.platform.create_session('tenant-a', 'orders-cents')
        result = self.platform.submit('tenant-a', session, [], [judge(0), judge(0)])
        self.assertEqual(result['grade']['status'], 'REVIEW')
        reviewed = self.platform.add_review(result['grade']['grade_id'], 'mentor', 'PASS', 'verified')
        self.assertEqual(reviewed['review_history'][0]['reviewer'], 'mentor')

    def test_checkpoint_survives_controller_restart(self):
        session = self.platform.create_session('tenant-b', 'inventory')
        self.platform.pause('tenant-b', session, {'sku': 'pear', 'quantity': 2})
        checkpoint = Path(self.tmp.name) / 'platform' / 'checkpoints' / f'{session}.json'
        self.assertTrue(checkpoint.is_file())
        self.platform.close()
        restarted = Platform(Path(self.tmp.name) / 'platform')
        state = restarted.state.load('tenant-b', session, 'inventory')
        output, trace = restarted.resume('tenant-b', session)
        restarted.close()
        self.assertEqual(state, {'sku': 'pear', 'quantity': 2, 'available': 3})
        self.assertTrue(output['accepted'])
        self.assertTrue(trace['resumed'])
        self.assertTrue(trace['fresh_capability'])

    def test_checkpoint_rejects_foreign_owner_and_schema(self):
        store = StateStore(Path(self.tmp.name) / 'checkpoints')
        store.save('tenant-a', 's1', 'inventory', {'sku': 'apple', 'quantity': 1, 'available': 7})
        with self.assertRaises(ValueError):
            store.load('tenant-b', 's1', 'inventory')

    def test_bad_checkpoint_does_not_renew_access(self):
        import json
        session = self.platform.create_session('tenant-b', 'inventory')
        self.platform.pause('tenant-b', session, {'sku': 'pear', 'quantity': 2})
        checkpoint = Path(self.tmp.name) / 'platform' / 'checkpoints' / f'{session}.json'
        data = json.loads(checkpoint.read_text(encoding='utf-8'))
        data['state']['quantity'] = -1
        checkpoint.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.platform.resume('tenant-b', session)
        self.assertEqual(self.platform.lifecycle.get('tenant-b', session)['state'], 'paused')
        self.assertEqual(self.platform.broker.db.execute(
            'SELECT state FROM sessions WHERE id=?', (session,)).fetchone()[0], 'paused')


if __name__ == '__main__':
    unittest.main()

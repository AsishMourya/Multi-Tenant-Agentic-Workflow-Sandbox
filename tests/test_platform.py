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


if __name__ == '__main__':
    unittest.main()
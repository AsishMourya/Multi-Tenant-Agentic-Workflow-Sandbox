import json
import unittest

from exercises.python.reference import solve
from sandbox.deterministic_runner import CASES, grade_orders_submission


class DeterministicRunnerTests(unittest.TestCase):
    def test_hidden_cases_are_independently_checked(self):
        report = grade_orders_submission(lambda payload: {
            'status': 'ok', 'stdout': json.dumps(solve(payload))})
        self.assertEqual(report['score'], 1)
        self.assertTrue(report['invariants_ok'])
        self.assertEqual(len(report['results'][0]['cases']), len(CASES))

    def test_wrong_or_malformed_guest_output_cannot_claim_a_pass(self):
        report = grade_orders_submission(lambda _payload: {
            'status': 'ok', 'stdout': '{"claimed": "all tests pass"}'})
        self.assertEqual(report['score'], 0)
        self.assertFalse(report['invariants_ok'])


if __name__ == '__main__':
    unittest.main()

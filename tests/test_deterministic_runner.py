import json
import unittest

from exercises.python.reference import solve
from exercises.python.daily_revenue.reference import solve as solve_daily_revenue
from sandbox.deterministic_runner import (CASES, DAILY_REVENUE_CASES,
                                          grade_daily_revenue_submission,
                                          grade_orders_submission)


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

    def test_daily_revenue_hidden_cases(self):
        report = grade_daily_revenue_submission(lambda payload: {
            'status': 'ok', 'stdout': json.dumps(solve_daily_revenue(payload))})
        self.assertEqual(report['manifest']['exercise_id'], 'daily-revenue')
        self.assertEqual(len(report['results']), len(DAILY_REVENUE_CASES))
        self.assertEqual(report['score'], 1)
        self.assertTrue(report['invariants_ok'])


if __name__ == '__main__':
    unittest.main()

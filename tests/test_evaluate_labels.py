import unittest

from scripts.evaluate_labels import evaluate


class EvaluationMetricsTests(unittest.TestCase):
    def test_preserves_rater_disagreement_and_reports_denominators(self):
        report = evaluate({'submissions': [
            {'id': 'a', 'family': 'f1', 'human_ratings': [True, True],
             'adjudicated_correct': True, 'automated_status': 'PASS'},
            {'id': 'b', 'family': 'f2', 'human_ratings': [False, True],
             'adjudicated_correct': False, 'automated_status': 'REVIEW'},
            {'id': 'c', 'family': 'f3', 'human_ratings': [False, False],
             'adjudicated_correct': False, 'automated_status': 'PASS'},
        ]})
        self.assertEqual(report['human_human_disagreement']['numerator'], 1)
        self.assertEqual(report['false_acceptance_rate'],
                         {'numerator': 1, 'denominator': 2, 'rate': .5})
        self.assertEqual(report['automatic_coverage']['numerator'], 2)


if __name__ == '__main__':
    unittest.main()

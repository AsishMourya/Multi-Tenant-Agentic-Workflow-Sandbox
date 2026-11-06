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
        self.assertEqual(report['human_human_agreement'],
                         {'numerator': 2, 'denominator': 3, 'rate': .6667})
        self.assertEqual(report['human_human_disagreement']['numerator'], 1)
        self.assertEqual(report['false_acceptance_rate'],
                         {'numerator': 1, 'denominator': 2, 'rate': .5})
        self.assertEqual(report['automatic_coverage']['numerator'], 2)

    def test_infrastructure_retries_are_reported_separately(self):
        report = evaluate({'submissions': [
            {'id': 'a', 'family': 'f1', 'human_ratings': [True, True],
             'adjudicated_correct': True, 'automated_status': 'PASS'},
            {'id': 'b', 'family': 'f2', 'human_ratings': [False, False],
             'adjudicated_correct': False, 'automated_status': 'RETRY_ERROR'},
            {'id': 'c', 'family': 'f3', 'human_ratings': [True, True],
             'adjudicated_correct': True, 'automated_status': 'FAIL_INVARIANT'},
            {'id': 'd', 'family': 'f4', 'human_ratings': [True, False],
             'adjudicated_correct': True, 'automated_status': 'REVIEW'},
        ]})
        self.assertEqual(report['evaluation_eligible_count'], 3)
        self.assertEqual(report['human_human_agreement'],
                         {'numerator': 3, 'denominator': 4, 'rate': .75})
        self.assertEqual(report['infrastructure_retry_rate'],
                         {'numerator': 1, 'denominator': 4, 'rate': .25})
        self.assertEqual(report['automatic_coverage'],
                         {'numerator': 2, 'denominator': 3, 'rate': .6667})
        self.assertEqual(report['review_rate'],
                         {'numerator': 1, 'denominator': 3, 'rate': .3333})
        self.assertEqual(report['false_rejection_rate'],
                         {'numerator': 1, 'denominator': 3, 'rate': .3333})

    def test_rejects_unknown_automated_status(self):
        with self.assertRaises(ValueError):
            evaluate({'submissions': [{
                'id': 'a', 'family': 'f1', 'human_ratings': [True, True],
                'adjudicated_correct': True, 'automated_status': 'UNKNOWN',
            }]})

    def test_reports_semantic_error_performance_cost_and_bootstrap_metrics(self):
        report = evaluate({'submissions': [
            {'id': 'a', 'family': 'f1', 'human_ratings': [True, True],
             'adjudicated_correct': True, 'automated_status': 'PASS',
             'adjudicated_criteria': {'correctness': 4, 'clarity': 4},
             'automated_criteria': {'correctness': 4, 'clarity': 3},
             'run_metrics': [{'judge_calls': 2, 'end_to_end_latency_ms': 100,
                              'inference_memory_mb': 256, 'cost_usd': .004}]},
            {'id': 'b', 'family': 'f2', 'human_ratings': [False, True],
             'adjudicated_correct': False, 'automated_status': 'REVIEW',
             'adjudicated_criteria': {'correctness': 1, 'clarity': 2},
             'automated_criteria': {'correctness': 2, 'clarity': 2},
             'run_metrics': [{'judge_calls': 4, 'end_to_end_latency_ms': 200,
                              'inference_memory_mb': 512, 'cost_usd': .006}]},
        ]})
        self.assertEqual(report['semantic_mae'], {
            'absolute_error_sum': 2, 'criterion_count': 4,
            'submission_count': 2, 'mae': .5,
        })
        self.assertEqual(report['judge_calls_per_submission'],
                         {'observations': 2, 'mean': 3.0, 'run_count': 2})
        self.assertEqual(report['end_to_end_latency_ms'],
                         {'observations': 2, 'mean': 150, 'run_count': 2})
        self.assertEqual(report['inference_memory_mb'],
                         {'observations': 2, 'mean': 384, 'run_count': 2})
        self.assertEqual(report['cost_usd'],
                         {'observations': 2, 'mean': .005, 'run_count': 2})
        self.assertEqual(report['confidence_intervals_95']['human_human_agreement'],
                         [0, 1])
        self.assertEqual(report['confidence_intervals_95']['semantic_mae'], [.5, .5])

    def test_retry_rows_do_not_enter_semantic_error_metric(self):
        report = evaluate({'submissions': [
            {'id': 'a', 'family': 'f1', 'human_ratings': [True, True],
             'adjudicated_correct': True, 'automated_status': 'RETRY_ERROR',
             'adjudicated_criteria': {'correctness': 4},
             'automated_criteria': {'correctness': 0}},
        ]})
        self.assertEqual(report['semantic_mae'], {
            'absolute_error_sum': 0, 'criterion_count': 0,
            'submission_count': 0, 'mae': None,
        })

    def test_rejects_mismatched_semantic_criteria_and_invalid_run_metrics(self):
        row = {'id': 'a', 'family': 'f1', 'human_ratings': [True, True],
               'adjudicated_correct': True, 'automated_status': 'PASS',
               'adjudicated_criteria': {'correctness': 4},
               'automated_criteria': {'clarity': 4}}
        with self.assertRaises(ValueError):
            evaluate({'submissions': [row]})
        row.pop('adjudicated_criteria')
        row.pop('automated_criteria')
        row['run_metrics'] = [{'cost_usd': -1}]
        with self.assertRaises(ValueError):
            evaluate({'submissions': [row]})


if __name__ == '__main__':
    unittest.main()

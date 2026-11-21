"""The M8 engineering summary is bound to frozen, observed records."""
import unittest
from pathlib import Path

from scripts.build_regression_bank import bank_digest, build_bank
from scripts.prepare_evaluation import prepare_split
from scripts.summarize_runs import summarize
from scripts.build_validation_bank import build_validation_bank


class SummarizeRunsTests(unittest.TestCase):
    def setUp(self):
        self.bank = build_bank(Path(__file__).resolve().parents[1])
        self.split = prepare_split(self.bank)
        self.split['bank_sha256'] = bank_digest(self.bank)
        assignment = self.split['assignments'][0]
        self.row = {'id': assignment['id'], 'repeat': 1, 'split': assignment['split'],
                    'bank_sha256': self.split['bank_sha256'], 'end_to_end_latency_ms': 1234,
                    'result': {'grade': {'status': 'REVIEW', 'metrics': {'judge_runs': [
                        {'latency_ms': 100}, {'latency_ms': 200}]}},
                               'execution': {'snapshot': {'restored': True}}}}

    def test_reports_observed_metrics_but_no_human_accuracy(self):
        report = summarize(self.bank, self.split, [self.row])
        self.assertEqual(report['status_counts'], {'REVIEW': 1})
        self.assertEqual(report['judge_calls'], 2)
        self.assertEqual(report['judge_latency']['p95_ms'], 200)
        self.assertEqual(report['judge_token_usage']['measured_calls'], 0)
        self.assertEqual(report['provisional_score_count'], 0)
        self.assertEqual(report['snapshot_restored'], 1)
        self.assertIsNone(report['human_label_metrics'])

    def test_model_validation_error_is_counted_separately(self):
        self.row['result']['grade']['metrics']['judge_error'] = 'invalid rubric'
        report = summarize(self.bank, self.split, [self.row])
        self.assertEqual(report['judge_error_counts'], {'invalid rubric': 1})

    def test_usage_totals_only_count_measured_calls(self):
        self.row['result']['grade']['metrics']['judge_runs'][0].update(
            {'prompt_tokens': 100, 'completion_tokens': 20, 'resident_bytes': 512})
        report = summarize(self.bank, self.split, [self.row])
        self.assertEqual(report['judge_token_usage'], {
            'measured_calls': 1, 'prompt_tokens': 100, 'completion_tokens': 20})
        self.assertEqual(report['judge_peak_resident_bytes'], 512)

    def test_matched_semantic_score_shift_is_observed_not_accuracy(self):
        bank = build_validation_bank(Path(__file__).resolve().parents[1])
        split = prepare_split(bank, seed='dat-validation-v1')
        split['bank_sha256'] = bank_digest(bank)
        assignments = {row['id']: row for row in split['assignments']}
        runs = []
        for category, score in (('starter', 75), ('adversarial', 80)):
            sid = f'inventory-{category}-1'
            runs.append({'id': sid, 'repeat': 1, 'split': assignments[sid]['split'],
                         'bank_sha256': split['bank_sha256'],
                         'result': {'grade': {'status': 'REVIEW', 'score': score}}})
        report = summarize(bank, split, runs)
        self.assertEqual(report['matched_score_shifts_vs_starter']['adversarial'],
                         {'matched_pairs': 1, 'mean_score_delta': 5})
        self.assertIsNone(report['human_label_metrics'])

    def test_rejects_duplicate_and_wrong_bank(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            summarize(self.bank, self.split, [self.row, self.row])
        self.row['bank_sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'frozen bank'):
            summarize(self.bank, self.split, [self.row])


if __name__ == '__main__':
    unittest.main()

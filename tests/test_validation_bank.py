import unittest
from collections import Counter
from pathlib import Path

from scripts.build_regression_bank import bank_digest
from scripts.build_validation_bank import build_validation_bank
from scripts.prepare_evaluation import prepare_split
from scripts.run_evaluation import validate_bank


class ValidationBankTests(unittest.TestCase):
    def test_candidate_bank_has_semantic_cases_and_frozen_split(self):
        bank = build_validation_bank(Path(__file__).resolve().parents[1])
        split = prepare_split(bank, seed='dat-validation-v1')
        split['bank_sha256'] = bank_digest(bank)
        validate_bank(bank, split)
        self.assertEqual(len(bank['submissions']), 60)
        self.assertEqual((split['calibration_count'], split['held_out_count']), (20, 40))
        categories = Counter(row['construction'] for row in bank['submissions'])
        self.assertEqual(categories['adversarial'], 8)
        self.assertEqual(categories['ambiguous'], 8)
        self.assertEqual(categories['partly-correct'], 12)
        self.assertFalse(any('human_label' in row for row in bank['submissions']))
        for row in bank['submissions']:
            compile(row['source'], row['id'], 'exec')


if __name__ == '__main__':
    unittest.main()

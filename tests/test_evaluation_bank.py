import copy
import unittest
from pathlib import Path

from scripts.build_regression_bank import bank_digest, build_bank
from scripts.prepare_evaluation import prepare_split
from scripts.run_evaluation import validate_bank


class EvaluationBankTests(unittest.TestCase):
    def setUp(self):
        self.bank = build_bank(Path(__file__).resolve().parents[1])
        self.split = prepare_split(self.bank)
        self.split['bank_sha256'] = bank_digest(self.bank)

    def test_complete_synthetic_bank_has_leak_free_frozen_split(self):
        self.assertEqual(len(validate_bank(self.bank, self.split)), 60)
        self.assertEqual(self.split['calibration_count'], 20)
        self.assertEqual(self.split['held_out_count'], 40)
        self.assertEqual(len({row['exercise_id'] for row in self.bank['submissions']}), 6)
        self.assertTrue(all('human_label' not in row for row in self.bank['submissions']))

    def test_modified_code_rejected_after_freeze(self):
        self.bank['submissions'][0]['source'] += '\n# changed'
        with self.assertRaisesRegex(ValueError, 'digest'):
            validate_bank(self.bank, self.split)

    def test_family_leak_rejected(self):
        for row in self.split['assignments']:
            if row['family'] == self.split['assignments'][0]['family']:
                row['split'] = 'held_out'
        self.split['assignments'][0]['split'] = 'calibration'
        with self.assertRaisesRegex(ValueError, 'leaks'):
            validate_bank(self.bank, self.split)

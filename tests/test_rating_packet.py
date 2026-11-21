import unittest
from pathlib import Path

from scripts.build_regression_bank import bank_digest, build_bank
from scripts.prepare_evaluation import prepare_split
from scripts.prepare_rating_packet import make_packet


class RatingPacketTests(unittest.TestCase):
    def setUp(self):
        self.bank = build_bank(Path(__file__).resolve().parents[1])
        self.split = prepare_split(self.bank)
        self.split['bank_sha256'] = bank_digest(self.bank)
        self.runs = [{'id': row['id'], 'repeat': 1,
                      'bank_sha256': self.split['bank_sha256'],
                      'result': {'output': {'example': True}, 'grade': {
                          'status': 'PASS', 'score': 100, 'judgments': ['secret'],
                          'deterministic_results': [{'check': 'example', 'passed': True}]}}}
                     for row in self.bank['submissions']]

    def test_packet_is_model_blind_and_unrated(self):
        packet = make_packet(self.bank, self.split, self.runs, 'rater-a')
        self.assertEqual(len(packet['submissions']), 60)
        first = packet['submissions'][0]
        self.assertEqual(first['ratings'], {'correctness': None, 'clarity': None})
        self.assertIsNone(first['overall_pass'])
        self.assertNotIn('status', first)
        self.assertNotIn('judgments', first)
        self.assertNotIn('split', first)

    def test_incomplete_or_duplicate_runs_rejected(self):
        with self.assertRaisesRegex(ValueError, 'every submission'):
            make_packet(self.bank, self.split, self.runs[:-1], 'rater-a')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            make_packet(self.bank, self.split, self.runs + self.runs[:1], 'rater-a')


if __name__ == '__main__':
    unittest.main()

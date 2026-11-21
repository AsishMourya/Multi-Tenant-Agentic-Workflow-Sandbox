import copy
import json
import unittest
from pathlib import Path

from scripts.assemble_human_evaluation import assemble, make_adjudication_packet
from scripts.evaluate_labels import evaluate


ROOT = Path(__file__).resolve().parents[1]


class AssembleHumanEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = json.loads((ROOT / 'evaluation/validation-bank.json').read_text(encoding='utf-8'))
        cls.split = json.loads((ROOT / 'evaluation/validation-split.json').read_text(encoding='utf-8'))
        cls.runs = [json.loads(line) for line in
                    (ROOT / 'evidence/validation-runs-2026-11-21.jsonl').read_text(encoding='utf-8').splitlines()]

    def packets(self):
        a = json.loads((ROOT / 'evaluation/rater-a.json').read_text(encoding='utf-8'))
        b = json.loads((ROOT / 'evaluation/rater-b.json').read_text(encoding='utf-8'))
        for packet in (a, b):
            for row in packet['submissions']:
                row['ratings'] = {'correctness': 3, 'clarity': 3}
                row['overall_pass'] = True
        return a, b

    def test_refuses_blank_packets(self):
        a, b = self.packets()
        a['submissions'][0]['ratings']['clarity'] = None
        with self.assertRaisesRegex(ValueError, 'missing or invalid'):
            make_adjudication_packet(self.bank, self.split, a, b)

    def test_assembles_only_complete_independent_adjudicated_labels(self):
        a, b = self.packets()
        b['submissions'][0]['ratings']['clarity'] = 2
        b['submissions'][0]['overall_pass'] = False
        adjudication = make_adjudication_packet(self.bank, self.split, a, b)
        self.assertEqual(len(adjudication['disagreements']), 1)
        with self.assertRaisesRegex(ValueError, 'incomplete adjudicated'):
            assemble(self.bank, self.split, a, b, adjudication, self.runs)
        adjudication['disagreements'][0]['adjudicated_ratings'] = {'correctness': 3, 'clarity': 2}
        adjudication['disagreements'][0]['adjudicated_pass'] = False
        adjudication['disagreements'][0]['rationale'] = 'Independent review of the test evidence.'
        labels = assemble(self.bank, self.split, a, b, adjudication, self.runs)
        self.assertEqual(len(labels['submissions']), 60)
        self.assertEqual(labels['submissions'][0]['human_ratings'], [True, False])
        self.assertFalse(labels['submissions'][0]['adjudicated_correct'])
        self.assertIn('human_human_agreement', evaluate(labels))
        altered = copy.deepcopy(adjudication)
        altered['disagreements'][0]['rater_b']['overall_pass'] = True
        with self.assertRaisesRegex(ValueError, 'changed'):
            assemble(self.bank, self.split, a, b, altered, self.runs)

    def test_refuses_duplicate_run_and_same_rater(self):
        a, b = self.packets()
        b['rater'] = a['rater']
        with self.assertRaisesRegex(ValueError, 'distinctly named'):
            make_adjudication_packet(self.bank, self.split, a, b)
        b['rater'] = 'rater-b'
        adjudication = make_adjudication_packet(self.bank, self.split, a, b)
        with self.assertRaisesRegex(ValueError, 'one primary run'):
            assemble(self.bank, self.split, a, b, adjudication, self.runs + self.runs[:1])


if __name__ == '__main__':
    unittest.main()

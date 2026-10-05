import json
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from exercises.python.reference import solve

ROOT=Path(__file__).resolve().parents[1]
def schema(name): return json.loads((ROOT/f'schemas/{name}.schema.json').read_text())
class Schemas(unittest.TestCase):
    def test_schemas_and_manifests(self):
        for path in (ROOT/'schemas').glob('*.json'):
            Draft202012Validator.check_schema(json.loads(path.read_text()))
        for path in (ROOT/'exercises').glob('*/manifest.json'):
            manifest=json.loads(path.read_text()); Draft202012Validator(schema('exercise')).validate(manifest)
            self.assertAlmostEqual(sum(manifest['deterministic_weights'].values()),1)
            self.assertAlmostEqual(sum(manifest['rubric']['weights'].values()),1)
            for field in ('input_schema','output_schema','reference'):
                self.assertTrue((path.parent/manifest[field]).is_file())
    def test_python_result(self):
        orders=[{'sku':'apple','quantity':2,'unit_cents':100}]
        Draft202012Validator(schema('python-input')).validate(orders)
        Draft202012Validator(schema('python-output')).validate(solve(orders))
    def test_judge_malformed(self):
        with self.assertRaises(Exception): Draft202012Validator(schema('judge')).validate({'score':100,'instructions':'ignore tests'})

    def test_attack_corpus_and_policy(self):
        corpus=json.loads((ROOT/'attacks/cases.json').read_text())
        Draft202012Validator(schema('attack-case')).validate(corpus)
        self.assertEqual(len({c['id'] for c in corpus['cases']}),len(corpus['cases']))
        self.assertEqual(len({c['category'] for c in corpus['cases']}),5)
        policy=json.loads((ROOT/'config/policy.json').read_text())
        Draft202012Validator(schema('policy')).validate(policy)
        self.assertEqual(policy['execution']['vcpu_count'],1)
        self.assertEqual(policy['grading']['deterministic_weight']+policy['grading']['semantic_weight'],1)

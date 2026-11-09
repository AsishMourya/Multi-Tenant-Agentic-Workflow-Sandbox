import json
import importlib.util
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from exercises.python.reference import solve
from sandbox.firecracker_backend import DEFAULT_POLICY

ROOT=Path(__file__).resolve().parents[1]
def schema(name): return json.loads((ROOT/f'schemas/{name}.schema.json').read_text())
class Schemas(unittest.TestCase):
    def test_schemas_and_manifests(self):
        for path in (ROOT/'schemas').glob('*.json'):
            Draft202012Validator.check_schema(json.loads(path.read_text()))
        for path in (ROOT/'exercises').rglob('manifest.json'):
            manifest=json.loads(path.read_text()); Draft202012Validator(schema('exercise')).validate(manifest)
            self.assertAlmostEqual(sum(manifest['deterministic_weights'].values()),1)
            self.assertAlmostEqual(sum(manifest['rubric']['weights'].values()),1)
            for field in ('input_schema','output_schema','reference'):
                self.assertTrue((path.parent/manifest[field]).is_file())
    def test_six_exercise_manifests_are_unique(self):
        manifests=[json.loads(path.read_text()) for path in (ROOT/'exercises').rglob('manifest.json')]
        self.assertEqual(len(manifests),6)
        self.assertEqual(len({manifest['exercise_id'] for manifest in manifests}),6)

    def test_additional_reference_outputs(self):
        def load_reference(path):
            spec=importlib.util.spec_from_file_location(path.parent.name+'_reference',path)
            module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            return module
        daily=load_reference(ROOT/'exercises/python/daily_revenue/reference.py')
        self.assertEqual(daily.solve({'sales':[{'day':'2026-01-01','amount_cents':125},
                                               {'day':'2026-01-01','amount_cents':75}]}),
                         {'by_day':{'2026-01-01':200},'total_cents':200})
        reorder=load_reference(ROOT/'exercises/workflow/stock-reorder/reference.py')
        self.assertEqual(reorder.solve({'sku':'apple','target_quantity':10},7)['reorder_quantity'],3)
        brief=load_reference(ROOT/'exercises/workflow/inventory-brief/reference.py')
        self.assertTrue(brief.solve({'sku':'pear','quantity':4},3)['accepted'] is False)
        explainer=load_reference(ROOT/'exercises/workflow/order-explainer/reference.py')
        self.assertEqual(explainer.solve({'sku':'apple','quantity':2,'unit_cents':125},7)['subtotal_cents'],250)
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
        execution=policy['execution']
        self.assertEqual(execution['memory_mib'],512)
        self.assertEqual(execution['cpu_seconds'],15)
        self.assertEqual(execution['address_space_mib'],256)
        self.assertEqual(execution['wall_seconds'],15)
        self.assertEqual(execution['snapshot_wall_seconds'],120)
        self.assertEqual({
            'vcpu_count': execution['vcpu_count'],
            'mem_size_mib': execution['memory_mib'],
            'cpu_seconds': execution['cpu_seconds'],
            'address_bytes': execution['address_space_mib'] * 1024 * 1024,
            'processes': execution['process_count'],
            'output_bytes': execution['output_bytes'],
            'wall_seconds': execution['wall_seconds'],
            'snapshot_wall_seconds': execution['snapshot_wall_seconds'],
            'writable_disk_bytes': execution['writable_disk_mib'] * 1024 * 1024,
        },DEFAULT_POLICY)
        self.assertEqual(policy['grading']['deterministic_weight']+policy['grading']['semantic_weight'],1)

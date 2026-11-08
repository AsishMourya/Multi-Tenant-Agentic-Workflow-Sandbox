import importlib.util
import unittest
from pathlib import Path

from sandbox.agent_grading import grade_inventory_agent, grade_workflow_agent

ROOT = Path(__file__).resolve().parents[1]


def reference(exercise):
    path = (ROOT / 'exercises' / 'workflow' / 'reference.py' if exercise == 'inventory'
            else ROOT / 'exercises' / 'workflow' / exercise / 'reference.py')
    spec = importlib.util.spec_from_file_location('reference_' + exercise.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentGradingTests(unittest.TestCase):
    def test_requires_output_trace_and_restoration(self):
        payload = {'sku': 'apple', 'quantity': 2}
        effects = [{'operation': 'inventory.lookup', 'request': 'lookup-1',
                    'result': {'sku': 'apple', 'available': 7}}]
        output = {'sku': 'apple', 'quantity': 2, 'available': 7, 'accepted': True,
                  'explanation': 'Requested 2; available 7; accepted True.'}
        report = grade_inventory_agent(payload, output, effects,
                                       {'snapshot': {'restored': True}})
        self.assertEqual(report['score'], 1)
        self.assertTrue(report['invariants_ok'])

    def test_no_final_answer_can_compensate_for_bad_tool_trace(self):
        payload = {'sku': 'apple', 'quantity': 2}
        output = {'sku': 'apple', 'quantity': 2, 'available': 7, 'accepted': True,
                  'explanation': 'Requested 2; available 7; accepted True.'}
        report = grade_inventory_agent(payload, output, [], {'snapshot': {}})
        self.assertFalse(report['invariants_ok'])
        self.assertEqual(report['score'], 0)

    def test_all_workflow_exercises_keep_tool_and_restore_gates(self):
        cases = {
            'inventory': ({'sku': 'apple', 'quantity': 2}, {'sku': 'apple', 'available': 7}),
            'stock-reorder': ({'sku': 'apple', 'target_quantity': 10}, {'sku': 'apple', 'available': 7}),
            'inventory-brief': ({'sku': 'pear', 'quantity': 4}, {'sku': 'pear', 'available': 3}),
            'order-explainer': ({'sku': 'apple', 'quantity': 2, 'unit_cents': 125}, {'sku': 'apple', 'available': 7}),
        }
        for exercise, (payload, tool_result) in cases.items():
            with self.subTest(exercise=exercise):
                output = reference(exercise).solve(payload, tool_result['available'])
                effects = [{'operation': 'inventory.lookup', 'request': 'lookup-1',
                            'result': tool_result}]
                execution = {'snapshot': {'restored': True}}
                report = grade_workflow_agent(exercise, payload, output, effects, execution)
                self.assertEqual(report['score'], 1.0)
                self.assertTrue(report['invariants_ok'])
                report = grade_workflow_agent(exercise, payload, output, [], execution)
                self.assertFalse(report['invariants_ok'])

    def test_malformed_workflow_payload_fails_closed(self):
        report = grade_workflow_agent('inventory', [], None, [], {'snapshot': {}})
        self.assertFalse(report['invariants_ok'])


if __name__ == '__main__':
    unittest.main()

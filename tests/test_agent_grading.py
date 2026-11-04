import unittest

from sandbox.agent_grading import grade_inventory_agent


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


if __name__ == '__main__':
    unittest.main()

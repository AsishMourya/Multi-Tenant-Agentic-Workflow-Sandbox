import unittest

from scripts.validate_security import validate


class SecurityReportTests(unittest.TestCase):
    def test_missing_live_enforcement_cannot_be_reported_as_pass(self):
        report = validate({'checks': {}}, {'checks': {}}, {'results': {}})
        self.assertEqual(len(report['cases']), 15)
        self.assertFalse(report['all_pass'])
        self.assertEqual({row['category'] for row in report['cases']},
                         {'isolation', 'resource_exhaustion', 'network_denial', 'secret_protection', 'grader_injection'})
        for row in report['cases']:
            if row['id'].startswith(('RES', 'NET')):
                self.assertEqual(row['status'], 'FAIL')

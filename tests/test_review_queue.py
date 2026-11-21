import unittest

from scripts.review_queue import pending_summary


class ReviewQueueSummaryTests(unittest.TestCase):
    def test_summary_excludes_raw_judgments_and_source(self):
        record = {'source': 'private', 'grade': {
            'grade_id': 'grade-1', 'session': 'tenant-a-1',
            'exercise_version': 'orders-cents:1.0.0', 'score': 70,
            'model_id': 'qwen2.5:0.5b', 'reason': 'pending calibration',
            'judgments': ['model response']}}
        self.assertEqual(pending_summary([record]), [{
            'grade_id': 'grade-1', 'session': 'tenant-a-1',
            'exercise': 'orders-cents', 'provisional_score': 70,
            'model': 'qwen2.5:0.5b', 'reason': 'pending calibration'}])


if __name__ == '__main__':
    unittest.main()

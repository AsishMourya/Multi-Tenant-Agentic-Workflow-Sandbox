import unittest

from scripts.prepare_evaluation import prepare_split


def bank(family_sizes):
    rows = []
    exercise_ids = [f'exercise-{index}' for index in range(6)]
    submission_index = 0
    for family_index, family_size in enumerate(family_sizes):
        for _ in range(family_size):
            rows.append({
                'id': f'submission-{submission_index:02d}',
                'family': f'family-{family_index:02d}',
                'exercise_id': exercise_ids[submission_index % len(exercise_ids)],
                'untrusted_answer': 'label fields must not affect assignment',
            })
            submission_index += 1
    return {'submissions': rows}


class EvaluationSplitTests(unittest.TestCase):
    def test_exact_counts_determinism_and_no_family_leakage(self):
        source = bank([2] * 30)
        first = prepare_split(source, seed='freeze-v1')
        second = prepare_split(source, seed='freeze-v1')
        self.assertEqual(first, second)
        self.assertEqual(first['calibration_count'], 20)
        self.assertEqual(first['held_out_count'], 40)
        self.assertEqual(first['exercise_count'], 6)
        family_splits = {}
        for assignment in first['assignments']:
            family_splits.setdefault(assignment['family'], set()).add(assignment['split'])
        self.assertTrue(all(len(splits) == 1 for splits in family_splits.values()))
        self.assertEqual(first['label_status'], 'not included; collect after split freeze')
        self.assertNotIn('untrusted_answer', first['assignments'][0])

    def test_rejects_unsplittable_family_sizes(self):
        with self.assertRaisesRegex(ValueError, 'cannot produce'):
            prepare_split(bank([7] * 8 + [4]))

    def test_rejects_bad_counts_and_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, 'exactly 60'):
            prepare_split({'submissions': []})
        source = bank([2] * 30)
        source['submissions'][1]['id'] = source['submissions'][0]['id']
        with self.assertRaisesRegex(ValueError, 'duplicate submission ID'):
            prepare_split(source)


if __name__ == '__main__':
    unittest.main()
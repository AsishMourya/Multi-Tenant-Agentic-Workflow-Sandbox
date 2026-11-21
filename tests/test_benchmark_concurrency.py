import unittest
from unittest.mock import patch

from scripts.benchmark_concurrency import benchmark, percentile


class BenchmarkConcurrencyTests(unittest.TestCase):
    def test_percentile_and_repeated_summary(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(percentile([1, 2, 3], .5), 2)

        def fake_burst(_base, _tokens, _source, _payload, count):
            return {'all_pass': True, 'queued_count': max(count - 2, 0),
                    'results': [{'latency_seconds': float(count), 'pass': True}
                                for _ in range(count)]}

        with patch('scripts.benchmark_concurrency.burst', side_effect=fake_burst):
            result = benchmark('local', {}, 'source', {}, repeats=3, capacities=(1, 2, 4))
        self.assertTrue(result['all_pass'])
        self.assertEqual(result['summary']['4']['requests'], 12)
        self.assertEqual(result['summary']['4']['successful'], 12)
        self.assertEqual(result['summary']['4']['queued'], 6)
        self.assertEqual(result['summary']['4']['p95_latency_seconds'], 4)


if __name__ == '__main__':
    unittest.main()

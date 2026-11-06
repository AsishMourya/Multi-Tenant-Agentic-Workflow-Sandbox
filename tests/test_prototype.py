import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.prototype import main


class PrototypeDemoTests(unittest.TestCase):
    def test_demo_runs_and_preserves_existing_output_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / 'evidence'
            output_dir.mkdir()
            existing = output_dir / 'prototype-work'
            existing.mkdir()
            sentinel = existing / 'keep.txt'
            sentinel.write_text('preserve', encoding='utf-8')
            output = output_dir / 'prototype.json'

            with redirect_stdout(io.StringIO()):
                main(output)

            result = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(result['tenant_a_orders']['output']['total_cents'], 625)
            self.assertTrue(result['tenant_b_inventory']['output']['accepted'])
            self.assertEqual(result['review_record']['review_history'][-1]['decision'], 'PASS')
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'preserve')


if __name__ == '__main__':
    unittest.main()

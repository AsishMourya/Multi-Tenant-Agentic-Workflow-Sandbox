"""Standalone Python exercise with a declared full-VM checkpoint."""
import json
import sys
from pathlib import Path

from guest_checkpoint_client import checkpoint


orders = json.load(sys.stdin)
counter = 77
Path('/tmp/dat-counter.txt').write_text(str(counter), encoding='utf-8')
checkpoint()
counter += 1
restored = Path('/tmp/dat-counter.txt').read_text(encoding='utf-8')
print(json.dumps({'counter_after_restore': counter, 'disk_value_after_restore': restored}),
      file=sys.stderr)
totals = {}
for order in orders:
    sku = order['sku']
    totals[sku] = totals.get(sku, 0) + order['quantity'] * order['unit_cents']
print(json.dumps({'by_sku': dict(sorted(totals.items())),
                  'total_cents': sum(totals.values())}))

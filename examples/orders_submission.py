"""Example learner program: read JSON input and print JSON output."""
import json
import sys


orders = json.load(sys.stdin)
totals = {}
for order in orders:
    sku = order['sku']
    totals[sku] = totals.get(sku, 0) + order['quantity'] * order['unit_cents']
print(json.dumps({'by_sku': dict(sorted(totals.items())),
                  'total_cents': sum(totals.values())}))

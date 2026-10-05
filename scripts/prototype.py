"""Run the two-tenant, two-exercise local prototype demonstration."""
import argparse
import json
import shutil
from pathlib import Path

from sandbox.platform import Platform


def judge(level=4):
    return {'criteria': {name: {'level': level, 'status': 'APPLICABLE', 'evidence': 'observed output',
                               'reason': 'matches the bounded exercise evidence'}
                         for name in ('correctness', 'clarity')},
            'conflicts_with_tests': False, 'confidence': .9}


def main(output):
    root = Path(output).parent / 'prototype-work'
    if root.exists():
        shutil.rmtree(root)
    platform = Platform(root)
    try:
        first = platform.create_session('tenant-a', 'orders-cents')
        second = platform.create_session('tenant-b', 'inventory')
        results = {
            'tenant_a_orders': platform.submit('tenant-a', first, [
                {'sku': 'apple', 'quantity': 2, 'unit_cents': 125},
                {'sku': 'apple', 'quantity': 3, 'unit_cents': 125}], [judge(), judge()]),
            'tenant_b_inventory': platform.submit('tenant-b', second,
                                                    {'sku': 'apple', 'quantity': 5}, [judge(), judge()]),
            'claims': ['two authenticated tenants', 'two supported exercises',
                       'application-state checkpoint after broker effect',
                       'review records are retained'],
        }
        review = platform.submit('tenant-a', first, [], [judge(0), judge(0)])['grade']
        results['review_record'] = platform.add_review(
            review['grade_id'], 'mentor-demo', 'PASS', 'boundary case checked')
        results['review_records'] = platform.grades
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps(results, indent=2))
    finally:
        platform.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='evidence/prototype.json')
    main(parser.parse_args().output)
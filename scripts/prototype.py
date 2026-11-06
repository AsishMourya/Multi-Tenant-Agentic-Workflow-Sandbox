"""Run the two-tenant, two-exercise local prototype demonstration."""
import argparse
import json
import tempfile
from pathlib import Path

from sandbox.platform import Platform


def judge(level=4):
    return {'criteria': {name: {'level': level, 'status': 'APPLICABLE', 'evidence': 'observed output',
                               'reason': 'matches the bounded exercise evidence'}
                         for name in ('correctness', 'clarity')},
            'conflicts_with_tests': False, 'confidence': .9}


def main(output):
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sandbox-prototype-') as work:
        platform = Platform(work)
        try:
            first = platform.create_session('tenant-a', 'orders-cents')
            second = platform.create_session('tenant-b', 'inventory')
            results = {
                'tenant_a_orders': platform.submit('tenant-a', first, [
                    {'sku': 'apple', 'quantity': 2, 'unit_cents': 125},
                    {'sku': 'apple', 'quantity': 3, 'unit_cents': 125}],
                    [judge(), judge()]),
                'tenant_b_inventory': platform.submit('tenant-b', second,
                    {'sku': 'apple', 'quantity': 5}, [judge(), judge()]),
                'claims': ['two synthetic tenant identities', 'two supported exercises',
                           'application-state checkpoint after broker effect',
                           'review records are retained',
                           'trusted reference demo; does not execute learner source'],
            }
            review_session = platform.create_session('tenant-a', 'orders-cents')
            review = platform.submit('tenant-a', review_session, [],
                                     [judge(0), judge(0)])['grade']
            results['review_record'] = platform.add_review(
                review['grade_id'], 'mentor-demo', 'PASS', 'boundary case checked')
            results['review_records'] = platform.grades
            result_path = Path(output)
            result_path.write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(json.dumps(results, indent=2))
        finally:
            platform.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='evidence/prototype.json')
    main(parser.parse_args().output)

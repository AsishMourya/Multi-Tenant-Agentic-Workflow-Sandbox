"""Build 60 explicitly synthetic development submissions, never human labels."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.live_api_workflow_probe import template
from scripts.prepare_evaluation import prepare_split


def build_bank(root):
    templates = (root / 'web/src/App.jsx').read_text(encoding='utf-8')
    rows = []
    for exercise in ('orders-cents', 'daily-revenue', 'inventory', 'stock-reorder',
                     'inventory-brief', 'order-explainer'):
        source, payload = template(templates, exercise)
        alternate = copy.deepcopy(payload)
        if exercise == 'orders-cents':
            alternate = []
            constant = {'by_sku': {'apple': 250, 'pear': 80}, 'total_cents': 330}
        elif exercise == 'daily-revenue':
            alternate = {'sales': []}
            constant = {'by_day': {'2026-01-01': 2000, '2026-01-02': 900}, 'total_cents': 2900}
        else:
            alternate['sku'] = 'pear' if payload['sku'] == 'apple' else 'apple'
            field = 'target_quantity' if exercise == 'stock-reorder' else 'quantity'
            alternate[field] = 9
            constant = {'sku': payload['sku'], 'available': 7, 'accepted': True}
        candidates = {
            'starter': source,
            'constant': f'import json\nprint(json.dumps({constant!r}))\n',
            'invalid-schema': 'print("[]")\n',
            'runtime-error': 'raise ValueError("synthetic evaluation failure")\n',
            'invalid-json': 'print("this is not JSON")\n',
        }
        for category, submission in candidates.items():
            digest = hashlib.sha256(submission.encode()).hexdigest()
            for index, input_value in enumerate((payload, alternate)):
                rows.append({'id': f'{exercise}-{category}-{index + 1}',
                             'family': f'source-{digest}', 'exercise_id': exercise,
                             'source': submission, 'payload': input_value,
                             'provenance': 'synthetic development fixture',
                             'construction': category})
    return {'schema_version': 'submission-bank-1.0.0',
            'purpose': 'engineering regression; not a human-labelled grading benchmark',
            'submissions': rows}


def bank_digest(bank):
    return hashlib.sha256(json.dumps(bank, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='evaluation/regression-bank.json')
    parser.add_argument('--split', default='evaluation/regression-split.json')
    args = parser.parse_args()
    bank = build_bank(Path(__file__).resolve().parents[1])
    split = prepare_split(bank)
    split['bank_sha256'] = bank_digest(bank)
    split['purpose'] = bank['purpose']
    for filename, data in ((args.output, bank), (args.split, split)):
        path = Path(filename)
        if path.exists():
            raise SystemExit(f'refusing to replace existing dataset: {path}')
    for filename, data in ((args.output, bank), (args.split, split)):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'submissions': len(bank['submissions']), 'families': split['family_count'],
                      'calibration': split['calibration_count'], 'held_out': split['held_out_count'],
                      'bank_sha256': split['bank_sha256']}))


if __name__ == '__main__':
    main()

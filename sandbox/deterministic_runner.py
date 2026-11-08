"""Trusted manifest-driven deterministic grading for submitted Python work.

The callback is an isolated executor supplied by the backend.  Test vectors and
expected answers stay in this controller module and are never staged in a guest.
"""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from exercises.python.reference import solve
from exercises.python.daily_revenue.reference import solve as solve_daily_revenue


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'exercises' / 'python' / 'manifest.json'
OUTPUT_SCHEMA = ROOT / 'schemas' / 'python-output.schema.json'
CASES = (
    ('normal', [{'sku': 'apple', 'quantity': 2, 'unit_cents': 125}]),
    ('empty', []),
    ('duplicate', [{'sku': 'pear', 'quantity': 2, 'unit_cents': 125},
                   {'sku': 'pear', 'quantity': 3, 'unit_cents': 125}]),
    ('mixed', [{'sku': 'pear', 'quantity': 1, 'unit_cents': 5},
               {'sku': 'apple', 'quantity': 2, 'unit_cents': 4}]),
)
DAILY_REVENUE_CASES = (
    ('empty', {'sales': []}),
    ('one-day-sum', {'sales': [{'day': '2026-01-01', 'amount_cents': 125},
                               {'day': '2026-01-01', 'amount_cents': 75}]}),
    ('multiple-days', {'sales': [{'day': '2026-01-02', 'amount_cents': 90},
                                 {'day': '2026-01-01', 'amount_cents': 110}]}),
)


def solve_python(exercise, payload):
    solvers = {'orders-cents': solve, 'daily-revenue': solve_daily_revenue}
    try:
        solver = solvers[exercise]
    except KeyError as exc:
        raise ValueError(f'unsupported Python exercise: {exercise}') from exc
    return solver(payload)


def _decode(execution, validator):
    if not isinstance(execution, dict) or execution.get('status') != 'ok':
        return None
    try:
        output = json.loads(execution['stdout'])
        validator.validate(output)
        return output
    except (KeyError, TypeError, ValueError):
        return None
    except Exception:  # jsonschema validation errors are intentionally a failed test.
        return None


def grade_orders_submission(execute):
    """Run all hidden cases through ``execute(payload)`` and return fixed evidence."""
    if not callable(execute):
        raise TypeError('isolated execution callback required')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    weights = manifest['deterministic_weights']
    validator = Draft202012Validator(json.loads(OUTPUT_SCHEMA.read_text(encoding='utf-8')))
    observed = []
    for name, payload in CASES:
        execution = execute(payload)
        output = _decode(execution, validator)
        observed.append({'case': name, 'passed': output == solve(payload),
                         'execution_status': execution.get('status') if isinstance(execution, dict) else None})
    numeric_cases = {'normal', 'duplicate'}
    results = [
        {'check': 'numeric_correctness', 'weight': weights['numeric_correctness'],
         'passed': all(item['passed'] for item in observed if item['case'] in numeric_cases),
         'cases': observed},
        {'check': 'schema_and_edge_cases', 'weight': weights['schema_and_edge_cases'],
         'passed': all(item['passed'] for item in observed), 'cases': observed},
    ]
    return {'manifest': {'exercise_id': manifest['exercise_id'],
                         'exercise_version': manifest['exercise_version'],
                         'test_suite_version': manifest['versions']['test_suite']},
            'results': results,
            'score': sum(item['weight'] for item in results if item['passed']),
            'invariants_ok': all(item['passed'] for item in results)}


def grade_daily_revenue_submission(execute):
    """Run fixed daily-revenue vectors in the isolated execution callback."""
    if not callable(execute):
        raise TypeError('isolated execution callback required')
    manifest_path = ROOT / 'exercises' / 'python' / 'daily_revenue' / 'manifest.json'
    output_schema = ROOT / 'schemas' / 'daily-revenue-output.schema.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    validator = Draft202012Validator(json.loads(output_schema.read_text(encoding='utf-8')))
    results = []
    for name, payload in DAILY_REVENUE_CASES:
        execution = execute(payload)
        output = _decode(execution, validator)
        results.append({'check': name, 'weight': 1 / len(DAILY_REVENUE_CASES),
                        'passed': output == solve_daily_revenue(payload),
                        'execution_status': execution.get('status') if isinstance(execution, dict) else None})
    return {'manifest': {'exercise_id': manifest['exercise_id'],
                         'exercise_version': manifest['exercise_version'],
                         'test_suite_version': manifest['versions']['test_suite']},
            'results': results,
            'score': sum(row['weight'] for row in results if row['passed']),
            'invariants_ok': all(row['passed'] for row in results)}


def grade_python_submission(exercise, execute):
    graders = {'orders-cents': grade_orders_submission,
               'daily-revenue': grade_daily_revenue_submission}
    try:
        grader = graders[exercise]
    except KeyError as exc:
        raise ValueError(f'unsupported Python exercise: {exercise}') from exc
    return grader(execute)


def grade_python_submission(exercise, execute):
    if exercise == 'orders-cents':
        return grade_orders_submission(execute)
    if exercise == 'daily-revenue':
        return grade_daily_revenue_submission(execute)
    raise ValueError(f'unsupported Python exercise: {exercise}')

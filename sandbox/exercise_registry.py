"""Supported exercise IDs and their execution modes."""
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

PYTHON_EXERCISES = frozenset({'orders-cents', 'daily-revenue'})
WORKFLOW_EXERCISES = frozenset({
    'inventory', 'stock-reorder', 'inventory-brief', 'order-explainer'
})
EXERCISE_MODES = {
    **{exercise: 'python' for exercise in PYTHON_EXERCISES},
    **{exercise: 'workflow' for exercise in WORKFLOW_EXERCISES},
}
EXERCISES = frozenset(EXERCISE_MODES)


@lru_cache(maxsize=6)
def input_validator(exercise):
    root = Path(__file__).resolve().parents[1] / 'exercises'
    for path in root.rglob('manifest.json'):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if manifest['exercise_id'] == exercise:
            schema = json.loads((path.parent / manifest['input_schema']).read_text(encoding='utf-8'))
            return Draft202012Validator(schema)
    raise ValueError('unsupported exercise')


def validate_input(exercise, payload):
    error = next(input_validator(exercise).iter_errors(payload), None)
    if error is not None:
        location = '.'.join(map(str, error.absolute_path)) or 'input'
        raise ValueError(f'invalid exercise input at {location}: {error.message}')

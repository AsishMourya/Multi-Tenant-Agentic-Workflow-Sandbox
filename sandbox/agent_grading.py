"""Deterministic gates for the registered inventory-backed workflow exercises."""
import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = {
    'inventory': ROOT / 'exercises' / 'workflow' / 'manifest.json',
    'stock-reorder': ROOT / 'exercises' / 'workflow' / 'stock-reorder' / 'manifest.json',
    'inventory-brief': ROOT / 'exercises' / 'workflow' / 'inventory-brief' / 'manifest.json',
    'order-explainer': ROOT / 'exercises' / 'workflow' / 'order-explainer' / 'manifest.json',
}
RESULT_CHECKS = {
    'inventory': 'accepted_result',
    'stock-reorder': 'reorder_result',
    'inventory-brief': 'decision_and_schema',
    'order-explainer': 'numeric_and_decision',
}
TEXT_FIELDS = {'explanation', 'summary'}


def _reference(manifest_path, exercise, payload, available):
    reference_path = manifest_path.parent / json.loads(
        manifest_path.read_text(encoding='utf-8'))['reference']
    module_name = 'dat_reference_' + exercise.replace('-', '_')
    spec = importlib.util.spec_from_file_location(module_name, reference_path)
    if spec is None or spec.loader is None:
        raise ValueError('exercise reference is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.solve(payload, available)


def grade_workflow_agent(exercise, payload, output, effects, execution):
    """Check output shape/value, one scoped lookup, and actual snapshot restoration."""
    if exercise not in MANIFESTS:
        raise ValueError(f'unsupported workflow exercise: {exercise}')
    manifest_path = MANIFESTS[exercise]
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    weights = manifest['deterministic_weights']
    output_path = manifest_path.parent / manifest['output_schema']
    validator = Draft202012Validator(json.loads(output_path.read_text(encoding='utf-8')))
    expected = None
    available = None
    if len(effects) == 1:
        try:
            available = effects[0]['result']['available']
            expected = _reference(manifest_path, exercise, payload, available)
        except (KeyError, TypeError, ValueError):
            pass
    schema_ok = False
    try:
        validator.validate(output)
        schema_ok = True
    except Exception:
        pass
    result_ok = False
    if schema_ok and expected is not None:
        result_ok = all(output.get(key) == value for key, value in expected.items()
                        if key not in TEXT_FIELDS)
        result_ok = result_ok and all(
            isinstance(output.get(key), str) and 0 < len(output[key]) <= 2000
            for key in expected if key in TEXT_FIELDS)
    tool_ok = (isinstance(payload, dict) and len(effects) == 1
               and effects[0].get('operation') == 'inventory.lookup'
               and effects[0].get('request') == 'lookup-1'
               and effects[0].get('result', {}).get('sku') == payload.get('sku'))
    restore_ok = execution.get('snapshot', {}).get('restored') is True
    result_name = RESULT_CHECKS[exercise]
    results = [
        {'check': result_name, 'weight': weights[result_name], 'passed': result_ok},
        {'check': 'authorized_tool_trace', 'weight': weights['authorized_tool_trace'],
         'passed': tool_ok},
        {'check': 'checkpoint_continuity', 'weight': weights['checkpoint_continuity'],
         'passed': restore_ok},
    ]
    return {'results': results, 'score': sum(item['weight'] for item in results if item['passed']),
            'invariants_ok': all(item['passed'] for item in results)}


def grade_inventory_agent(payload, output, effects, execution):
    """Compatibility wrapper retained for the original inventory callers."""
    return grade_workflow_agent('inventory', payload, output, effects, execution)

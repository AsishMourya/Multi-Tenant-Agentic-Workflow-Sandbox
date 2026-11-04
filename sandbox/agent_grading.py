"""Trusted deterministic checks for the brokered inventory agent exercise."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'exercises' / 'workflow' / 'manifest.json'
SCHEMA = ROOT / 'schemas' / 'workflow-output.schema.json'


def grade_inventory_agent(payload, output, effects, execution):
    """Grade the final answer, authorized tool trace, and safe-point restoration."""
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    weights = manifest['deterministic_weights']
    expected = None
    if len(effects) == 1:
        try:
            available = effects[0]['result']['available']
            expected = {'sku': payload['sku'], 'quantity': payload['quantity'],
                        'available': available, 'accepted': payload['quantity'] <= available,
                        'explanation': f"Requested {payload['quantity']}; available {available}; accepted {payload['quantity'] <= available}."}
        except (KeyError, TypeError):
            pass
    schema_ok = False
    try:
        Draft202012Validator(json.loads(SCHEMA.read_text(encoding='utf-8'))).validate(output)
        schema_ok = True
    except Exception:
        pass
    tool_ok = (len(effects) == 1 and effects[0].get('operation') == 'inventory.lookup'
               and effects[0].get('request') == 'lookup-1'
               and effects[0].get('result', {}).get('sku') == payload.get('sku'))
    restore_ok = execution.get('snapshot', {}).get('restored') is True
    results = [
        {'check': 'accepted_result', 'weight': weights['accepted_result'],
         'passed': schema_ok and output == expected},
        {'check': 'authorized_tool_trace', 'weight': weights['authorized_tool_trace'],
         'passed': tool_ok},
        {'check': 'checkpoint_continuity', 'weight': weights['checkpoint_continuity'],
         'passed': restore_ok},
    ]
    return {'results': results, 'score': sum(item['weight'] for item in results if item['passed']),
            'invariants_ok': all(item['passed'] for item in results)}

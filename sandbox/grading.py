"""Exercise-grade decision policy; model judgments never bypass hard gates."""
import math


DEFAULT_WEIGHTS = {'correctness': 0.5, 'clarity': 0.5}
DEFAULT_PASS_THRESHOLD = 60
DEFAULT_REVIEW_MARGIN = 5


def normalize_deterministic(results):
    """Return D in [0, 1] from weighted observed subtest results."""
    if not isinstance(results, list) or not results:
        raise ValueError('deterministic results required')
    total = passed = 0.0
    for result in results:
        if not isinstance(result, dict) or type(result.get('passed')) is not bool:
            raise ValueError('invalid deterministic result')
        weight = result.get('weight')
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or not math.isfinite(weight) or weight <= 0:
            raise ValueError('invalid deterministic weight')
        total += weight
        passed += weight if result['passed'] else 0
    return passed / total


def _valid_judgment(judgment, criteria):
    if not isinstance(judgment, dict) or set(judgment) != {'criteria', 'conflicts_with_tests', 'confidence'}:
        return False, 'invalid judgment shape'
    if type(judgment['conflicts_with_tests']) is not bool:
        return False, 'invalid conflict flag'
    if type(judgment['confidence']) not in (int, float) or not math.isfinite(judgment['confidence']) or not 0 <= judgment['confidence'] <= 1:
        return False, 'invalid confidence'
    if not isinstance(judgment['criteria'], dict) or set(judgment['criteria']) != set(criteria):
        return False, 'criteria set mismatch'
    for name, item in judgment['criteria'].items():
        if not isinstance(item, dict) or set(item) != {'level', 'evidence', 'reason', 'status'}:
            return False, f'invalid criterion fields: {name}'
        if item['status'] not in {'APPLICABLE', 'NOT_APPLICABLE', 'ABSTAIN'}:
            return False, f'invalid criterion status: {name}'
        if item['status'] == 'APPLICABLE' and (type(item['level']) is not int or not 0 <= item['level'] <= 4):
            return False, f'invalid criterion level: {name}'
        if item['status'] != 'APPLICABLE' and item['level'] is not None:
            return False, f'non-applicable criterion must have null level: {name}'
        if not all(isinstance(item[key], str) and 0 < len(item[key]) <= 2000 for key in ('evidence', 'reason')):
            return False, f'invalid criterion evidence: {name}'
    return True, None


def _normalize_judgment(judgment):
    """Accept old local fixtures while new records remain explicit."""
    if not isinstance(judgment, dict) or not isinstance(judgment.get('criteria'), dict):
        return judgment
    normalized = dict(judgment)
    normalized['criteria'] = {
        name: dict(item, status=item.get('status', 'APPLICABLE'))
        for name, item in judgment['criteria'].items()
    }
    return normalized


def decision(deterministic, invariant_ok, judges, infrastructure_ok=True,
             policy_ok=True, weights=None, pass_threshold=DEFAULT_PASS_THRESHOLD,
             review_margin=DEFAULT_REVIEW_MARGIN):
    """Return a final status with infrastructure/policy/gate precedence.

    D is normalized to [0, 1]. S is the weighted average of applicable levels / 4.
    Any abstention, inconsistent applicability, disagreement, borderline score, or
    conflict with deterministic evidence remains REVIEW rather than auto-final.
    """
    if not infrastructure_ok:
        return {'status': 'RETRY_ERROR', 'score': None, 'reason': 'infrastructure failure'}
    if not policy_ok:
        return {'status': 'POLICY_FAILURE', 'score': None, 'reason': 'policy failure'}
    if not invariant_ok:
        return {'status': 'FAIL_INVARIANT', 'score': None, 'reason': 'mandatory invariant failed'}
    if not isinstance(deterministic, (int, float)) or isinstance(deterministic, bool) or not math.isfinite(deterministic) or not 0 <= deterministic <= 1:
        raise ValueError('invalid normalized deterministic score')
    weights = dict(weights or DEFAULT_WEIGHTS)
    if set(weights) != {'correctness', 'clarity'} or any(type(value) not in (int, float) or value <= 0 for value in weights.values()):
        raise ValueError('invalid semantic weights')
    if not isinstance(judges, list) or len(judges) != 2:
        return {'status': 'REVIEW', 'score': None, 'reason': 'exactly two judgments required'}
    normalized = [_normalize_judgment(judge) for judge in judges]
    for judge in normalized:
        valid, reason = _valid_judgment(judge, weights)
        if not valid:
            return {'status': 'REVIEW', 'score': None, 'reason': reason}
    review_reasons = []
    applicable = []
    for criterion in weights:
        statuses = [judge['criteria'][criterion]['status'] for judge in normalized]
        if 'ABSTAIN' in statuses:
            review_reasons.append(f'{criterion}: abstention')
        if statuses == ['NOT_APPLICABLE', 'NOT_APPLICABLE']:
            continue
        if 'NOT_APPLICABLE' in statuses:
            review_reasons.append(f'{criterion}: inconsistent applicability')
            continue
        applicable.append(criterion)
    if not applicable:
        return {'status': 'REVIEW', 'score': None, 'reason': 'no applicable semantic criteria'}
    if review_reasons:
        return {'status': 'REVIEW', 'score': None, 'reason': '; '.join(review_reasons)}
    applicable_weight = sum(weights[name] for name in applicable)
    semantic = sum(sum(judge['criteria'][name]['level'] * weights[name] for name in applicable) / applicable_weight for judge in normalized) / 8
    score = round(100 * (0.6 * deterministic + 0.4 * semantic), 2)
    if any(abs(normalized[0]['criteria'][name]['level'] - normalized[1]['criteria'][name]['level']) > 1 for name in applicable):
        review_reasons.append('criterion disagreement greater than one level')
    if abs(score - pass_threshold) <= review_margin:
        review_reasons.append('score is within review margin')
    if any(judge['conflicts_with_tests'] for judge in normalized):
        review_reasons.append('judge conflicts with deterministic evidence')
    return {'status': 'REVIEW' if review_reasons else ('PASS' if score >= pass_threshold else 'FAIL'),
            'score': score, 'D': deterministic, 'S': semantic,
            'normalization': {'deterministic': 'weighted passed weight / total weight',
                              'semantic': 'weighted applicable level / (4 * applicable weight)'},
            'review_reasons': review_reasons}

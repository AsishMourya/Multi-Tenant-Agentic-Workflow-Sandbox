"""Assign fixed evaluation submissions to calibration or held-out by family.

This utility reads only submission ID, family, and exercise ID. It never reads,
generates, or modifies human labels or automated grades.
"""
import argparse
import hashlib
import json
from pathlib import Path


def prepare_split(bank, *, seed='dat-eval-family-v1', total=60,
                  calibration=20, exercise_count=6):
    if not isinstance(bank, dict) or not isinstance(bank.get('submissions'), list):
        raise ValueError('input must contain a submissions list')
    rows = bank['submissions']
    if len(rows) != total:
        raise ValueError(f'exactly {total} submissions are required')
    if not isinstance(seed, str) or not seed:
        raise ValueError('non-empty split seed required')
    if type(calibration) is not int or not 0 < calibration < total:
        raise ValueError('calibration count must be between zero and total')

    ids = set()
    groups = {}
    exercises = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('each submission must be an object')
        submission_id = row.get('id')
        family = row.get('family')
        exercise = row.get('exercise_id')
        if not all(isinstance(value, str) and value.strip()
                   for value in (submission_id, family, exercise)):
            raise ValueError('each submission requires id, family, and exercise_id')
        if submission_id in ids:
            raise ValueError(f'duplicate submission ID: {submission_id}')
        ids.add(submission_id)
        exercises.add(exercise)
        groups.setdefault(family, []).append(submission_id)
    if len(exercises) != exercise_count:
        raise ValueError(f'exactly {exercise_count} exercises are required')

    ranked_families = sorted(
        groups,
        key=lambda family: (hashlib.sha256(f'{seed}\0{family}'.encode()).hexdigest(), family),
    )
    reachable = {0: ()}
    for family in ranked_families:
        family_size = len(groups[family])
        for count, selected in list(reachable.items()):
            next_count = count + family_size
            if next_count <= calibration and next_count not in reachable:
                reachable[next_count] = selected + (family,)
    if calibration not in reachable:
        raise ValueError('family sizes cannot produce the requested calibration count')

    calibration_families = set(reachable[calibration])
    split_by_family = {
        family: 'calibration' if family in calibration_families else 'held_out'
        for family in groups
    }
    assignments = [
        {'id': row['id'], 'family': row['family'], 'exercise_id': row['exercise_id'],
         'split': split_by_family[row['family']]}
        for row in rows
    ]
    assignments.sort(key=lambda row: row['id'])
    counts = {
        name: sum(row['split'] == name for row in assignments)
        for name in ('calibration', 'held_out')
    }
    return {
        'schema_version': 'evaluation-split-1.0.0',
        'seed': seed,
        'source_submission_count': total,
        'exercise_count': exercise_count,
        'family_count': len(groups),
        'calibration_count': counts['calibration'],
        'held_out_count': counts['held_out'],
        'label_status': 'not included; collect after split freeze',
        'assignments': assignments,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='JSON bank with id, family, exercise_id per submission')
    parser.add_argument('--output', required=True, help='write the split assignment JSON here')
    parser.add_argument('--seed', default='dat-eval-family-v1')
    args = parser.parse_args()
    try:
        bank = json.loads(Path(args.input).read_text(encoding='utf-8'))
        split = prepare_split(bank, seed=args.seed)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(split, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in split.items() if key != 'assignments'}, indent=2))


if __name__ == '__main__':
    main()
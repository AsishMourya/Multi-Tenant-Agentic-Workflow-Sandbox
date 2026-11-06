"""Compute held-out grading metrics without overwriting independent human labels."""
import argparse
import json
from pathlib import Path


def rate(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'rate': None if not denominator else round(numerator / denominator, 4)}


def evaluate(data):
    rows = data.get('submissions') if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError('non-empty submissions list required')
    automatic = [row for row in rows if row.get('automated_status') in {'PASS', 'FAIL'}]
    disagreements = 0
    false_accepts = false_rejects = incorrect = correct = 0
    families = set()
    for row in rows:
        ratings = row.get('human_ratings')
        if (not isinstance(row.get('id'), str) or not isinstance(row.get('family'), str) or
                not isinstance(ratings, list) or len(ratings) != 2 or
                any(type(item) is not bool for item in ratings) or
                type(row.get('adjudicated_correct')) is not bool):
            raise ValueError('invalid labelled submission')
        families.add(row['family'])
        disagreements += ratings[0] != ratings[1]
        if row['adjudicated_correct']:
            correct += 1
        else:
            incorrect += 1
        if row in automatic:
            if row['automated_status'] == 'PASS' and not row['adjudicated_correct']:
                false_accepts += 1
            if row['automated_status'] == 'FAIL' and row['adjudicated_correct']:
                false_rejects += 1
    return {'submission_count': len(rows), 'family_count': len(families),
            'human_human_disagreement': rate(disagreements, len(rows)),
            'automatic_coverage': rate(len(automatic), len(rows)),
            'false_acceptance_rate': rate(false_accepts, incorrect),
            'false_rejection_rate': rate(false_rejects, correct),
            'review_rate': rate(len(rows) - len(automatic), len(rows))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = evaluate(json.loads(Path(args.labels).read_text(encoding='utf-8')))
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))

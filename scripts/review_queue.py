"""Trusted host-only review queue. Never exposes review authority to learners."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.reviews import record_review


def pending_summary(records):
    return [{'grade_id': record['grade']['grade_id'],
             'session': record['grade']['session'],
             'exercise': record['grade']['exercise_version'].split(':')[0],
             'provisional_score': record['grade'].get('score'),
             'model': record['grade'].get('model_id'),
             'reason': record['grade'].get('reason')}
            for record in records]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', default='work/demo-state-v2')
    parser.add_argument('--grade-id')
    parser.add_argument('--reviewer')
    parser.add_argument('--decision', choices=['PASS', 'FAIL', 'ESCALATE'])
    parser.add_argument('--reason')
    parser.add_argument('--summary', action='store_true',
                        help='list pending reviews without raw submissions or model responses')
    args = parser.parse_args()
    database = Path(args.state_root) / 'platform.sqlite3'
    if not database.is_file():
        parser.error('platform database does not exist')
    if args.grade_id:
        if not all((args.reviewer, args.decision, args.reason)):
            parser.error('recording review requires reviewer, decision and reason')
        result = record_review(database, args.grade_id, args.reviewer, args.decision, args.reason)
    else:
        db = sqlite3.connect(database)
        try:
            result = []
            for (encoded,) in db.execute('SELECT result_json FROM submissions WHERE result_json IS NOT NULL'):
                record = json.loads(encoded)
                grade = record.get('grade', {})
                history = grade.get('review_history', [])
                if grade.get('status') == 'REVIEW' and (not history or history[-1]['decision'] == 'ESCALATE'):
                    result.append(record)
        finally:
            db.close()
        if args.summary:
            result = pending_summary(result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

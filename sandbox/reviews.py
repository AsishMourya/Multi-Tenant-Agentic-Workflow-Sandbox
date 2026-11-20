"""Transactional human review records; machine grades remain immutable."""
import json
import sqlite3
from datetime import datetime, timezone


def record_review(database, grade_id, reviewer, decision, reason):
    if (not all(isinstance(value, str) and 0 < len(value.strip()) <= 2000
                for value in (grade_id, reviewer, decision, reason))
            or decision not in {'PASS', 'FAIL', 'ESCALATE'}):
        raise ValueError('invalid review record')
    db = sqlite3.connect(database, isolation_level=None)
    try:
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute('SELECT session,result_json FROM submissions WHERE result_json IS NOT NULL').fetchall()
        for session, encoded in rows:
            result = json.loads(encoded)
            grade = result.get('grade', {})
            if grade.get('grade_id') != grade_id:
                continue
            if grade['status'] != 'REVIEW':
                raise ValueError('grade is not pending review')
            grade.setdefault('review_history', []).append({
                'reviewer': reviewer.strip(), 'at_utc': datetime.now(timezone.utc).isoformat(),
                'decision': decision, 'reason': reason.strip()})
            db.execute('UPDATE submissions SET result_json=? WHERE session=?',
                       (json.dumps(result), session))
            db.execute('COMMIT')
            return grade
        raise KeyError('unknown grade')
    finally:
        if db.in_transaction:
            db.execute('ROLLBACK')
        db.close()

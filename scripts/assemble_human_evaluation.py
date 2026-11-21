"""Validate independent ratings and assemble an auditable, held-out label set.

No ratings are inferred from model output. Disagreements require a separate
adjudicator decision; matching ratings are copied without alteration.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_evaluation import validate_bank


CRITERIA = ('correctness', 'clarity')


def _packet_rows(packet, assignments, digest, originals):
    if packet.get('schema_version') != 'independent-human-rating-1.0.0' or packet.get('bank_sha256') != digest:
        raise ValueError('rating packet schema or frozen bank digest mismatch')
    rows = packet.get('submissions')
    if not isinstance(rows, list) or len(rows) != len(assignments):
        raise ValueError('rating packet must cover the entire frozen bank')
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('id') not in assignments or row['id'] in by_id:
            raise ValueError('unknown or duplicate rating row')
        original = originals[row['id']]
        if any(row.get(key) != original[key] for key in ('exercise_id', 'source', 'payload')):
            raise ValueError(f"rating packet submission changed: {row['id']}")
        ratings = row.get('ratings')
        if not isinstance(ratings, dict) or set(ratings) != set(CRITERIA) or any(
                type(ratings[name]) is not int or not 0 <= ratings[name] <= 4 for name in CRITERIA):
            raise ValueError(f"missing or invalid criterion ratings: {row['id']}")
        if type(row.get('overall_pass')) is not bool:
            raise ValueError(f"missing overall_pass: {row['id']}")
        by_id[row['id']] = row
    return by_id


def disagreements(bank, split, rater_a, rater_b):
    assignments = validate_bank(bank, split)
    originals = {row['id']: row for row in bank['submissions']}
    if not rater_a.get('rater') or not rater_b.get('rater') or rater_a['rater'] == rater_b['rater']:
        raise ValueError('two distinctly named independent raters required')
    a = _packet_rows(rater_a, assignments, split['bank_sha256'], originals)
    b = _packet_rows(rater_b, assignments, split['bank_sha256'], originals)
    return [{'id': sid, 'rater_a': {'ratings': a[sid]['ratings'], 'overall_pass': a[sid]['overall_pass']},
             'rater_b': {'ratings': b[sid]['ratings'], 'overall_pass': b[sid]['overall_pass']},
             'adjudicated_ratings': {name: None for name in CRITERIA},
             'adjudicated_pass': None, 'rationale': ''}
            for sid in assignments if a[sid]['ratings'] != b[sid]['ratings'] or
            a[sid]['overall_pass'] != b[sid]['overall_pass']]


def make_adjudication_packet(bank, split, rater_a, rater_b):
    return {'schema_version': 'human-adjudication-1.0.0',
            'bank_sha256': split['bank_sha256'], 'rater_a': rater_a['rater'],
            'rater_b': rater_b['rater'],
            'instructions': 'Resolve each disagreement independently of model scores and split assignments. '
                            'Record a rationale for every decision. Do not overwrite either original rating packet.',
            'disagreements': disagreements(bank, split, rater_a, rater_b)}


def assemble(bank, split, rater_a, rater_b, adjudication, runs):
    assignments = validate_bank(bank, split)
    expected = disagreements(bank, split, rater_a, rater_b)
    if (adjudication.get('schema_version') != 'human-adjudication-1.0.0' or
            adjudication.get('bank_sha256') != split['bank_sha256'] or
            adjudication.get('rater_a') != rater_a['rater'] or
            adjudication.get('rater_b') != rater_b['rater']):
        raise ValueError('adjudication provenance mismatch')
    decisions = adjudication.get('disagreements')
    if not isinstance(decisions, list) or {row.get('id') for row in decisions} != {
            row['id'] for row in expected} or len(decisions) != len(expected):
        raise ValueError('adjudication must resolve exactly the rater disagreements')
    expected_by_id = {row['id']: row for row in expected}
    decided = {}
    for row in decisions:
        sid = row['id']
        if row.get('rater_a') != expected_by_id[sid]['rater_a'] or row.get('rater_b') != expected_by_id[sid]['rater_b']:
            raise ValueError('original rater decisions changed in adjudication')
        ratings = row.get('adjudicated_ratings')
        if not isinstance(ratings, dict) or set(ratings) != set(CRITERIA) or any(
                type(ratings[name]) is not int or not 0 <= ratings[name] <= 4 for name in CRITERIA):
            raise ValueError(f'incomplete adjudicated ratings: {sid}')
        if type(row.get('adjudicated_pass')) is not bool or not str(row.get('rationale', '')).strip():
            raise ValueError(f'adjudication decision and rationale required: {sid}')
        decided[sid] = row
    observed = {}
    for run in runs:
        sid = run.get('id')
        if sid not in assignments or run.get('bank_sha256') != split['bank_sha256'] or run.get('repeat') != 1 or sid in observed:
            raise ValueError('expected one primary run per frozen submission')
        observed[sid] = run
    if set(observed) != set(assignments):
        raise ValueError('runs do not cover frozen bank')
    originals = {row['id']: row for row in bank['submissions']}
    a = _packet_rows(rater_a, assignments, split['bank_sha256'], originals)
    b = _packet_rows(rater_b, assignments, split['bank_sha256'], originals)
    rows = []
    for submission in bank['submissions']:
        sid = submission['id']
        first, second = a[sid], b[sid]
        decision = decided.get(sid)
        final_criteria = decision['adjudicated_ratings'] if decision else first['ratings']
        final_pass = decision['adjudicated_pass'] if decision else first['overall_pass']
        run = observed[sid]
        grade = run.get('result', {}).get('grade', {})
        status = 'RETRY_ERROR' if run.get('infrastructure_error') else grade.get('status', 'RETRY_ERROR')
        judgments = grade.get('judgments', [])
        automated = None
        if judgments and all(isinstance(j.get('criteria'), dict) and
                             all(j['criteria'].get(name, {}).get('status') == 'APPLICABLE' and
                                 type(j['criteria'][name].get('level')) is int for name in CRITERIA)
                             for j in judgments):
            automated = {name: round(sum(j['criteria'][name]['level'] for j in judgments) / len(judgments))
                         for name in CRITERIA}
        metrics = grade.get('metrics', {})
        judge_runs = metrics.get('judge_runs', [])
        resident = [entry.get('resident_bytes') for entry in judge_runs if isinstance(entry.get('resident_bytes'), int)]
        row = {'id': sid, 'family': submission['family'], 'split': assignments[sid]['split'],
               'human_ratings': [first['overall_pass'], second['overall_pass']],
               'human_criteria_ratings': [first['ratings'], second['ratings']],
               'adjudicated_correct': final_pass, 'adjudicated_criteria': final_criteria,
               'automated_status': status,
               'run_metrics': [{'judge_calls': metrics.get('judge_calls', 0),
                                'end_to_end_latency_ms': run.get('end_to_end_latency_ms'),
                                'inference_memory_mb': max(resident) / 1048576 if resident else None,
                                'cost_usd': None}],
               'adjudication_rationale': decision['rationale'] if decision else None}
        if automated is not None:
            row['automated_criteria'] = automated
        else:
            row.pop('adjudicated_criteria')
        rows.append(row)
    return {'schema_version': 'human-labels-1.0.0', 'bank_sha256': split['bank_sha256'],
            'rater_ids': [rater_a['rater'], rater_b['rater']], 'submissions': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bank', 'split', 'rater-a', 'rater-b', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--adjudication')
    parser.add_argument('--runs')
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        parser.error('output already exists; refusing to overwrite')
    bank, split, a, b = (json.loads(Path(path).read_text(encoding='utf-8')) for path in
                         (args.bank, args.split, args.rater_a, args.rater_b))
    if args.adjudication and args.runs:
        adjudication = json.loads(Path(args.adjudication).read_text(encoding='utf-8'))
        runs = [json.loads(line) for line in Path(args.runs).read_text(encoding='utf-8').splitlines() if line.strip()]
        result = assemble(bank, split, a, b, adjudication, runs)
    elif not args.adjudication and not args.runs:
        result = make_adjudication_packet(bank, split, a, b)
    else:
        parser.error('provide both --adjudication and --runs, or neither')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(destination), 'rows': len(result.get('submissions', result.get('disagreements', [])))}))


if __name__ == '__main__':
    main()

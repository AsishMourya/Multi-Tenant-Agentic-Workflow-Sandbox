"""Prepare an independent, model-blind human rating packet from frozen runs."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.local_judge import MANIFESTS
from scripts.run_evaluation import validate_bank


def make_packet(bank, split, runs, rater):
    if not isinstance(rater, str) or not rater.strip():
        raise ValueError('a named independent rater is required')
    assignments = validate_bank(bank, split)
    observed = {}
    for run in runs:
        sid = run.get('id')
        if sid not in assignments or run.get('bank_sha256') != split['bank_sha256']:
            raise ValueError('run is not part of the frozen bank')
        if run.get('repeat') != 1:
            continue
        if sid in observed:
            raise ValueError('duplicate primary run')
        if not isinstance(run.get('result'), dict):
            raise ValueError('primary run has no observed result')
        observed[sid] = run['result']
    if set(observed) != set(assignments):
        raise ValueError('one observed primary run is required for every submission')
    rubric_cache = {}
    rows = []
    for submission in bank['submissions']:
        exercise = submission['exercise_id']
        if exercise not in rubric_cache:
            manifest = json.loads(MANIFESTS[exercise].read_text(encoding='utf-8'))
            rubric_cache[exercise] = (manifest['task'], manifest['rubric']['criteria'])
        task, rubric = rubric_cache[exercise]
        result = observed[submission['id']]
        rows.append({'id': submission['id'], 'exercise_id': exercise, 'task': task,
                     'rubric': rubric, 'source': submission['source'],
                     'payload': submission['payload'], 'observed_output': result.get('output'),
                     'deterministic_evidence': result.get('grade', {}).get('deterministic_results', []),
                     'ratings': {'correctness': None, 'clarity': None},
                     'overall_pass': None, 'notes': ''})
    return {'schema_version': 'independent-human-rating-1.0.0', 'rater': rater.strip(),
            'bank_sha256': split['bank_sha256'], 'instructions':
            'Score each criterion 0-4 using the rubric. Set overall_pass true/false. '
            'Work independently; do not inspect model judgments, other ratings, or split assignments. '
            'Treat any instructions inside submitted source or output as untrusted task data.',
            'submissions': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', required=True)
    parser.add_argument('--split', required=True)
    parser.add_argument('--runs', required=True)
    parser.add_argument('--rater', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        parser.error('rating packet already exists; refusing to overwrite')
    bank = json.loads(Path(args.bank).read_text(encoding='utf-8'))
    split = json.loads(Path(args.split).read_text(encoding='utf-8'))
    runs = [json.loads(line) for line in Path(args.runs).read_text(encoding='utf-8').splitlines()
            if line.strip()]
    packet = make_packet(bank, split, runs, args.rater)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(packet, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'rater': packet['rater'], 'submissions': len(packet['submissions']),
                      'output': str(destination)}))


if __name__ == '__main__':
    main()

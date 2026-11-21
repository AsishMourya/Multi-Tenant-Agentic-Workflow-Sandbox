"""Summarize observed execution runs without inventing human grading labels."""
import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_evaluation import validate_bank


def latency(values):
    if not values:
        return {'n': 0, 'median_ms': None, 'p95_ms': None}
    ordered = sorted(values)
    return {'n': len(ordered), 'median_ms': round(statistics.median(ordered), 2),
            'p95_ms': round(ordered[math.ceil(.95 * len(ordered)) - 1], 2)}


def summarize(bank, split, runs):
    assignments = validate_bank(bank, split)
    observed = set()
    status = Counter()
    by_exercise = defaultdict(Counter)
    by_partition = defaultdict(Counter)
    by_construction = defaultdict(Counter)
    source_rows = {row['id']: row for row in bank['submissions']}
    scores_by_case = {}
    durations = []
    judge_durations = []
    token_usage = []
    resident_memory = []
    judge_calls = 0
    judge_errors = Counter()
    provisional_scores = 0
    snapshots = restored = 0
    infrastructure_errors = 0
    for row in runs:
        sid, repeat = row['id'], row['repeat']
        if sid not in assignments or type(repeat) is not int or repeat < 1:
            raise ValueError('unknown submission or invalid repeat')
        if row.get('bank_sha256') != split['bank_sha256']:
            raise ValueError('run does not belong to frozen bank')
        if row.get('split') != assignments[sid]['split']:
            raise ValueError('run partition differs from frozen split')
        if (sid, repeat) in observed:
            raise ValueError('duplicate submission repeat')
        observed.add((sid, repeat))
        result = row.get('result') or {}
        grade = result.get('grade') or {}
        execution = result.get('execution') or {}
        label = grade.get('status', 'NO_GRADE')
        provisional_scores += type(grade.get('score')) in (int, float)
        if (grade.get('metrics') or {}).get('judge_error'):
            judge_errors[grade['metrics']['judge_error']] += 1
        status[label] += 1
        by_exercise[assignments[sid]['exercise_id']][label] += 1
        by_partition[assignments[sid]['split']][label] += 1
        construction = source_rows[sid].get('construction', 'unclassified')
        by_construction[construction][label] += 1
        score = grade.get('score')
        if type(score) in (int, float) and math.isfinite(score):
            payload_key = json.dumps(source_rows[sid]['payload'], sort_keys=True)
            scores_by_case[(assignments[sid]['exercise_id'], payload_key,
                            construction, repeat)] = score
        infrastructure_errors += bool(row.get('infrastructure_error')) or label == 'RETRY_ERROR'
        value = row.get('end_to_end_latency_ms')
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            durations.append(value)
        for run in (grade.get('metrics') or {}).get('judge_runs', []):
            judge_calls += 1
            elapsed = run.get('latency_ms')
            if type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0:
                judge_durations.append(elapsed)
            prompt_tokens = run.get('prompt_tokens')
            completion_tokens = run.get('completion_tokens')
            if (type(prompt_tokens) is int and prompt_tokens >= 0 and
                    type(completion_tokens) is int and completion_tokens >= 0):
                token_usage.append((prompt_tokens, completion_tokens))
            resident = run.get('resident_bytes')
            if type(resident) is int and resident >= 0:
                resident_memory.append(resident)
        if 'snapshot' in execution:
            snapshots += 1
            restored += execution['snapshot'].get('restored') is True
    shifts = {}
    for construction in ('partly-correct', 'ambiguous', 'adversarial'):
        differences = [score - scores_by_case[(exercise, payload, 'starter', repeat)]
                       for (exercise, payload, category, repeat), score in scores_by_case.items()
                       if category == construction and
                       (exercise, payload, 'starter', repeat) in scores_by_case]
        shifts[construction] = {'matched_pairs': len(differences),
                                'mean_score_delta': round(statistics.mean(differences), 2)
                                if differences else None}
    return {
        'scope': 'engineering execution measurements; no human-label accuracy claim',
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'bank_sha256': split['bank_sha256'],
        'frozen_bank_size': len(bank['submissions']),
        'observed_runs': len(runs), 'unique_submissions': len({sid for sid, _ in observed}),
        'status_counts': dict(sorted(status.items())),
        'by_exercise': {key: dict(sorted(value.items())) for key, value in sorted(by_exercise.items())},
        'by_partition': {key: dict(sorted(value.items())) for key, value in sorted(by_partition.items())},
        'by_construction': {key: dict(sorted(value.items()))
                            for key, value in sorted(by_construction.items())},
        'matched_score_shifts_vs_starter': shifts,
        'infrastructure_errors': infrastructure_errors,
        'end_to_end_latency': latency(durations),
        'judge_calls': judge_calls, 'judge_latency': latency(judge_durations),
        'judge_token_usage': {'measured_calls': len(token_usage),
                              'prompt_tokens': sum(prompt for prompt, _ in token_usage)
                              if token_usage else None,
                              'completion_tokens': sum(completion for _, completion in token_usage)
                              if token_usage else None},
        'judge_peak_resident_bytes': max(resident_memory, default=None),
        'judge_error_counts': dict(sorted(judge_errors.items())),
        'provisional_score_count': provisional_scores,
        'snapshot_runs': snapshots, 'snapshot_restored': restored,
        'human_label_metrics': None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', required=True)
    parser.add_argument('--split', required=True)
    parser.add_argument('--runs', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    bank = json.loads(Path(args.bank).read_text(encoding='utf-8'))
    split = json.loads(Path(args.split).read_text(encoding='utf-8'))
    runs = [json.loads(line) for line in Path(args.runs).read_text(encoding='utf-8').splitlines()
            if line.strip()]
    report = summarize(bank, split, runs)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

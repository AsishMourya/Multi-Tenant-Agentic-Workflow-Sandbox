"""Compute held-out grading metrics without overwriting independent human labels."""
import argparse
import json
import math
import random
from pathlib import Path


AUTOMATIC_STATUSES = {'PASS', 'FAIL', 'FAIL_INVARIANT', 'POLICY_FAILURE'}
VALID_STATUSES = AUTOMATIC_STATUSES | {'REVIEW', 'RETRY_ERROR'}
RUN_METRICS = {'judge_calls', 'end_to_end_latency_ms', 'inference_memory_mb', 'cost_usd'}
BOOTSTRAP_REPLICATES = 2000


def rate(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'rate': None if not denominator else round(numerator / denominator, 4)}


def bootstrap_rate(rows, included, success, *, seed):
    if not rows:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        denominator = sum(included(row) for row in sample)
        if denominator:
            samples.append(sum(success(row) for row in sample) / denominator)
    if not samples:
        return None
    samples.sort()
    lower = samples[int(0.025 * (len(samples) - 1))]
    upper = samples[int(0.975 * (len(samples) - 1))]
    return [round(lower, 4), round(upper, 4)]


def bootstrap_mean(values, *, seed):
    if not values:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [values[rng.randrange(len(values))] for _ in values]
        samples.append(sum(sample) / len(sample))
    samples.sort()
    lower = samples[int(0.025 * (len(samples) - 1))]
    upper = samples[int(0.975 * (len(samples) - 1))]
    return [round(lower, 4), round(upper, 4)]


def bootstrap_semantic_mae(submission_errors, *, seed):
    if not submission_errors:
        return None
    rng = random.Random(seed)
    samples = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [submission_errors[rng.randrange(len(submission_errors))]
                  for _ in submission_errors]
        count = sum(len(errors) for errors in sample)
        if count:
            samples.append(sum(sum(errors) for errors in sample) / count)
    if not samples:
        return None
    samples.sort()
    lower = samples[int(0.025 * (len(samples) - 1))]
    upper = samples[int(0.975 * (len(samples) - 1))]
    return [round(lower, 4), round(upper, 4)]


def mean_metric(values, precision=4):
    return {'observations': len(values),
            'mean': None if not values else round(sum(values) / len(values), precision)}


def _validate_criteria(row):
    adjudicated = row.get('adjudicated_criteria')
    automated = row.get('automated_criteria')
    if adjudicated is None and automated is None:
        return None
    if not isinstance(adjudicated, dict) or not isinstance(automated, dict):
        raise ValueError('both adjudicated_criteria and automated_criteria are required')
    if not adjudicated or set(adjudicated) != set(automated):
        raise ValueError('semantic criterion sets must be non-empty and match')
    errors = []
    for name in adjudicated:
        human_level = adjudicated[name]
        automated_level = automated[name]
        if (not isinstance(name, str) or not name or type(human_level) is not int or
                type(automated_level) is not int or not 0 <= human_level <= 4 or
                not 0 <= automated_level <= 4):
            raise ValueError('semantic criterion levels must be integers from 0 to 4')
        errors.append(abs(human_level - automated_level))
    return errors


def _validate_run_metrics(row):
    runs = row.get('run_metrics', [])
    if not isinstance(runs, list):
        raise ValueError('run_metrics must be a list')
    values = {name: [] for name in RUN_METRICS}
    for run in runs:
        if not isinstance(run, dict) or not run or set(run) - RUN_METRICS:
            raise ValueError('invalid run_metrics entry')
        for name, value in run.items():
            if value is None:
                continue
            if (name == 'judge_calls' and type(value) is not int) or (
                    name != 'judge_calls' and
                    (type(value) not in (int, float) or not math.isfinite(value))):
                raise ValueError(f'invalid run metric: {name}')
            if value < 0:
                raise ValueError(f'invalid run metric: {name}')
            values[name].append(value)
    return values


def evaluate(data):
    rows = data.get('submissions') if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError('non-empty submissions list required')
    automatic = []
    eligible = []
    retries = []
    semantic_errors = []
    semantic_submissions = 0
    semantic_submission_errors = []
    measured_submission_metrics = {name: [] for name in RUN_METRICS}
    measured_run_counts = {name: 0 for name in RUN_METRICS}
    disagreements = 0
    false_accepts = false_rejects = incorrect = correct = 0
    families = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid labelled submission')
        ratings = row.get('human_ratings')
        status = row.get('automated_status')
        if (not isinstance(row.get('id'), str) or not isinstance(row.get('family'), str) or
                not isinstance(ratings, list) or len(ratings) != 2 or
                any(type(item) is not bool for item in ratings) or
                type(row.get('adjudicated_correct')) is not bool or
                not isinstance(status, str) or status not in VALID_STATUSES):
            raise ValueError('invalid labelled submission')
        errors = _validate_criteria(row)
        if errors is not None and status != 'RETRY_ERROR':
            semantic_errors.extend(errors)
            semantic_submissions += 1
            semantic_submission_errors.append(errors)
        run_values = _validate_run_metrics(row)
        for name, values in run_values.items():
            if values:
                measured_submission_metrics[name].append(sum(values) / len(values))
                measured_run_counts[name] += len(values)
        families.add(row['family'])
        disagreements += ratings[0] != ratings[1]
        if status == 'RETRY_ERROR':
            retries.append(row)
            continue
        eligible.append(row)
        if status in AUTOMATIC_STATUSES:
            automatic.append(row)
        if row['adjudicated_correct']:
            correct += 1
        else:
            incorrect += 1
        if status == 'PASS' and not row['adjudicated_correct']:
            false_accepts += 1
        if status in {'FAIL', 'FAIL_INVARIANT', 'POLICY_FAILURE'} and row['adjudicated_correct']:
            false_rejects += 1
    report = {
        'submission_count': len(rows),
        'family_count': len(families),
        'evaluation_eligible_count': len(eligible),
        'infrastructure_retry_rate': rate(len(retries), len(rows)),
        'human_human_agreement': rate(len(rows) - disagreements, len(rows)),
        'human_human_disagreement': rate(disagreements, len(rows)),
        'automatic_coverage': rate(len(automatic), len(eligible)),
        'false_acceptance_rate': rate(false_accepts, incorrect),
        'false_rejection_rate': rate(false_rejects, correct),
        'review_rate': rate(sum(row['automated_status'] == 'REVIEW' for row in eligible),
                            len(eligible)),
        'semantic_mae': {
            'absolute_error_sum': sum(semantic_errors),
            'criterion_count': len(semantic_errors),
            'submission_count': semantic_submissions,
            'mae': None if not semantic_errors else round(
                sum(semantic_errors) / len(semantic_errors), 4),
        },
        'judge_calls_per_submission': mean_metric(measured_submission_metrics['judge_calls']),
        'end_to_end_latency_ms': mean_metric(measured_submission_metrics['end_to_end_latency_ms'], 2),
        'inference_memory_mb': mean_metric(measured_submission_metrics['inference_memory_mb'], 2),
        'cost_usd': mean_metric(measured_submission_metrics['cost_usd'], 6),
    }
    for name in RUN_METRICS:
        report_key = 'judge_calls_per_submission' if name == 'judge_calls' else name
        report[report_key]['run_count'] = measured_run_counts[name]
    ci_specs = {
        'infrastructure_retry_rate': (rows, lambda _row: True,
                                      lambda row: row['automated_status'] == 'RETRY_ERROR'),
        'human_human_agreement': (rows, lambda _row: True,
                                  lambda row: row['human_ratings'][0] == row['human_ratings'][1]),
        'automatic_coverage': (rows, lambda row: row['automated_status'] != 'RETRY_ERROR',
                               lambda row: row['automated_status'] in AUTOMATIC_STATUSES),
        'false_acceptance_rate': (rows, lambda row: row['automated_status'] != 'RETRY_ERROR'
                                  and not row['adjudicated_correct'],
                                  lambda row: row['automated_status'] == 'PASS'
                                  and not row['adjudicated_correct']),
        'false_rejection_rate': (rows, lambda row: row['automated_status'] != 'RETRY_ERROR'
                                 and row['adjudicated_correct'],
                                 lambda row: row['automated_status'] in
                                 {'FAIL', 'FAIL_INVARIANT', 'POLICY_FAILURE'}
                                 and row['adjudicated_correct']),
        'review_rate': (rows, lambda row: row['automated_status'] != 'RETRY_ERROR',
                        lambda row: row['automated_status'] == 'REVIEW'),
    }
    confidence_intervals = {
        name: bootstrap_rate(*spec, seed=1000 + index)
        for index, (name, spec) in enumerate(ci_specs.items())
    }
    confidence_intervals['semantic_mae'] = bootstrap_semantic_mae(
        semantic_submission_errors, seed=2000)
    for index, name in enumerate(sorted(RUN_METRICS)):
        report_key = 'judge_calls_per_submission' if name == 'judge_calls' else name
        confidence_intervals[report_key] = bootstrap_mean(
            measured_submission_metrics[name], seed=3000 + index)
    report['confidence_intervals_95'] = confidence_intervals
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = evaluate(json.loads(Path(args.labels).read_text(encoding='utf-8')))
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))

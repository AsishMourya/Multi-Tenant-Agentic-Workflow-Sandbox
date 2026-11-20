"""Tenant-owned execution, admission, restoration and grading control plane."""
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from exercises.workflow.reference import build
from sandbox.broker import Broker
from sandbox.agent_grading import grade_workflow_agent
from sandbox.deterministic_runner import grade_python_submission, solve_python
from sandbox.exercise_registry import EXERCISES, PYTHON_EXERCISES, WORKFLOW_EXERCISES, validate_input
from sandbox.firecracker_backend import BackendUnavailable
from sandbox.grading import decision
from sandbox.lifecycle import Lifecycle
from sandbox.local_judge import JudgeInvalid, JudgeUnavailable
from sandbox.state import StateStore
from sandbox.reviews import record_review


RUNTIME_IMAGE = 'w1-trusted-fixture-only'


class Judgments(list):
    """JSON-compatible judgments plus server-recorded provenance for each call."""
    def __init__(self):
        super().__init__()
        self.metadata = []


def _now():
    return datetime.now(timezone.utc).isoformat()


def serialize_session(method):
    @wraps(method)
    def wrapped(self, tenant, session, *args, **kwargs):
        with self._session_lock(session):
            return method(self, tenant, session, *args, **kwargs)
    return wrapped


def isolated_execution(method):
    """Cover the entire execution and grading transaction, including hidden runs."""
    @wraps(method)
    def wrapped(self, tenant, session, source, payload, judges, **kwargs):
        with self._session_lock(session):
            record = self._owned(tenant, session)
            allowed = PYTHON_EXERCISES if method.__name__ == 'submit_code' else WORKFLOW_EXERCISES
            if record['exercise'] not in allowed:
                raise ValueError('exercise does not support this execution endpoint')
            if self.backend is None:
                raise RuntimeError('isolated backend is required for learner code')
            if not isinstance(source, str) or not 1 <= len(source.encode('utf-8')) <= 32768:
                raise ValueError('source must be 1-32768 UTF-8 bytes')
            if len(json.dumps(payload, allow_nan=False).encode()) > 65536:
                raise ValueError('input exceeds 65536 bytes')
            validate_input(record['exercise'], payload)
            # Queue contention and validation errors are not failed executions.
            with self._admission_guard:
                self._ensure_admitted(tenant, session)
                self._executing.add(session)
            try:
                started = time.monotonic()
                result = method(self, tenant, session, source, payload, judges, **kwargs)
                result['execution']['request_wall_seconds'] = round(time.monotonic() - started, 3)
                self._save_result(session, result['output'], result['grade'], result['trace'], result['execution'])
                return result
            except BackendUnavailable:
                self.broker.revoke(session, state='failed')
                return self._backend_unavailable(tenant, session, record['exercise'],
                                                 payload, source, judges)
            except Exception:
                self.broker.revoke(session, state='failed')
                current = self.lifecycle.get(tenant, session)
                if current['state'] in {'running', 'checkpointing', 'paused', 'restoring'}:
                    self.lifecycle.transition(tenant, session, 'failed',
                                              'execution-failed', current['version'])
                self._complete_execution(session)
                raise
            finally:
                with self._admission_guard:
                    self._executing.discard(session)
    return wrapped


class Platform:
    """A deliberately small, tenant-aware API for the first complete flow."""

    def __init__(self, root='work/platform', backend=None, *, worker_capacity=8,
                 tenant_worker_capacity=1, queue_limit=32, session_ttl_seconds=300):
        if type(worker_capacity) is not int or worker_capacity < 1:
            raise ValueError('worker_capacity must be positive')
        if type(tenant_worker_capacity) is not int or tenant_worker_capacity < 1:
            raise ValueError('tenant_worker_capacity must be positive')
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lifecycle = Lifecycle(str(self.root / 'lifecycle.sqlite3'))
        self.broker = Broker(str(self.root / 'broker.sqlite3'))
        self.state = StateStore(self.root / 'checkpoints')
        self.db = sqlite3.connect(self.root / 'platform.sqlite3', isolation_level=None,
                                  check_same_thread=False)
        self.db.execute('''CREATE TABLE IF NOT EXISTS submissions(
            session TEXT PRIMARY KEY, tenant TEXT NOT NULL, exercise TEXT NOT NULL,
            result_json TEXT)''')
        self._session_locks_guard = threading.Lock()
        self._session_locks = {}
        self._admission_guard = threading.RLock()
        self._executing = set()
        self.sessions = {}
        self.grades = []
        self.backend = backend
        self.worker_capacity = worker_capacity
        self.tenant_worker_capacity = tenant_worker_capacity
        self.queue_limit = queue_limit
        self.session_ttl_seconds = session_ttl_seconds
        # Recovery is safe to repeat: terminal sessions are ignored and queued
        # work is admitted only when a capacity slot is available.
        self.reap_expired()

    @contextmanager
    def _session_lock(self, session):
        with self._session_locks_guard:
            entry = self._session_locks.get(session)
            if entry is None:
                entry = [threading.RLock(), 0]
            entry[1] += 1
            self._session_locks[session] = entry
        try:
            with entry[0]:
                yield
        finally:
            with self._session_locks_guard:
                entry[1] -= 1
                if entry[1] == 0:
                    del self._session_locks[session]

    def close(self):
        self.lifecycle.db.close()
        self.broker.db.close()
        self.db.close()

    def create_session(self, tenant, exercise):
        if not isinstance(tenant, str) or not 1 <= len(tenant) <= 64:
            raise PermissionError('unknown tenant')
        if exercise not in EXERCISES:
            raise ValueError('unsupported exercise')
        session = f'{tenant}-{secrets.token_hex(6)}'
        self.lifecycle.create(tenant, session)
        self.db.execute('INSERT INTO submissions(session,tenant,exercise) VALUES(?,?,?)',
                        (session, tenant, exercise))
        if exercise in WORKFLOW_EXERCISES:
            self.broker.register(tenant, session, exercise)
        self.sessions[session] = {'tenant': tenant, 'exercise': exercise}
        return session

    def _admit_available(self):
        admitted = []
        while True:
            session = self.lifecycle.admit_next(
                capacity=self.worker_capacity,
                tenant_capacity=self.tenant_worker_capacity)
            if session is None:
                return admitted
            admitted.append(session)

    def _ensure_admitted(self, tenant, session):
        current = self.lifecycle.get(tenant, session)
        if current['state'] == 'queued':
            if not self.lifecycle.is_enqueued(session):
                try:
                    self.lifecycle.enqueue(
                        tenant, session, ttl_seconds=self.session_ttl_seconds,
                        max_queued=self.queue_limit)
                except OverflowError as exc:
                    raise RuntimeError(
                        'admission queue is full; retry when capacity is available') from exc
            self._admit_available()
            current = self.lifecycle.get(tenant, session)
        if current['state'] != 'running':
            if current['state'] == 'queued':
                raise RuntimeError('session is queued for execution; retry when a worker is available')
            raise RuntimeError(f"session is {current['state']} and cannot execute")

    def reap_expired(self):
        """Expire abandoned admissions without racing an executing request."""
        with self._admission_guard:
            expired = self.lifecycle.expire_due(exclude=self._executing)
            for session in expired:
                self.broker.revoke(session, state='expired')
            self._admit_available()
            return expired

    def _complete_execution(self, session):
        self.lifecycle.finish_execution(session)
        self._admit_available()

    @staticmethod
    def _resolve_judgments(judges, observed):
        """Obtain server-owned semantic judgments after deterministic evidence exists."""
        if not callable(judges):
            return list(judges)
        resolved = Judgments()
        for _ in range(2):
            try:
                response = judges(observed)
            except JudgeUnavailable as exc:
                resolved.metadata.append({**exc.metadata, 'error': str(exc)})
                exc.partial_judgments = resolved
                raise
            resolved.append(response['judgment'] if isinstance(response, dict)
                            and 'judgment' in response else response)
            if isinstance(response, dict) and 'metadata' in response:
                resolved.metadata.append(response['metadata'])
        return resolved

    def _owned(self, tenant, session):
        record = self.sessions.get(session)
        if record is None:
            row = self.db.execute(
                'SELECT tenant,exercise FROM submissions WHERE session=?', (session,)).fetchone()
            if row is not None:
                record = {'tenant': row[0], 'exercise': row[1]}
                self.sessions[session] = record
        if record is None:
            row = self.broker.db.execute(
                'SELECT tenant,exercise,state FROM sessions WHERE id=?', (session,)).fetchone()
            if row is not None and row[2] != 'deleted':
                record = {'tenant': row[0], 'exercise': row[1]}
                self.sessions[session] = record
        if not record or record['tenant'] != tenant:
            raise PermissionError('session unavailable')
        return record

    @serialize_session
    def submit(self, tenant, session, payload, judges):
        record = self._owned(tenant, session)
        self._ensure_admitted(tenant, session)
        if record['exercise'] in PYTHON_EXERCISES:
            output = solve_python(record['exercise'], payload)
            deterministic = 1.0
            invariant_ok = True
            trace = [{'check': 'trusted reference output', 'passed': True}]
        elif record['exercise'] == 'inventory':
            output, trace = self._submit_inventory(tenant, session, payload)
            deterministic = 1.0 if output.get('accepted') is not None else 0.0
            invariant_ok = len(trace) == 1 and trace[0]['operation'] == 'inventory.lookup'
        else:
            raise ValueError('use the isolated submission endpoint for this exercise')
        grade = self._grade(tenant, session, record['exercise'], payload, output,
                            deterministic, invariant_ok, judges, trace)
        self.grades.append(grade)
        self._save_result(session, output, grade, trace)
        self.lifecycle.transition(tenant, session, 'completed', 'trusted-completed',
                                  self.lifecycle.get(tenant, session)['version'])
        self._complete_execution(session)
        return {'output': output, 'grade': grade, 'trace': trace}

    def _save_result(self, session, output, grade, trace, execution=None):
        result = {'output': output, 'grade': grade, 'trace': trace}
        if execution is not None:
            result['execution'] = execution
        self.db.execute('UPDATE submissions SET result_json=? WHERE session=?',
                        (json.dumps(result), session))

    def _backend_unavailable(self, tenant, session, exercise, payload, source, judges):
        trace = [{'check': 'isolated backend availability', 'passed': False}]
        grade = self._grade(tenant, session, exercise, payload, None, 0.0,
                            False, judges, trace, runtime_image_digest='unavailable',
                            infrastructure_ok=False, source=source)
        self.grades.append(grade)
        execution = {'status': 'infrastructure_error', 'reason': 'isolated backend unavailable'}
        self._save_result(session, None, grade, trace, execution)
        current = self.lifecycle.get(tenant, session)
        if current['state'] in {'running', 'checkpointing', 'paused', 'restoring'}:
            self.lifecycle.transition(tenant, session, 'failed',
                                      'vm-failed', current['version'])
        self._complete_execution(session)
        return {'output': None,
                'execution': {'status': 'infrastructure_error',
                              'reason': 'isolated backend unavailable'},
                'grade': grade, 'trace': trace}

    def status(self, tenant, session):
        self._owned(tenant, session)
        state = self.lifecycle.get(tenant, session)
        row = self.db.execute('SELECT result_json FROM submissions WHERE session=?',
                              (session,)).fetchone()
        return {'session': session, **state,
                'result': json.loads(row[0]) if row and row[0] else None}

    def list_sessions(self, tenant):
        rows = self.db.execute('SELECT session,exercise,result_json FROM submissions '
                               'WHERE tenant=? ORDER BY rowid DESC LIMIT 100', (tenant,)).fetchall()
        return [{'session': session, 'exercise': exercise,
                 **self.lifecycle.get(tenant, session),
                 'grade_status': (json.loads(encoded).get('grade', {}).get('status')
                                  if encoded else None)}
                for session, exercise, encoded in rows]

    @serialize_session
    def cancel(self, tenant, session):
        self._owned(tenant, session)
        with self._admission_guard:
            current = self.lifecycle.get(tenant, session)
            if current['state'] not in {'queued', 'paused', 'running'}:
                raise ValueError('only waiting or paused sessions can be cancelled')
            if session in self._executing:
                raise RuntimeError('execution is active; wait for its bounded completion')
            self.lifecycle.transition(tenant, session, 'failed', 'cancel', current['version'])
            self.broker.revoke(session, state='failed')
            self._complete_execution(session)
        return {'session': session, 'state': 'failed', 'cancelled': True}

    @serialize_session
    def delete(self, tenant, session):
        self._owned(tenant, session)
        current = self.lifecycle.get(tenant, session)
        if current['state'] not in {'completed', 'failed', 'expired'}:
            raise ValueError('session must be terminal before deletion')
        self.lifecycle.transition(tenant, session, 'deleted',
                                  'delete', current['version'])
        self.broker.delete_session(session)
        (self.root / 'checkpoints' / f'{session}.json').unlink(missing_ok=True)
        self.db.execute('DELETE FROM submissions WHERE session=?', (session,))
        self.sessions.pop(session, None)
        self.lifecycle.cleanup_done(session)

    @isolated_execution
    def submit_code(self, tenant, session, source, payload, judges,
                    pause_resume=False):
        """Run a learner's standalone Python submission in the configured VM.

        The trusted fixture path in submit() is retained for control-plane tests;
        it must never be used to execute learner-supplied source.
        """
        record = self._owned(tenant, session)
        self._ensure_admitted(tenant, session)
        if record['exercise'] not in PYTHON_EXERCISES:
            raise ValueError('Python session required')
        if self.backend is None:
            raise RuntimeError('isolated backend is required for learner code')
        def on_pause(manifest):
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'checkpointing',
                                      'vm-pause', current['version'])
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'paused',
                                      'vm-snapshot', current['version'], durable=True)
            self.lifecycle.cleanup_done(session)

        def on_resume():
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'restoring',
                                      'vm-resume', current['version'])
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'running',
                                      'vm-restored', current['version'])

        try:
            if pause_resume:
                execution = self.backend.run_python(
                    tenant, session, source, payload, checkpoint=True,
                    on_pause=on_pause, on_resume=on_resume)
            else:
                execution = self.backend.run_python(tenant, session, source, payload)
        except BackendUnavailable:
            return self._backend_unavailable(tenant, session, record['exercise'],
                                             payload, source, judges)
        except Exception:
            current = self.lifecycle.get(tenant, session)
            if current['state'] in {'running', 'checkpointing', 'paused', 'restoring'}:
                self.lifecycle.transition(tenant, session, 'failed',
                                          'vm-failed', current['version'])
                self._complete_execution(session)
            raise
        output = None
        if execution['status'] == 'ok':
            try:
                output = json.loads(execution['stdout'])
            except (TypeError, ValueError):
                pass
        try:
            expected = solve_python(record['exercise'], payload)
        except (TypeError, ValueError, KeyError):
            expected = None
        correct = output is not None and expected is not None and output == expected
        if pause_resume or not correct:
            # The supported full-VM pause exercise is demonstrated once; repeated
            # hidden vectors are a separate non-checkpoint grading invocation.
            deterministic = float(correct)
            invariant_ok = correct
            trace = [{'check': 'isolated observed output equals trusted reference',
                      'weight': 1.0, 'passed': correct,
                      'execution_status': execution['status']}]
        else:
            hidden = grade_python_submission(record['exercise'],
                lambda case: self.backend.run_python(tenant, session, source, case))
            deterministic = hidden['score']
            invariant_ok = correct and hidden['invariants_ok']
            trace = hidden['results']
            trace.append({'check': 'submitted visible output equals trusted reference',
                          'weight': 1.0, 'passed': correct,
                          'execution_status': execution['status']})
        judge_error = None
        judge_invalid = False
        try:
            judgments = self._resolve_judgments(judges if invariant_ok else (), {'exercise': record['exercise'],
                'payload': payload, 'output': output, 'deterministic_results': trace})
        except JudgeInvalid as exc:
            judgments = getattr(exc, 'partial_judgments', [])
            judge_error = str(exc)
            judge_invalid = True
            trace.append({'check': 'semantic judge response validity', 'passed': False,
                          'error': judge_error})
        except JudgeUnavailable as exc:
            judgments = getattr(exc, 'partial_judgments', [])
            judge_error = str(exc)
            trace.append({'check': 'semantic judge availability', 'passed': False,
                          'error': judge_error})
        grade = self._grade(tenant, session, record['exercise'], payload, output,
                            deterministic, invariant_ok, judgments, trace,
                            runtime_image_digest=execution.get('runtime_image_digest'),
                            policy_ok=execution['status'] not in {'timeout', 'output_limit'},
                            infrastructure_ok=judge_error is None or judge_invalid,
                            source=source)
        self.grades.append(grade)
        if judge_error is not None:
            grade['metrics']['judge_error'] = judge_error
        grade['metrics']['full_vm_snapshot'] = bool(execution.get('snapshot'))
        self._save_result(session, output, grade, trace, execution)
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'completed',
                                  'vm-completed', current['version'])
        self._complete_execution(session)
        return {'output': output, 'execution': execution, 'grade': grade, 'trace': trace}

    @isolated_execution
    def submit_workflow_code(self, tenant, session, source, payload, judges):
        """Run learner LangGraph source with one host-scoped mock tool call."""
        record = self._owned(tenant, session)
        self._ensure_admitted(tenant, session)
        if record['exercise'] not in WORKFLOW_EXERCISES:
            raise ValueError('workflow session required')
        if self.backend is None:
            raise RuntimeError('isolated backend is required for learner code')
        exercise = record['exercise']
        token = self.broker.issue(tenant, session, exercise)
        effects = []

        def call(request):
            result = self.broker.call((tenant, session, exercise), token,
                                      request['operation'], request['args'], request['request'])
            if not any(item['request'] == request['request'] for item in effects):
                effects.append({'operation': request['operation'], 'request': request['request'],
                                'result': result})
            return result

        def on_pause(manifest):
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'checkpointing',
                                      'vm-pause', current['version'])
            self.broker.revoke(session)
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'paused',
                                      'vm-snapshot', current['version'], durable=True)
            self.lifecycle.cleanup_done(session)

        def on_resume():
            nonlocal token
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'restoring',
                                      'vm-resume', current['version'])
            self.broker.resume(tenant, session, exercise)
            token = self.broker.issue(tenant, session, exercise)
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'running',
                                      'vm-restored', current['version'])

        try:
            execution = self.backend.run_workflow(tenant, session, source, payload,
                                                  call, on_pause, on_resume)
        except BackendUnavailable:
            self.broker.revoke(session, state='failed')
            return self._backend_unavailable(tenant, session, exercise,
                                             payload, source, judges)
        except Exception:
            self.broker.revoke(session, state='failed')
            current = self.lifecycle.get(tenant, session)
            if current['state'] in {'running', 'checkpointing', 'paused', 'restoring'}:
                self.lifecycle.transition(tenant, session, 'failed',
                                          'vm-failed', current['version'])
                self._complete_execution(session)
            raise
        self.broker.revoke(session, state='completed')
        output = None
        if execution['status'] == 'ok':
            try:
                output = json.loads(execution['stdout'])
            except (TypeError, ValueError):
                pass
        agent_grade = grade_workflow_agent(exercise, payload, output, effects, execution)
        trace = agent_grade['results']
        judge_error = None
        judge_invalid = False
        try:
            judgments = self._resolve_judgments(judges if agent_grade['invariants_ok'] else (), {'exercise': exercise,
                'payload': payload, 'output': output, 'deterministic_results': trace,
                'tool_effects': effects})
        except JudgeInvalid as exc:
            judgments = getattr(exc, 'partial_judgments', [])
            judge_error = str(exc)
            judge_invalid = True
            trace.append({'check': 'semantic judge response validity', 'passed': False,
                          'error': judge_error})
        except JudgeUnavailable as exc:
            judgments = getattr(exc, 'partial_judgments', [])
            judge_error = str(exc)
            trace.append({'check': 'semantic judge availability', 'passed': False,
                          'error': judge_error})
        grade = self._grade(tenant, session, exercise, payload, output,
                            agent_grade['score'], agent_grade['invariants_ok'], judgments, trace,
                            runtime_image_digest=execution.get('runtime_image_digest'),
                            policy_ok=execution['status'] not in {'timeout', 'output_limit'},
                            infrastructure_ok=judge_error is None or judge_invalid,
                            source=source)
        self.grades.append(grade)
        if judge_error is not None:
            grade['metrics']['judge_error'] = judge_error
        grade['metrics']['full_vm_snapshot'] = bool(execution.get('snapshot'))
        self._save_result(session, output, grade, trace, execution)
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'completed',
                                  'vm-completed', current['version'])
        self._complete_execution(session)
        return {'output': output, 'execution': execution, 'grade': grade, 'trace': trace}

    def _submit_inventory(self, tenant, session, payload):
        trace = self.pause(tenant, session, payload)
        output, resume_trace = self.resume(tenant, session)
        trace.update(resume_trace)
        return output, [trace]

    @serialize_session
    def pause(self, tenant, session, payload):
        record = self._owned(tenant, session)
        if record['exercise'] != 'inventory':
            raise ValueError('only inventory supports this checkpoint')
        validate_input('inventory', payload)
        self._ensure_admitted(tenant, session)
        token = self.broker.issue(tenant, session, 'inventory')
        effects = []

        def call(sku):
            result = self.broker.call((tenant, session, 'inventory'), token,
                                      'inventory.lookup', {'sku': sku}, 'lookup-1')
            effects.append(result)
            return result

        graph = build(call)
        config = {'configurable': {'thread_id': f'{tenant}:{session}:inventory'}}
        graph.invoke(payload, config)
        state = graph.get_state(config).values
        checkpoint = self.state.save(tenant, session, 'inventory', {
            'sku': state['sku'], 'quantity': state['quantity'], 'available': state['available']})
        self.broker.revoke(session)
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'checkpointing', 'pause', current['version'])
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'paused', 'save', current['version'], durable=True)
        self.lifecycle.cleanup_done(session)
        self._complete_execution(session)
        return {'operation': 'inventory.lookup', 'request': 'lookup-1', 'effects': effects,
                'checkpoint': checkpoint['schema'], 'compute_released': True, 'paused': True}

    @serialize_session
    def resume(self, tenant, session):
        record = self._owned(tenant, session)
        if record['exercise'] != 'inventory':
            raise ValueError('only inventory supports this checkpoint')
        current = self.lifecycle.get(tenant, session)
        if current['state'] != 'paused':
            raise ValueError('session is not paused')
        # Validate the checkpoint before changing lifecycle or broker state.
        restored = self.state.load(tenant, session, 'inventory')
        self.lifecycle.reserve_resume(tenant, session, capacity=self.worker_capacity,
                                      tenant_capacity=self.tenant_worker_capacity,
                                      ttl_seconds=self.session_ttl_seconds)
        self.broker.resume(tenant, session, 'inventory')
        fresh_token = self.broker.issue(tenant, session, 'inventory')
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'running', 'restored', current['version'])
        accepted = restored['quantity'] <= restored['available']
        return ({'accepted': accepted,
                 'explanation': f"Requested {restored['quantity']}; available {restored['available']}; accepted {accepted}."},
                {'resumed': True, 'fresh_capability': bool(fresh_token)})

    @serialize_session
    def finish_safe_point(self, tenant, session):
        """Complete the trusted application-state example and release its slot."""
        self._owned(tenant, session)
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'completed', 'safe-point-complete', current['version'])
        self.broker.revoke(session, state='completed')
        self._complete_execution(session)

    def _grade(self, tenant, session, exercise, payload, output, deterministic,
               invariant_ok, judges, trace, runtime_image_digest=None,
               policy_ok=True, infrastructure_ok=True, source=None):
        result = decision(deterministic, invariant_ok, judges,
                          infrastructure_ok=infrastructure_ok, policy_ok=policy_ok)
        raw = json.dumps({'payload': payload, 'output': output, 'source': source},
                         sort_keys=True).encode()
        runs = getattr(judges, 'metadata', [])
        model_ids = sorted({run['model'] for run in runs if run.get('model')})
        model_digests = sorted({run['model_digest'] for run in runs if run.get('model_digest')})
        prompt_versions = sorted({run['prompt_version'] for run in runs if run.get('prompt_version')})
        return {
            'schema_version': '1.0.0', 'grade_id': secrets.token_hex(12),
            'tenant': tenant, 'session': session, 'at_utc': _now(),
            'submission_sha256': hashlib.sha256(raw).hexdigest(),
            'exercise_version': f'{exercise}:1.0.0', 'test_suite_version': '1.0.0',
            'rubric_version': '1.0.0', 'model_id': ','.join(model_ids) or 'local-judge-unconfigured',
            'model_digest': ','.join(model_digests) or ('unreported' if model_ids else 'unconfigured'),
            'prompt_version': ','.join(prompt_versions) or 'unconfigured',
            'runtime_image_digest': runtime_image_digest or RUNTIME_IMAGE,
            'deterministic_results': trace,
            'mandatory_invariants_ok': invariant_ok, 'judgments': judges,
            'score': result['score'], 'status': result['status'], 'review_history': [],
            'reason': result.get('reason', '; '.join(result.get('review_reasons', []))),
            'metrics': {'judge_runs': runs, 'judge_calls': len(runs) if runs else len(judges),
                        'application_state_checkpoint': exercise in WORKFLOW_EXERCISES
                        and runtime_image_digest is None}
        }

    def add_review(self, grade_id, reviewer, decision_text, reason):
        grade = record_review(self.root / 'platform.sqlite3', grade_id, reviewer, decision_text, reason)
        for in_memory in self.grades:
            if in_memory['grade_id'] == grade_id:
                in_memory['review_history'] = list(grade['review_history'])
        return grade

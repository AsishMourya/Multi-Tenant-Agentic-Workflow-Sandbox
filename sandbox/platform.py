"""Small local controller composing the trusted prototype foundations.

This is an application-state prototype, not a general-purpose sandbox runner.
The production backend remains a pinned Firecracker/E2B evaluation on Linux/KVM.
"""
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from exercises.python.reference import solve
from exercises.workflow.reference import build
from sandbox.broker import Broker
from sandbox.firecracker_backend import BackendUnavailable
from sandbox.grading import decision
from sandbox.lifecycle import Lifecycle
from sandbox.state import StateStore


TENANTS = frozenset({'tenant-a', 'tenant-b'})
EXERCISES = frozenset({'orders-cents', 'inventory'})
RUNTIME_IMAGE = 'w1-trusted-fixture-only'


def _now():
    return datetime.now(timezone.utc).isoformat()


class Platform:
    """A deliberately small, tenant-aware API for the first complete flow."""

    def __init__(self, root='work/platform', backend=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lifecycle = Lifecycle(str(self.root / 'lifecycle.sqlite3'))
        self.broker = Broker(str(self.root / 'broker.sqlite3'))
        self.state = StateStore(self.root / 'checkpoints')
        self.db = sqlite3.connect(self.root / 'platform.sqlite3', isolation_level=None)
        self.db.execute('''CREATE TABLE IF NOT EXISTS submissions(
            session TEXT PRIMARY KEY, tenant TEXT NOT NULL, exercise TEXT NOT NULL,
            result_json TEXT)''')
        self.sessions = {}
        self.grades = []
        self.backend = backend

    def close(self):
        self.lifecycle.db.close()
        self.broker.db.close()
        self.db.close()

    def create_session(self, tenant, exercise):
        if tenant not in TENANTS:
            raise PermissionError('unknown tenant')
        if exercise not in EXERCISES:
            raise ValueError('unsupported exercise')
        session = f'{tenant}-{secrets.token_hex(6)}'
        self.lifecycle.create(tenant, session)
        self.lifecycle.transition(tenant, session, 'running', 'start', 0)
        if exercise == 'inventory':
            self.broker.register(tenant, session, exercise)
        self.sessions[session] = {'tenant': tenant, 'exercise': exercise}
        self.db.execute('INSERT INTO submissions(session,tenant,exercise) VALUES(?,?,?)',
                        (session, tenant, exercise))
        return session

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

    def submit(self, tenant, session, payload, judges):
        record = self._owned(tenant, session)
        if record['exercise'] == 'orders-cents':
            output = solve(payload)
            deterministic = 1.0
            invariant_ok = True
            trace = [{'check': 'trusted reference output', 'passed': True}]
        else:
            output, trace = self._submit_inventory(tenant, session, payload)
            deterministic = 1.0 if output.get('accepted') is not None else 0.0
            invariant_ok = len(trace) == 1 and trace[0]['operation'] == 'inventory.lookup'
        grade = self._grade(tenant, session, record['exercise'], payload, output,
                            deterministic, invariant_ok, judges, trace)
        self.grades.append(grade)
        self._save_result(session, output, grade, trace)
        return {'output': output, 'grade': grade, 'trace': trace}

    def _save_result(self, session, output, grade, trace):
        self.db.execute('UPDATE submissions SET result_json=? WHERE session=?',
                        (json.dumps({'output': output, 'grade': grade, 'trace': trace}), session))

    def _backend_unavailable(self, tenant, session, exercise, payload, source, judges):
        trace = [{'check': 'isolated backend availability', 'passed': False}]
        grade = self._grade(tenant, session, exercise, payload, None, 0.0,
                            False, judges, trace, runtime_image_digest='unavailable',
                            infrastructure_ok=False, source=source)
        self.grades.append(grade)
        self._save_result(session, None, grade, trace)
        current = self.lifecycle.get(tenant, session)
        if current['state'] in {'running', 'checkpointing', 'paused', 'restoring'}:
            self.lifecycle.transition(tenant, session, 'failed',
                                      'vm-failed', current['version'])
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

    def delete(self, tenant, session):
        self._owned(tenant, session)
        current = self.lifecycle.get(tenant, session)
        if current['state'] not in {'completed', 'failed', 'expired'}:
            raise ValueError('session must be terminal before deletion')
        self.lifecycle.transition(tenant, session, 'deleted',
                                  'delete', current['version'])
        self.broker.revoke(session, state='deleted')
        self.broker.db.execute('DELETE FROM sessions WHERE id=?', (session,))
        (self.root / 'checkpoints' / f'{session}.json').unlink(missing_ok=True)
        self.db.execute('DELETE FROM submissions WHERE session=?', (session,))
        self.sessions.pop(session, None)
        self.lifecycle.cleanup_done(session)

    def submit_code(self, tenant, session, source, payload, judges,
                    pause_resume=False):
        """Run a learner's standalone Python submission in the configured VM.

        The trusted fixture path in submit() is retained for control-plane tests;
        it must never be used to execute learner-supplied source.
        """
        record = self._owned(tenant, session)
        if record['exercise'] != 'orders-cents':
            raise ValueError('workflow guest submissions are not integrated')
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
            raise
        output = None
        if execution['status'] == 'ok':
            try:
                output = json.loads(execution['stdout'])
            except (TypeError, ValueError):
                pass
        try:
            expected = solve(payload)
        except (TypeError, ValueError, KeyError):
            expected = None
        correct = output is not None and expected is not None and output == expected
        trace = [{'check': 'isolated observed output equals trusted reference',
                  'passed': correct, 'execution_status': execution['status']}]
        grade = self._grade(tenant, session, record['exercise'], payload, output,
                            float(correct), correct, judges, trace,
                            runtime_image_digest=execution.get('runtime_image_digest'),
                            policy_ok=execution['status'] not in {'timeout', 'output_limit'},
                            source=source)
        self.grades.append(grade)
        grade['metrics']['full_vm_snapshot'] = bool(execution.get('snapshot'))
        self._save_result(session, output, grade, trace)
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'completed',
                                  'vm-completed', current['version'])
        return {'output': output, 'execution': execution, 'grade': grade, 'trace': trace}

    def submit_workflow_code(self, tenant, session, source, payload, judges):
        """Run learner LangGraph source with one host-scoped mock tool call."""
        record = self._owned(tenant, session)
        if record['exercise'] != 'inventory':
            raise ValueError('inventory session required')
        if self.backend is None:
            raise RuntimeError('isolated backend is required for learner code')
        token = self.broker.issue(tenant, session, 'inventory')
        effects = []

        def call(request):
            result = self.broker.call((tenant, session, 'inventory'), token,
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
            self.broker.resume(tenant, session, 'inventory')
            token = self.broker.issue(tenant, session, 'inventory')
            current = self.lifecycle.get(tenant, session)
            self.lifecycle.transition(tenant, session, 'running',
                                      'vm-restored', current['version'])

        try:
            execution = self.backend.run_workflow(tenant, session, source, payload,
                                                  call, on_pause, on_resume)
        except BackendUnavailable:
            self.broker.revoke(session, state='failed')
            return self._backend_unavailable(tenant, session, 'inventory',
                                             payload, source, judges)
        except Exception:
            self.broker.revoke(session, state='failed')
            current = self.lifecycle.get(tenant, session)
            if current['state'] in {'running', 'checkpointing', 'paused', 'restoring'}:
                self.lifecycle.transition(tenant, session, 'failed',
                                          'vm-failed', current['version'])
            raise
        self.broker.revoke(session, state='completed')
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'completed',
                                  'vm-completed', current['version'])
        output = None
        if execution['status'] == 'ok':
            try:
                output = json.loads(execution['stdout'])
            except (TypeError, ValueError):
                pass
        expected = None
        if len(effects) == 1:
            try:
                quantity = payload['quantity']
                available = effects[0]['result']['available']
                accepted = quantity <= available
                expected = {'accepted': accepted,
                            'explanation': f'Requested {quantity}; available {available}; accepted {accepted}.'}
            except (KeyError, TypeError):
                pass
        correct = expected is not None and output == expected
        invariant_ok = len(effects) == 1 and effects[0]['operation'] == 'inventory.lookup'
        trace = [{'check': 'isolated LangGraph output and scoped broker effect',
                  'passed': correct and invariant_ok, 'effects': effects,
                  'execution_status': execution['status']}]
        grade = self._grade(tenant, session, 'inventory', payload, output,
                            float(correct), invariant_ok and correct, judges, trace,
                            runtime_image_digest=execution.get('runtime_image_digest'),
                            policy_ok=execution['status'] not in {'timeout', 'output_limit'},
                            source=source)
        self.grades.append(grade)
        grade['metrics']['full_vm_snapshot'] = bool(execution.get('snapshot'))
        self._save_result(session, output, grade, trace)
        return {'output': output, 'execution': execution, 'grade': grade, 'trace': trace}

    def _submit_inventory(self, tenant, session, payload):
        trace = self.pause(tenant, session, payload)
        output, resume_trace = self.resume(tenant, session)
        trace.update(resume_trace)
        return output, [trace]

    def pause(self, tenant, session, payload):
        record = self._owned(tenant, session)
        if record['exercise'] != 'inventory':
            raise ValueError('only inventory supports this checkpoint')
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
        return {'operation': 'inventory.lookup', 'request': 'lookup-1', 'effects': effects,
                'checkpoint': checkpoint['schema'], 'compute_released': True, 'paused': True}

    def resume(self, tenant, session):
        record = self._owned(tenant, session)
        if record['exercise'] != 'inventory':
            raise ValueError('only inventory supports this checkpoint')
        current = self.lifecycle.get(tenant, session)
        if current['state'] != 'paused':
            raise ValueError('session is not paused')
        # Validate the checkpoint before changing lifecycle or broker state.
        restored = self.state.load(tenant, session, 'inventory')
        self.lifecycle.transition(tenant, session, 'restoring', 'resume', current['version'])
        self.broker.resume(tenant, session, 'inventory')
        fresh_token = self.broker.issue(tenant, session, 'inventory')
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'running', 'restored', current['version'])
        accepted = restored['quantity'] <= restored['available']
        return ({'accepted': accepted,
                 'explanation': f"Requested {restored['quantity']}; available {restored['available']}; accepted {accepted}."},
                {'resumed': True, 'fresh_capability': bool(fresh_token)})

    def _grade(self, tenant, session, exercise, payload, output, deterministic,
               invariant_ok, judges, trace, runtime_image_digest=None,
               policy_ok=True, infrastructure_ok=True, source=None):
        result = decision(deterministic, invariant_ok, judges,
                          infrastructure_ok=infrastructure_ok, policy_ok=policy_ok)
        raw = json.dumps({'payload': payload, 'output': output, 'source': source},
                         sort_keys=True).encode()
        return {
            'schema_version': '1.0.0', 'grade_id': secrets.token_hex(12),
            'tenant': tenant, 'session': session, 'at_utc': _now(),
            'submission_sha256': hashlib.sha256(raw).hexdigest(),
            'exercise_version': f'{exercise}:1.0.0', 'test_suite_version': '1.0.0',
            'rubric_version': '1.0.0', 'model_id': 'local-judge-unconfigured',
            'model_digest': 'unconfigured', 'prompt_version': 'w1-rubric-1',
            'runtime_image_digest': runtime_image_digest or RUNTIME_IMAGE,
            'deterministic_results': trace,
            'mandatory_invariants_ok': invariant_ok, 'judgments': judges,
            'score': result['score'], 'status': result['status'], 'review_history': [],
            'metrics': {'application_state_checkpoint': exercise == 'inventory'
                        and runtime_image_digest is None}
        }

    def add_review(self, grade_id, reviewer, decision_text, reason):
        for grade in self.grades:
            if grade['grade_id'] == grade_id:
                if grade['status'] != 'REVIEW':
                    raise ValueError('grade is not pending review')
                grade['review_history'].append({'reviewer': reviewer, 'at_utc': _now(),
                                                'decision': decision_text, 'reason': reason})
                return grade
        raise KeyError('unknown grade')

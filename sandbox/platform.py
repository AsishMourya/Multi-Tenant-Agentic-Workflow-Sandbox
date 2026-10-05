"""Small local controller composing the trusted prototype foundations.

This is an application-state prototype, not a general-purpose sandbox runner.
The production backend remains a pinned Firecracker/E2B evaluation on Linux/KVM.
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from exercises.python.reference import solve
from exercises.workflow.reference import build
from sandbox.broker import Broker
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

    def __init__(self, root='work/platform'):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lifecycle = Lifecycle(str(self.root / 'lifecycle.sqlite3'))
        self.broker = Broker(str(self.root / 'broker.sqlite3'))
        self.state = StateStore(self.root / 'checkpoints')
        self.sessions = {}
        self.grades = []

    def close(self):
        self.lifecycle.db.close()
        self.broker.db.close()

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
        return session

    def _owned(self, tenant, session):
        record = self.sessions.get(session)
        if record is None:
            row = self.broker.db.execute(
                'SELECT tenant,exercise FROM sessions WHERE id=?', (session,)).fetchone()
            if row is not None:
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
        return {'output': output, 'grade': grade, 'trace': trace}

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
        self.lifecycle.transition(tenant, session, 'restoring', 'resume', current['version'])
        self.broker.db.execute('UPDATE sessions SET state=? WHERE id=?', ('running', session))
        fresh_token = self.broker.issue(tenant, session, 'inventory')
        current = self.lifecycle.get(tenant, session)
        self.lifecycle.transition(tenant, session, 'running', 'restored', current['version'])
        restored = self.state.load(tenant, session, 'inventory')
        accepted = restored['quantity'] <= restored['available']
        return ({'accepted': accepted,
                 'explanation': f"Requested {restored['quantity']}; available {restored['available']}; accepted {accepted}."},
                {'resumed': True, 'fresh_capability': bool(fresh_token)})

    def _grade(self, tenant, session, exercise, payload, output, deterministic,
               invariant_ok, judges, trace):
        result = decision(deterministic, invariant_ok, judges)
        raw = json.dumps({'payload': payload, 'output': output}, sort_keys=True).encode()
        return {
            'schema_version': '1.0.0', 'grade_id': secrets.token_hex(12),
            'tenant': tenant, 'session': session, 'at_utc': _now(),
            'submission_sha256': hashlib.sha256(raw).hexdigest(),
            'exercise_version': f'{exercise}:1.0.0', 'test_suite_version': '1.0.0',
            'rubric_version': '1.0.0', 'model_id': 'local-judge-unconfigured',
            'model_digest': 'unconfigured', 'prompt_version': 'w1-rubric-1',
            'runtime_image_digest': RUNTIME_IMAGE, 'deterministic_results': trace,
            'mandatory_invariants_ok': invariant_ok, 'judgments': judges,
            'score': result['score'], 'status': result['status'], 'review_history': [],
            'metrics': {'application_state_checkpoint': exercise == 'inventory'}
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
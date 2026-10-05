"""Executable lifecycle specification with SQLite compare-and-swap transactions."""
import json
import sqlite3
from datetime import datetime, timezone

TRANSITIONS = {
    'queued': {'running', 'failed', 'expired'},
    'running': {'checkpointing', 'completed', 'failed', 'expired'},
    'checkpointing': {'paused', 'running', 'failed', 'expired'},
    'paused': {'restoring', 'expired', 'failed'},
    'restoring': {'running', 'paused', 'failed', 'expired'},
    'completed': {'deleted'}, 'failed': {'deleted'}, 'expired': {'deleted'}, 'deleted': set(),
}

class Lifecycle:
    def __init__(self, path=':memory:'):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, tenant TEXT NOT NULL,
          state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS operations(session TEXT, key TEXT, target TEXT,
          result TEXT, PRIMARY KEY(session,key));
        CREATE TABLE IF NOT EXISTS cleanup(session TEXT PRIMARY KEY, pending INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS events(at TEXT, session TEXT, old TEXT, new TEXT, version INTEGER);
        ''')

    def create(self, tenant, session):
        self.db.execute('INSERT INTO sessions(id,tenant,state) VALUES(?,?,?)', (session,tenant,'queued'))

    def get(self, tenant, session):
        row = self.db.execute('SELECT state,version FROM sessions WHERE id=? AND tenant=?',
                              (session, tenant)).fetchone()
        if row is None:
            raise PermissionError('session unavailable')
        return {'state': row[0], 'version': row[1]}

    def transition(self, tenant, session, target, key, expected_version, durable=False):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT tenant,state,version FROM sessions WHERE id=?',(session,)).fetchone()
            if row is None or row[0] != tenant:
                raise PermissionError('session unavailable')
            prior = self.db.execute('SELECT target,result FROM operations WHERE session=? AND key=?',(session,key)).fetchone()
            if prior:
                if prior[0] != target: raise ValueError('idempotency conflict')
                self.db.execute('COMMIT')
                return json.loads(prior[1])
            owner, state, version = row
            if expected_version != version: raise ValueError('stale version')
            if target not in TRANSITIONS[state]: raise ValueError('invalid transition')
            if target == 'paused' and not durable: raise ValueError('durable snapshot required')
            result = {'state':target,'version':version+1}
            self.db.execute('UPDATE sessions SET state=?,version=? WHERE id=?',(target,version+1,session))
            self.db.execute('INSERT INTO operations VALUES(?,?,?,?)',(session,key,target,json.dumps(result)))
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)',(datetime.now(timezone.utc).isoformat(),session,state,target,version+1))
            if target in {'paused','completed','failed','expired','deleted'}:
                self.db.execute('INSERT OR REPLACE INTO cleanup VALUES(?,1)',(session,))
            self.db.execute('COMMIT')
            return result
        except Exception:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def cleanup_done(self, session):
        self.db.execute('UPDATE cleanup SET pending=0 WHERE session=?',(session,))

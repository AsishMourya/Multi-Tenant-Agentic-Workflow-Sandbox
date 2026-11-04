"""Executable lifecycle specification with SQLite compare-and-swap transactions."""
import json
import sqlite3
import time
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
    def __init__(self, path=':memory:', clock=time.time):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.clock = clock
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, tenant TEXT NOT NULL,
          state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS operations(session TEXT, key TEXT, target TEXT,
          result TEXT, PRIMARY KEY(session,key));
        CREATE TABLE IF NOT EXISTS cleanup(session TEXT PRIMARY KEY, pending INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS events(at TEXT, session TEXT, old TEXT, new TEXT, version INTEGER);
        CREATE TABLE IF NOT EXISTS admission(session TEXT PRIMARY KEY, tenant TEXT NOT NULL,
          queued_at REAL NOT NULL, expires_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS scheduler(id INTEGER PRIMARY KEY CHECK(id=1), last_tenant TEXT);
        ''')

    def create(self, tenant, session):
        self.db.execute('INSERT INTO sessions(id,tenant,state) VALUES(?,?,?)', (session,tenant,'queued'))

    def enqueue(self, tenant, session, *, ttl_seconds=300, max_queued=32):
        """Durably queue a session, rejecting excess work before it consumes a VM."""
        if type(ttl_seconds) not in (int, float) or ttl_seconds <= 0 or max_queued < 1:
            raise ValueError('invalid admission policy')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT tenant,state FROM sessions WHERE id=?', (session,)).fetchone()
            if row is None or row[0] != tenant or row[1] != 'queued':
                raise PermissionError('session is not queueable')
            if self.db.execute('SELECT 1 FROM admission WHERE session=?', (session,)).fetchone():
                raise ValueError('session already queued')
            queued = self.db.execute('''SELECT count(*) FROM admission a JOIN sessions s ON s.id=a.session
                                        WHERE s.state='queued' ''').fetchone()[0]
            if queued >= max_queued:
                raise OverflowError('admission queue is full')
            now = float(self.clock())
            self.db.execute('INSERT INTO admission VALUES(?,?,?,?,0)',
                            (session, tenant, now, now + ttl_seconds))
            self.db.execute('COMMIT')
        except Exception:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def admit_next(self, *, capacity, tenant_capacity=1):
        """Atomically start one queued session using tenant round-robin fairness."""
        if (type(capacity) is not int or capacity < 1 or
                type(tenant_capacity) is not int or tenant_capacity < 1):
            raise ValueError('invalid worker capacity')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            active = self.db.execute("SELECT count(*) FROM sessions WHERE state IN ('running','checkpointing','restoring')").fetchone()[0]
            if active >= capacity:
                self.db.execute('COMMIT')
                return None
            now = float(self.clock())
            candidates = self.db.execute('''SELECT a.session,a.tenant,s.version FROM admission a
                JOIN sessions s ON s.id=a.session WHERE s.state='queued' AND a.expires_at>?
                ORDER BY a.queued_at,a.session''', (now,)).fetchall()
            candidates = [candidate for candidate in candidates if self.db.execute(
                "SELECT count(*) FROM sessions WHERE tenant=? AND state IN ('running','checkpointing','restoring')",
                (candidate[1],)).fetchone()[0] < tenant_capacity]
            if not candidates:
                self.db.execute('COMMIT')
                return None
            last = self.db.execute('SELECT last_tenant FROM scheduler WHERE id=1').fetchone()
            last_tenant = last[0] if last else None
            selected = next((item for item in candidates if item[1] != last_tenant), candidates[0])
            session, tenant, version = selected
            self.db.execute("UPDATE sessions SET state='running',version=? WHERE id=? AND state='queued' AND version=?",
                            (version + 1, session, version))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('admission race')
            result = {'state': 'running', 'version': version + 1}
            self.db.execute('INSERT INTO operations VALUES(?,?,?,?)',
                            (session, f'admit:{version}', 'running', json.dumps(result)))
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)',
                            (datetime.now(timezone.utc).isoformat(), session, 'queued', 'running', version + 1))
            self.db.execute('INSERT INTO scheduler(id,last_tenant) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET last_tenant=excluded.last_tenant',
                            (tenant,))
            self.db.execute('COMMIT')
            return {'tenant': tenant, 'session': session, **result}
        except Exception:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def finish_execution(self, session):
        """Release a worker slot after a terminal result and return the next admission."""
        self.db.execute('DELETE FROM admission WHERE session=?', (session,))

    def expire_due(self):
        """Expire queued or active work after controller restart; returns affected IDs."""
        now = float(self.clock())
        rows = self.db.execute('''SELECT a.session,a.tenant,s.state,s.version FROM admission a
            JOIN sessions s ON s.id=a.session WHERE a.expires_at<=?
            AND s.state IN ('queued','running','checkpointing','paused','restoring')''', (now,)).fetchall()
        expired = []
        for session, tenant, _state, version in rows:
            self.transition(tenant, session, 'expired', f'expire:{version}', version)
            self.finish_execution(session)
            expired.append(session)
        return expired

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

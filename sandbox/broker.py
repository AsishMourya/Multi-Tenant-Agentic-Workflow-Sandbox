"""Trusted mock broker: no HTTP endpoint and no production credentials."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',',':'), allow_nan=False)

class Broker:
    def __init__(self, path=':memory:', clock=time.time):
        self.clock = clock
        self.key = secrets.token_bytes(32)  # restart invalidates outstanding tokens
        self.dummy_secret = 'DUMMY_UPSTREAM_CANARY_NOT_A_REAL_SECRET'
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,tenant TEXT,exercise TEXT,epoch INTEGER,state TEXT);
          CREATE TABLE IF NOT EXISTS calls(session TEXT,epoch INTEGER,request TEXT,digest TEXT,result TEXT,
              PRIMARY KEY(session,request));
        CREATE TABLE IF NOT EXISTS audit(at TEXT,tenant TEXT,session TEXT,request TEXT,operation TEXT,outcome TEXT,reason TEXT);
        ''')

    def register(self, tenant, session, exercise):
        self.db.execute('INSERT INTO sessions VALUES(?,?,?,0,?)',(session,tenant,exercise,'running'))

    def revoke(self, session, state='paused'):
        self.db.execute('UPDATE sessions SET epoch=epoch+1,state=? WHERE id=?',(state,session))

    def issue(self, tenant, session, exercise, ttl=60):
        row = self.db.execute('SELECT tenant,exercise,epoch,state FROM sessions WHERE id=?',(session,)).fetchone()
        if not row or (row[0],row[1],row[3]) != (tenant,exercise,'running'): raise PermissionError('scope')
        if not 0 < ttl <= 300: raise ValueError('ttl')
        now = int(self.clock())
        cap = {'v':1,'iss':'w1-broker','aud':'mock-tools','tenant':tenant,'session':session,
               'exercise':exercise,'ops':['inventory.lookup'],'iat':now,'nbf':now,'exp':now+ttl,
               'epoch':row[2],'jti':secrets.token_hex(16)}
        payload = canonical(cap)
        return {'cap':cap,'sig':hmac.new(self.key,payload.encode(),hashlib.sha256).hexdigest()}

    def call(self, principal, token, operation, args, request):
        """principal comes from trusted transport authentication, never submission input."""
        tenant, session, exercise = principal
        outcome, reason = 'denied','authorization'
        self.db.execute('BEGIN IMMEDIATE')
        try:
            cap = token['cap']
            sig = hmac.new(self.key,canonical(cap).encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig,token['sig']): raise PermissionError('signature')
            row = self.db.execute('SELECT tenant,exercise,epoch,state FROM sessions WHERE id=?',(session,)).fetchone()
            now = self.clock()
            if not row or row != (tenant,exercise,cap['epoch'],'running'): raise PermissionError('session')
            if (cap['v'],cap['iss'],cap['aud'],cap['tenant'],cap['session'],cap['exercise']) != (1,'w1-broker','mock-tools',tenant,session,exercise): raise PermissionError('scope')
            if not cap['nbf'] <= now < cap['exp'] or cap['exp']-cap['iat'] > 300: raise PermissionError('expiry')
            if operation not in cap['ops'] or operation != 'inventory.lookup': raise PermissionError('operation')
            if not isinstance(args,dict) or set(args) != {'sku'} or args['sku'] not in {'apple','pear'}: raise PermissionError('arguments')
            if not isinstance(request,str) or not 1 <= len(request) <= 64: raise PermissionError('request ID')
            digest = hashlib.sha256(canonical([operation,args]).encode()).hexdigest()
            old = self.db.execute('SELECT digest,result FROM calls WHERE session=? AND request=?',(session,request)).fetchone()
            if old:
                if old[0] != digest: raise PermissionError('replay conflict')
                outcome, reason = 'allowed','cached retry'
                return json.loads(old[1])
            count = self.db.execute('SELECT count(*) FROM calls WHERE session=?',(session,)).fetchone()[0]
            if count >= 20: raise PermissionError('session call budget')
            result = {'sku':args['sku'],'available':{'apple':7,'pear':3}[args['sku']]}
            self.db.execute('INSERT INTO calls VALUES(?,?,?,?,?)',(session,cap['epoch'],request,digest,canonical(result)))
            outcome, reason = 'allowed','authorized'
            return result
        except (KeyError,TypeError,ValueError) as exc:
            reason = 'malformed'
            raise PermissionError('malformed capability') from exc
        except PermissionError as exc:
            reason = str(exc)
            raise
        finally:
            self.db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?,?)',(datetime.now(timezone.utc).isoformat(),tenant,session,request,operation,outcome,reason))
            self.db.execute('COMMIT')

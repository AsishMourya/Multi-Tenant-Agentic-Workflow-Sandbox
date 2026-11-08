"""Local account and opaque-session store for the one-machine demo.

Passwords are never retained in plaintext.  The browser receives only an
HttpOnly session token; tenant identity stays server-derived.
"""
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone


def _now():
    return datetime.now(timezone.utc)


class LocalAuth:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.execute('''CREATE TABLE IF NOT EXISTS accounts(
            username TEXT PRIMARY KEY, tenant TEXT UNIQUE NOT NULL,
            salt BLOB NOT NULL, password_hash BLOB NOT NULL, created_at TEXT NOT NULL)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS browser_sessions(
            digest BLOB PRIMARY KEY, tenant TEXT NOT NULL, expires_at TEXT NOT NULL)''')

    @staticmethod
    def _password(password, salt):
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError('password must contain 12-256 characters')
        return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1)

    @staticmethod
    def _username(username):
        if (not isinstance(username, str) or not username.replace('_', '').replace('-', '').isalnum()
                or not 3 <= len(username) <= 32):
            raise ValueError('username must be 3-32 letters, numbers, hyphens, or underscores')

    def register(self, username, password):
        self._username(username)
        salt = secrets.token_bytes(16)
        tenant = 'tenant-' + secrets.token_hex(12)
        try:
            self.db.execute('INSERT INTO accounts VALUES(?,?,?,?,?)',
                            (username, tenant, salt, self._password(password, salt), _now().isoformat()))
        except sqlite3.IntegrityError as exc:
            raise ValueError('username already exists') from exc
        return self.login(username, password)

    def login(self, username, password):
        self._username(username)
        row = self.db.execute('SELECT tenant,salt,password_hash FROM accounts WHERE username=?',
                              (username,)).fetchone()
        if not row or not hmac.compare_digest(self._password(password, row[1]), row[2]):
            raise PermissionError('invalid username or password')
        token = secrets.token_urlsafe(32)
        expiry = (_now() + timedelta(hours=12)).isoformat()
        self.db.execute('INSERT INTO browser_sessions VALUES(?,?,?)',
                        (hashlib.sha256(token.encode()).digest(), row[0], expiry))
        return token, row[0], expiry

    def tenant_for(self, token):
        if not isinstance(token, str):
            raise PermissionError('sign in required')
        row = self.db.execute('SELECT tenant,expires_at FROM browser_sessions WHERE digest=?',
                              (hashlib.sha256(token.encode()).digest(),)).fetchone()
        if not row or datetime.fromisoformat(row[1]) <= _now():
            raise PermissionError('sign in required')
        return row[0]

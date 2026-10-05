"""Versioned application-state checkpoints for the supported workflow exercise."""
import json
import os
import tempfile
from pathlib import Path


SCHEMA = 'inventory-safe-point-1'


class StateStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session):
        if not isinstance(session, str) or not session or '/' in session or '\\' in session:
            raise ValueError('invalid session')
        return self.root / f'{session}.json'

    def save(self, tenant, session, exercise, state):
        if exercise != 'inventory':
            raise ValueError('unsupported checkpoint exercise')
        required = {'sku', 'quantity', 'available'}
        if set(state) != required or state['sku'] not in {'apple', 'pear'}:
            raise ValueError('invalid checkpoint state')
        if type(state['quantity']) is not int or not 0 <= state['quantity'] <= 100:
            raise ValueError('invalid checkpoint quantity')
        if type(state['available']) is not int or not 0 <= state['available'] <= 100:
            raise ValueError('invalid checkpoint availability')
        record = {'schema': SCHEMA, 'tenant': tenant, 'session': session,
                  'exercise': exercise, 'state': state}
        path = self._path(session)
        fd, temporary = tempfile.mkstemp(prefix=f'.{session}.', dir=self.root, text=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return record

    def load(self, tenant, session, exercise):
        path = self._path(session)
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ValueError('checkpoint unavailable') from exc
        if (record.get('schema'), record.get('tenant'), record.get('session'),
                record.get('exercise')) != (SCHEMA, tenant, session, exercise):
            raise ValueError('checkpoint ownership or version mismatch')
        state = record.get('state')
        if not isinstance(state, dict):
            raise ValueError('invalid checkpoint state')
        self.save(tenant, session, exercise, state)
        return state
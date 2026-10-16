"""Credential-bound entry point for tenant operations.

Transport code should pass only an opaque bearer token. The tenant identifier is
derived here and never accepted from a learner request body.
"""
import hashlib
import hmac

from sandbox.platform import TENANTS


class TenantGateway:
    def __init__(self, platform, credentials):
        if set(credentials) != set(TENANTS):
            raise ValueError('one credential is required for each tenant')
        if any(not isinstance(token, str) or len(token) < 32 for token in credentials.values()):
            raise ValueError('tenant credentials must be at least 32 characters')
        if len(set(credentials.values())) != len(credentials):
            raise ValueError('tenant credentials must be distinct')
        self.platform = platform
        self.digests = {tenant: hashlib.sha256(token.encode()).digest()
                        for tenant, token in credentials.items()}

    def _tenant(self, bearer):
        if not isinstance(bearer, str):
            raise PermissionError('invalid credential')
        digest = hashlib.sha256(bearer.encode()).digest()
        for tenant, expected in self.digests.items():
            if hmac.compare_digest(digest, expected):
                return tenant
        raise PermissionError('invalid credential')

    def create(self, bearer, exercise):
        return self.platform.create_session(self._tenant(bearer), exercise)

    def submit_python(self, bearer, session, source, payload, judges,
                      pause_resume=False):
        return self.platform.submit_code(self._tenant(bearer), session,
                                         source, payload, judges,
                                         pause_resume=pause_resume)

    def submit_workflow(self, bearer, session, source, payload, judges):
        return self.platform.submit_workflow_code(self._tenant(bearer), session,
                                                  source, payload, judges)

    def status(self, bearer, session):
        return self.platform.status(self._tenant(bearer), session)

    def delete(self, bearer, session):
        return self.platform.delete(self._tenant(bearer), session)

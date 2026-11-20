"""Credential-bound entry point for tenant operations.

Transport code should pass only an opaque bearer token. The tenant identifier is
derived here and never accepted from a learner request body.
"""
import hashlib
import hmac

class TenantGateway:
    def __init__(self, platform, credentials):
        if (not isinstance(credentials, dict) or not credentials or
                any(not isinstance(tenant, str) or not 1 <= len(tenant) <= 64
                    for tenant in credentials)):
            raise ValueError('at least one named tenant credential is required')
        if any(not isinstance(token, str) or len(token) < 32 for token in credentials.values()):
            raise ValueError('tenant credentials must be at least 32 characters')
        if len(set(credentials.values())) != len(credentials):
            raise ValueError('tenant credentials must be distinct')
        self.platform = platform
        self.digests = {tenant: hashlib.sha256(token.encode()).digest()
                        for tenant, token in credentials.items()}
        self.browser_auth = None

    def bind_browser_session(self, tenant, token):
        """Bind a verified opaque browser session to its server-owned tenant."""
        if not isinstance(tenant, str) or not isinstance(token, str):
            raise PermissionError('invalid session')
        if self.browser_auth is None or self.browser_auth.tenant_for(token) != tenant:
            raise PermissionError('invalid session')

    def _tenant(self, bearer):
        if not isinstance(bearer, str):
            raise PermissionError('invalid credential')
        digest = hashlib.sha256(bearer.encode()).digest()
        for tenant, expected in self.digests.items():
            if hmac.compare_digest(digest, expected):
                return tenant
        if self.browser_auth is not None:
            # Always consult the durable session store, including after restart.
            return self.browser_auth.tenant_for(bearer)
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

    def list_sessions(self, bearer):
        return self.platform.list_sessions(self._tenant(bearer))

    def cancel(self, bearer, session):
        return self.platform.cancel(self._tenant(bearer), session)

    def delete(self, bearer, session):
        return self.platform.delete(self._tenant(bearer), session)

    def pause(self, bearer, session, payload):
        return self.platform.pause(self._tenant(bearer), session, payload)

    def resume(self, bearer, session):
        return self.platform.resume(self._tenant(bearer), session)

    def finish_safe_point(self, bearer, session):
        return self.platform.finish_safe_point(self._tenant(bearer), session)

"""Minimal inherited environment for sandbox subprocesses."""


def safe_firecracker_env(environment):
    """Keep only executable lookup and locale; exclude host credentials by default."""
    return {'PATH': environment.get('PATH', '/usr/bin:/bin'), 'LANG': 'C', 'LC_ALL': 'C'}

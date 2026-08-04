"""Shared config for the couch test rigs.

Credentials live in ~/couch/.env, never in source. systemd hands the server its
environment via EnvironmentFile=; these scripts are run by hand, so they read
the same file directly. Anything already exported in the environment wins.
"""
import os

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')


def load_env(path=ENV_FILE):
    """Read KEY=value lines into os.environ without overriding what is set."""
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, val = line.partition('=')
        os.environ.setdefault(key.strip(), val.strip())


def kodi_auth():
    """`user:password` for Kodi's JSON-RPC basic auth, as curl -u wants it."""
    load_env()
    password = os.environ.get('KODI_PASSWORD')
    if not password:
        raise SystemExit('KODI_PASSWORD is not set (see .env.example)')
    return '%s:%s' % (os.environ.get('KODI_USER', 'kodi'), password)


def kodi_url():
    load_env()
    return os.environ.get('KODI_URL', 'http://localhost:8090') + '/jsonrpc'

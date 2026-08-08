#!/usr/bin/env python3
"""Running host programs, and reading host files, from inside Kodi.

Under apt-Kodi this module does nothing at all: Kodi is an ordinary process
owned by ds2000, `~/.local/bin/game-launch` is on the filesystem and runs, and
`/tmp/game-suspended` is `/tmp/game-suspended`. Every call here is a
passthrough and the console behaves exactly as it did before this file
existed. That is the point - the apt build stays the rollback.

Under the Flatpak (Kodi 21) neither is true:

  * the filesystem inside the sandbox is the Freedesktop 24.08 runtime, not
    Ubuntu. `--filesystem=home` makes `~/.local/bin/game-launch` *visible*,
    which is the trap: it is a bash script wanting xdotool, xrandr, wmctrl,
    pgrep, steam and the host's python3, and none of those are in there. It
    would start and fail halfway, which is worse than not starting.
  * `/tmp` is a private tmpfs per app unless it is explicitly exported, so the
    console's coordination flags can read as "no game running" when a game is
    running - and `script.tvpoweroff` would then offer to power off the TV
    mid-game.

So: `host_run` sends the argv out to the real session over
`flatpak-spawn --host`, and `host_read` falls back to the same route when a
direct read fails. The fallback is what makes the `--filesystem=/tmp`
override an optimisation rather than a dependency - if that override is ever
dropped or a flatpak release changes its mind about exporting /tmp, the flags
still read, just a few tens of milliseconds slower.

THE ENVIRONMENT IS CLEARED, deliberately. flatpak-spawn forwards the caller's
environment by default, and the caller here is inside the runtime: passing
`LD_LIBRARY_PATH=/app/lib` or the sandbox's `PATH` out to a host bash script
would have host binaries loading runtime libraries. So the host side gets an
explicit, minimal set - the same set the console's own scripts already default
for themselves when they are started from odd contexts.

Single source of truth: `~/couch/kodi-addons/couchhost/couchhost.py`, vendored
byte-identically into each addon that needs it (Kodi addons cannot depend on a
path outside the addon tree without breaking the moment that path moves).
`tools/test_couchhost.py` pins the copies against this original.
"""
import os
import subprocess

__all__ = ['in_sandbox', 'host_argv', 'host_env', 'host_popen', 'host_read',
           'host_exists', 'SPAWN']

#: flatpak's own marker, present in every sandbox and nowhere else. Checked
#: once per process: a Kodi that started outside a sandbox will not find
#: itself inside one later.
_SANDBOX = os.path.exists('/.flatpak-info')

#: In the runtime this is /usr/bin/flatpak-spawn; the absolute path avoids
#: depending on the sandbox PATH.
SPAWN = '/usr/bin/flatpak-spawn'

#: Passed through to the host when we have them, defaulted when we do not.
#: DISPLAY/XAUTHORITY are defaulted the same way game-launch defaults them, so
#: a spawned script behaves identically however it was reached.
_ENV_DEFAULTS = {
    'DISPLAY': ':0',
    'XAUTHORITY': None,          # filled from HOME below
    'XDG_RUNTIME_DIR': None,     # filled from uid below
    'DBUS_SESSION_BUS_ADDRESS': None,
    'LANG': 'en_GB.UTF-8',
}


def in_sandbox():
    """True inside a Flatpak, False under the apt build."""
    return _SANDBOX


def host_env():
    """The environment a host program should be handed, as a dict.

    Not the sandbox's environment. Everything in here is either read from the
    sandbox because flatpak passes the real value through (HOME, USER,
    DISPLAY) or reconstructed from the uid, and PATH is the console's own -
    `~/.local/bin` first, because that is where every script it wants lives.
    """
    home = os.path.expanduser('~')
    uid = os.getuid()
    runtime = '/run/user/%d' % uid
    env = {
        'HOME': home,
        'USER': os.environ.get('USER') or os.path.basename(home),
        'PATH': '%s/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/games' % home,
        'DISPLAY': os.environ.get('DISPLAY') or _ENV_DEFAULTS['DISPLAY'],
        'XAUTHORITY': os.environ.get('XAUTHORITY') or home + '/.Xauthority',
        'XDG_RUNTIME_DIR': runtime,
        'DBUS_SESSION_BUS_ADDRESS': 'unix:path=%s/bus' % runtime,
        'LANG': os.environ.get('LANG') or _ENV_DEFAULTS['LANG'],
    }
    return env


def host_argv(argv):
    """The argv to actually exec: unchanged outside a sandbox."""
    argv = [str(a) for a in argv]
    if not _SANDBOX:
        return argv
    cmd = [SPAWN, '--host', '--clear-env']
    for key, value in sorted(host_env().items()):
        cmd.append('--env=%s=%s' % (key, value))
    return cmd + argv


def host_popen(argv, **kwargs):
    """subprocess.Popen, routed to the host session when sandboxed.

    Keyword arguments are passed straight through, so existing call sites keep
    their `start_new_session=True` and their DEVNULL redirections. `env` is
    never set here: outside the sandbox the caller's environment is inherited
    exactly as before, and inside it the environment travels as --env flags
    rather than as this process's own.
    """
    return subprocess.Popen(host_argv(argv), **kwargs)


def host_read(path, timeout=3.0):
    """The contents of a host file, or None.

    Direct read first - that is the whole cost outside a sandbox, and inside
    one it is also the whole cost whenever the path happens to be exported
    (which /tmp and $HOME are meant to be). Only a failed direct read pays for
    a spawn, and only when sandboxed: on the apt build a missing file is a
    missing file and None comes straight back.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:
        pass
    if not _SANDBOX:
        return None
    try:
        done = subprocess.run(host_argv(['cat', '--', path]),
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode('utf-8', 'replace')


def host_exists(path, timeout=3.0):
    """Whether a host path exists, with the same fallback as host_read.

    `test -e` rather than a read, so a large or unreadable file is not pulled
    across just to answer a yes/no.
    """
    if os.path.exists(path):
        return True
    if not _SANDBOX:
        return False
    try:
        done = subprocess.run(host_argv(['test', '-e', path]),
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0

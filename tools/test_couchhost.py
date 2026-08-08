#!/usr/bin/env python3
"""couchhost: the one place Kodi is allowed to leave the sandbox.

Kodi 21 arrives as a Flatpak (docs/kodi21-flatpak-migration.md), and two of
its habits stop working inside one: spawning `~/.local/bin/game-launch`, and
reading `/tmp/game-suspended`. This module is the whole of the fix, so what
gets pinned here is the pair of properties the migration rests on:

  1. OUTSIDE a sandbox nothing changes. Not "changes compatibly" - nothing.
     The argv is the argv, the environment is inherited, a missing file
     returns None without spawning anything. apt-Kodi is the rollback and a
     rollback that behaves differently is not one.
  2. INSIDE a sandbox the environment handed to the host is CLEARED and
     rebuilt. The failure this prevents is quiet and nasty: flatpak-spawn
     forwards the caller's environment by default, so a host bash script
     would inherit the runtime's LD_LIBRARY_PATH=/app/lib and PATH, and host
     binaries would start loading Freedesktop-runtime libraries.

Plus the vendoring rule: the copies inside each addon must be byte-identical
to the original, the same way test_legacy_mirror.py pins ~/.local/bin against
legacy-mirror/. A drifted copy is a bug that only shows up on the one addon
nobody re-tested.

Run:  couchd/.venv/bin/pytest tools/test_couchhost.py -q
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys

import pytest

HOME = os.path.expanduser('~')
SOURCE = os.path.join(HOME, 'couch', 'kodi-addons', 'couchhost',
                      'couchhost.py')

#: every addon that vendors a copy, and where the copy lives relative to
#: ~/couch/kodi-addons. Adding an addon to this list is what makes the
#: identity test cover it.
VENDORED = [
    'copacetic-helper-patches/couchhost.py',
    'script.couch.switcher/couchhost.py',
    'script.tvpoweroff/couchhost.py',
]


def _load(name, sandbox):
    """A fresh import of the module with /.flatpak-info faked either way.

    The sandbox check is deliberately done once at import (a process does not
    move in or out of a sandbox mid-life), so the only honest way to test both
    worlds is to import it twice.
    """
    real_exists = os.path.exists

    def exists(path):
        if path == '/.flatpak-info':
            return sandbox
        return real_exists(path)

    os.path.exists = exists
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, SOURCE))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.path.exists = real_exists
    return module


@pytest.fixture(scope='module')
def host():
    """couchhost as it behaves under apt-Kodi."""
    return _load('couchhost_host', sandbox=False)


@pytest.fixture(scope='module')
def sandboxed():
    """couchhost as it behaves inside the Flatpak."""
    return _load('couchhost_sandboxed', sandbox=True)


# =========================================================================
# 1. outside a sandbox: a passthrough, and provably so
# =========================================================================
def test_the_argv_is_untouched_on_the_apt_build(host):
    assert host.in_sandbox() is False
    argv = ['/home/ds2000/.local/bin/game-launch', 'shadps4', '/x/eboot.bin']
    assert host.host_argv(argv) == argv


def test_non_string_arguments_are_stringified_either_way(host, sandboxed):
    """games.py builds tile ids out of ints; Popen would raise on them."""
    assert host.host_argv(['x', 1]) == ['x', '1']
    assert sandboxed.host_argv(['x', 1])[-2:] == ['x', '1']


def test_a_missing_file_reads_none_without_spawning(host, monkeypatch):
    """The apt path must not gain a subprocess on the no-game case - it runs
    on every Games row listing."""
    monkeypatch.setattr(host.subprocess, 'run', _forbidden)
    assert host.host_read('/tmp/definitely-not-here-8afc') is None
    assert host.host_exists('/tmp/definitely-not-here-8afc') is False


def test_a_present_file_reads_directly(host, tmp_path, monkeypatch):
    monkeypatch.setattr(host.subprocess, 'run', _forbidden)
    flag = tmp_path / 'game-suspended'
    flag.write_text('367520\n')
    assert host.host_read(str(flag)) == '367520\n'
    assert host.host_exists(str(flag)) is True


def test_popen_passes_kwargs_through_unchanged(host, monkeypatch):
    """The call sites rely on start_new_session=True to detach the launcher
    from Kodi's own process group; losing it would kill a game when Kodi
    restarts."""
    seen = {}
    monkeypatch.setattr(host.subprocess, 'Popen',
                        lambda argv, **kw: seen.update(argv=argv, kw=kw))
    host.host_popen(['/bin/true'], start_new_session=True,
                    stdout=subprocess.DEVNULL)
    assert seen['argv'] == ['/bin/true']
    assert seen['kw'] == {'start_new_session': True,
                          'stdout': subprocess.DEVNULL}
    assert 'env' not in seen['kw']          # inheritance, exactly as before


def _forbidden(*args, **kwargs):
    raise AssertionError('spawned a subprocess on the apt path')


# =========================================================================
# 2. inside a sandbox: out through flatpak-spawn, with a clean environment
# =========================================================================
def test_the_argv_goes_out_through_flatpak_spawn(sandboxed):
    argv = ['/home/ds2000/.local/bin/tv', 'off']
    built = sandboxed.host_argv(argv)
    assert built[:3] == [sandboxed.SPAWN, '--host', '--clear-env']
    assert built[-2:] == argv


def test_the_environment_is_cleared_and_rebuilt(sandboxed, monkeypatch):
    """--clear-env is the whole safety property. Without it the runtime's
    LD_LIBRARY_PATH travels to a host bash script."""
    monkeypatch.setenv('LD_LIBRARY_PATH', '/app/lib')
    monkeypatch.setenv('PYTHONPATH', '/app/share/kodi/addons')
    monkeypatch.setenv('KODI_HOME', '/app/share/kodi')
    built = sandboxed.host_argv(['/bin/true'])
    assert '--clear-env' in built
    passed = [a for a in built if a.startswith('--env=')]
    keys = {a[len('--env='):].split('=', 1)[0] for a in passed}
    assert keys == {'HOME', 'USER', 'PATH', 'DISPLAY', 'XAUTHORITY',
                    'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'LANG'}
    assert not any('/app/lib' in a for a in built)
    assert not any(a.startswith('--env=LD_LIBRARY_PATH') for a in built)


def test_the_host_path_puts_local_bin_first(sandboxed):
    """Everything Kodi spawns lives in ~/.local/bin, and the sandbox PATH
    (/app/bin:/usr/bin) does not contain it at all."""
    env = sandboxed.host_env()
    assert env['PATH'].split(':')[0] == os.path.join(HOME, '.local', 'bin')
    assert env['HOME'] == HOME


def test_the_session_bus_and_runtime_dir_are_rebuilt_from_the_uid(sandboxed):
    """Flatpak gives the sandbox its own XDG_RUNTIME_DIR; a host program
    handed that one cannot reach the session bus, so bluetoothctl and the
    volume calls in tv/tvpoweroff would fail."""
    env = sandboxed.host_env()
    assert env['XDG_RUNTIME_DIR'] == '/run/user/%d' % os.getuid()
    assert env['DBUS_SESSION_BUS_ADDRESS'] == (
        'unix:path=/run/user/%d/bus' % os.getuid())


def test_display_falls_back_when_the_sandbox_has_none(sandboxed, monkeypatch):
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('XAUTHORITY', raising=False)
    env = sandboxed.host_env()
    assert env['DISPLAY'] == ':0'
    assert env['XAUTHORITY'] == os.path.join(HOME, '.Xauthority')


# =========================================================================
# 3. the /tmp fallback - the override is an optimisation, not a dependency
# =========================================================================
def test_a_readable_flag_never_pays_for_a_spawn(sandboxed, tmp_path,
                                                monkeypatch):
    """With --filesystem=/tmp working, this is every read: one open()."""
    monkeypatch.setattr(sandboxed.subprocess, 'run', _forbidden)
    flag = tmp_path / 'game-suspended'
    flag.write_text('bigpicture')
    assert sandboxed.host_read(str(flag)) == 'bigpicture'


@pytest.fixture
def unexported(tmp_path):
    """A path that does not exist in *this* namespace but does on the host.

    Standing in for /tmp/game-suspended when --filesystem=/tmp is not in
    effect: the sandbox sees nothing there, the host has the flag. The
    injected path is a tmp_path one - never the live /tmp, which on this box
    really does carry a suspended game's flag and would make these tests
    read the console's actual state (the 5 Aug rule)."""
    return str(tmp_path / 'game-suspended')


def test_an_unreadable_flag_falls_back_to_the_host(sandboxed, monkeypatch,
                                                   unexported):
    """The case that matters: /tmp not exported, so the private tmpfs is
    empty and a direct read finds nothing. The answer must still be the
    truth on the host, not 'no game running' - `script.tvpoweroff` offering
    to power off the TV mid-game is the failure being prevented."""
    calls = []

    class Done:
        returncode = 0
        stdout = b'367520\n'

    monkeypatch.setattr(sandboxed.subprocess, 'run',
                        lambda argv, **kw: (calls.append(argv), Done())[1])
    assert sandboxed.host_read(unexported) == '367520\n'
    assert calls[0][:3] == [sandboxed.SPAWN, '--host', '--clear-env']
    assert calls[0][-3:] == ['cat', '--', unexported]


def test_a_genuinely_absent_flag_is_still_absent(sandboxed, monkeypatch,
                                                 unexported):
    class Done:
        returncode = 1
        stdout = b''

    monkeypatch.setattr(sandboxed.subprocess, 'run', lambda argv, **kw: Done())
    assert sandboxed.host_read(unexported) is None
    assert sandboxed.host_exists(unexported) is False


def test_exists_asks_test_e_rather_than_reading(sandboxed, monkeypatch,
                                                unexported):
    calls = []

    class Done:
        returncode = 0
        stdout = b''

    monkeypatch.setattr(sandboxed.subprocess, 'run',
                        lambda argv, **kw: (calls.append(argv), Done())[1])
    assert sandboxed.host_exists(unexported) is True
    assert calls[0][-3:] == ['test', '-e', unexported]


@pytest.mark.parametrize('boom', [OSError('no spawn helper'),
                                  subprocess.TimeoutExpired('cat', 3)])
def test_a_broken_spawn_helper_degrades_to_none_not_a_traceback(sandboxed,
                                                                monkeypatch,
                                                                unexported,
                                                                boom):
    """If org.freedesktop.Flatpak is not on the bus (a headless run, a
    stripped override) the flags read as absent. That is the safe direction -
    the console loses the paused badge, it does not lose Kodi to an
    unhandled exception inside a directory listing."""
    def raise_it(*args, **kwargs):
        raise boom
    monkeypatch.setattr(sandboxed.subprocess, 'run', raise_it)
    assert sandboxed.host_read(unexported) is None
    assert sandboxed.host_exists(unexported) is False


# =========================================================================
# 4. the vendored copies
# =========================================================================
def test_every_vendored_copy_is_byte_identical():
    """Three addons carry a copy because a Kodi addon that imports from
    ~/couch breaks the day ~/couch moves. Copies drift; this is the guard."""
    original = open(SOURCE, 'rb').read()
    base = os.path.join(HOME, 'couch', 'kodi-addons')
    for relative in VENDORED:
        path = os.path.join(base, relative)
        assert os.path.exists(path), f'{relative} was never vendored'
        assert open(path, 'rb').read() == original, f'{relative} has drifted'


def test_the_module_has_no_kodi_imports():
    """It is imported by tests, by the migration script's verifier and by
    three addons; an `import xbmc` would make it unusable everywhere but
    inside Kodi."""
    text = open(SOURCE).read()
    assert 'import xbmc' not in text
    assert 'xbmcgui' not in text


def test_the_source_compiles_under_the_hosts_python():
    subprocess.run([sys.executable, '-m', 'py_compile', SOURCE], check=True)

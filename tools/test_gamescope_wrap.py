#!/usr/bin/env python3
"""Tests for tools/gamescope-wrap, the stage-3 nested-gamescope launcher.

NOTHING here touches the live console, the real gamescope build, X, or any
live path: the end-to-end tests run the wrapper against a FAKE gamescope
written into tmp_path (one that runs the child then exits 139, exactly the
3.16.25 teardown segfault the wrapper exists to launder), and every seam
(GSWRAP_GAMESCOPE_DIR / GSWRAP_STATUS_DIR / GSWRAP_LOG) points under
tmp_path. The manual/real-build proof lives in tools/gamescope-wrap-rig.

Run:  couchd/.venv/bin/python -m pytest tools/test_gamescope_wrap.py -q
"""
import importlib.machinery
import importlib.util
import os
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'gamescope-wrap')

FAKE_GAMESCOPE = '''#!/usr/bin/env python3
import os, subprocess, sys
if os.environ.get('FAKE_GS_SKIP_CHILD') == '1':
    sys.exit(int(os.environ.get('FAKE_GS_RC', '1')))
args = sys.argv[1:]
cmd = args[args.index('--') + 1:]
subprocess.run(cmd)
if os.environ.get('FAKE_GS_EAT_STATUS') == '1':
    try:
        os.remove(os.environ['GSWRAP_STATUS'])
    except OSError:
        pass
sys.exit(int(os.environ.get('FAKE_GS_EXIT', '139')))
'''


def load(modname='gswrap_under_test'):
    if not os.path.exists(TOOL):
        pytest.skip('tools/gamescope-wrap not present')
    loader = importlib.machinery.SourceFileLoader(modname, TOOL)
    spec = importlib.util.spec_from_loader(modname, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)          # imports only; runs nothing
    return mod


@pytest.fixture(scope='module')
def wrap():
    return load()


@pytest.fixture
def fake_build(tmp_path):
    """A build dir holding a fake gamescope + gamescopereaper."""
    build = tmp_path / 'build'
    build.mkdir()
    for name in ('gamescope', 'gamescopereaper'):
        p = build / name
        p.write_text(FAKE_GAMESCOPE)
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return build


def run_tool(args, tmp_path, gs_dir, extra_env=None):
    env = dict(os.environ)
    env['GSWRAP_GAMESCOPE_DIR'] = str(gs_dir)
    env['GSWRAP_STATUS_DIR'] = str(tmp_path)
    env['GSWRAP_LOG'] = str(tmp_path / 'wrap.log')
    env.pop('GSWRAP_DISABLE', None)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, TOOL] + args, env=env,
                          capture_output=True, text=True, timeout=60)


# =========================================================================
# argument parsing
# =========================================================================
def test_parse_defaults(wrap):
    o = wrap.parse_args(['--', 'game', '--level', '3'])
    assert o['output'] == (1920, 1080)
    assert o['game'] == (1920, 1080)          # follows output when unset
    assert o['rate'] == 120
    assert o['backend'] == 'sdl'
    assert o['command'] == ['game', '--level', '3']
    assert not o['dry_run'] and not o['no_gamescope']


def test_parse_sizes_and_rate(wrap):
    o = wrap.parse_args(['--output', '3840x2160', '--game', '1920x1080',
                         '--rate', '60', '--', 'g'])
    assert o['output'] == (3840, 2160)
    assert o['game'] == (1920, 1080)
    assert o['rate'] == 60


def test_parse_equals_spelling(wrap):
    o = wrap.parse_args(['--output=1280x720', '--rate=90', '--', 'g'])
    assert o['output'] == (1280, 720)
    assert o['rate'] == 90


def test_parse_gs_args_repeat(wrap):
    o = wrap.parse_args(['--gs-arg', '--adaptive-sync', '--gs-arg',
                         '--hdr-enabled', '--', 'g'])
    assert o['gs_args'] == ['--adaptive-sync', '--hdr-enabled']


def test_command_after_dashdash_is_verbatim(wrap):
    """A game command containing our own flag names must not be parsed."""
    o = wrap.parse_args(['--', 'game', '--output', 'weird', '--dry-run'])
    assert o['command'] == ['game', '--output', 'weird', '--dry-run']
    assert not o['dry_run']


@pytest.mark.parametrize('argv', [
    [],                                # help
    ['--', ],                          # no command
    ['game'],                          # no --
    ['--output', 'bogus', '--', 'g'],  # bad size
    ['--output', '1x1', '--', 'g'],    # implausible size
    ['--rate', 'fast', '--', 'g'],     # bad rate
    ['--nonsense', '--', 'g'],         # unknown flag
    ['--gs-arg', '--', 'g'],           # --gs-arg swallows the separator;
                                       # 'g' is then an unknown option
])
def test_parse_rejects(wrap, argv):
    with pytest.raises(wrap.Usage):
        wrap.parse_args(argv)


def test_forbidden_gs_args(wrap):
    assert wrap.forbidden_gs_args(['-g']) == '-g'
    assert wrap.forbidden_gs_args(['--steam']) == '--steam'
    assert wrap.forbidden_gs_args(['-e']) == '-e'
    assert wrap.forbidden_gs_args(['--adaptive-sync']) is None
    assert wrap.forbidden_gs_args([]) is None


# =========================================================================
# command building
# =========================================================================
def test_build_argv_shape(wrap):
    o = wrap.parse_args(['--output', '1920x1080', '--game', '1280x720',
                         '--rate', '120', '--gs-arg', '--adaptive-sync',
                         '--', 'mygame', '--flag'])
    argv = wrap.build_argv(o, '/x/gamescope')
    assert argv[0] == '/x/gamescope'
    s = ' '.join(argv)
    assert '-W 1920 -H 1080' in s
    assert '-w 1280 -h 720' in s
    assert '-r 120' in s
    assert '--backend sdl' in s
    assert '--adaptive-sync' in s
    # the shim hosts the game: ... -- sh -c <shim> gswrap-shim mygame --flag
    i = argv.index('--')
    assert argv[i + 1:i + 3] == ['sh', '-c']
    assert argv[i + 3] == wrap.SHIM
    assert argv[-2:] == ['mygame', '--flag']


def test_never_flags_absent_by_default(wrap):
    o = wrap.parse_args(['--', 'g'])
    argv = wrap.build_argv(o, '/x/gamescope')
    for banned in ('-e', '--steam', '-g', '--grab'):
        assert banned not in argv


# =========================================================================
# exit laundering (the pure decision table)
# =========================================================================
def test_resolve_status_wins_over_segfault(wrap):
    code, action, why = wrap.resolve_exit(139, True, '0')
    assert (code, action) == (0, 'report')
    assert 'laundered' in why


def test_resolve_real_failure_survives(wrap):
    code, action, _ = wrap.resolve_exit(139, True, '7')
    assert (code, action) == (7, 'report')


def test_resolve_status_matches_gamescope(wrap):
    code, action, _ = wrap.resolve_exit(0, True, '0')
    assert (code, action) == (0, 'report')


def test_resolve_garbage_status(wrap):
    code, action, _ = wrap.resolve_exit(0, True, 'not-a-number')
    assert (code, action) == (1, 'report')


def test_resolve_out_of_range_status(wrap):
    code, action, _ = wrap.resolve_exit(0, True, '512')
    assert (code, action) == (1, 'report')


def test_resolve_pregame_death_falls_back(wrap):
    code, action, _ = wrap.resolve_exit(1, False, None)
    assert action == 'fallback'
    assert code == 1


def test_resolve_pregame_death_rc0_still_falls_back_nonzero(wrap):
    code, action, _ = wrap.resolve_exit(0, False, None)
    assert action == 'fallback'
    assert code == 1


def test_resolve_lost_status_never_fallback(wrap):
    """The game RAN; relaunching it bare would be a second copy."""
    code, action, why = wrap.resolve_exit(139, True, None)
    assert action == 'report'
    assert code == 139
    assert 'lost' in why


def test_resolve_lost_status_rc0_reports_failure(wrap):
    code, action, _ = wrap.resolve_exit(0, True, None)
    assert action == 'report'
    assert code == 1


# =========================================================================
# finding the build
# =========================================================================
def test_find_gamescope_ok(wrap, fake_build):
    path, why = wrap.find_gamescope(str(fake_build))
    assert why is None
    assert path == str(fake_build / 'gamescope')


def test_find_gamescope_missing_reaper(wrap, fake_build):
    (fake_build / 'gamescopereaper').unlink()
    path, why = wrap.find_gamescope(str(fake_build))
    assert path is None and 'gamescopereaper' in why


def test_find_gamescope_missing_dir(wrap, tmp_path):
    path, why = wrap.find_gamescope(str(tmp_path / 'nope'))
    assert path is None


# =========================================================================
# end to end against the fake gamescope (tmp_path only)
# =========================================================================
def test_e2e_clean_exit_laundered(tmp_path, fake_build):
    r = run_tool(['--', 'sh', '-c', 'exit 0'], tmp_path, fake_build)
    assert r.returncode == 0, r.stderr


def test_e2e_failure_preserved(tmp_path, fake_build):
    r = run_tool(['--', 'sh', '-c', 'exit 7'], tmp_path, fake_build)
    assert r.returncode == 7, r.stderr


def test_e2e_signal_death_preserved(tmp_path, fake_build):
    r = run_tool(['--', 'sh', '-c', 'kill -9 $$'], tmp_path, fake_build)
    assert r.returncode == 137, r.stderr


def test_e2e_pregame_death_runs_bare(tmp_path, fake_build):
    r = run_tool(['--', 'sh', '-c', 'echo BARE; exit 5'], tmp_path,
                 fake_build, {'FAKE_GS_SKIP_CHILD': '1'})
    assert r.returncode == 5
    assert 'BARE' in r.stdout
    assert 'bare' in r.stderr.lower()


def test_e2e_lost_status_no_relaunch(tmp_path, fake_build):
    r = run_tool(['--', 'sh', '-c', 'echo ONCE; exit 0'], tmp_path,
                 fake_build, {'FAKE_GS_EAT_STATUS': '1'})
    assert r.stdout.count('ONCE') == 1
    assert r.returncode == 139


def test_e2e_missing_build_goes_bare_loudly(tmp_path):
    r = run_tool(['--', 'sh', '-c', 'exit 3'], tmp_path,
                 tmp_path / 'no-build-here')
    assert r.returncode == 3
    assert 'NO GAMESCOPE' in r.stderr


def test_e2e_disable_env_goes_bare(tmp_path, fake_build):
    r = run_tool(['--', 'sh', '-c', 'exit 4'], tmp_path, fake_build,
                 {'GSWRAP_DISABLE': '1'})
    assert r.returncode == 4
    assert 'NO GAMESCOPE' in r.stderr


def test_e2e_no_gamescope_flag(tmp_path, fake_build):
    r = run_tool(['--no-gamescope', '--', 'sh', '-c', 'exit 6'],
                 tmp_path, fake_build)
    assert r.returncode == 6


def test_e2e_env_passthrough(tmp_path, fake_build):
    r = run_tool(['--', 'sh', '-c', 'echo "V=$GSWRAP_TEST_CANARY"'],
                 tmp_path, fake_build, {'GSWRAP_TEST_CANARY': 'alive'})
    assert 'V=alive' in r.stdout


def test_e2e_dry_run_runs_nothing(tmp_path, fake_build):
    canary = tmp_path / 'ran'
    r = run_tool(['--dry-run', '--', 'sh', '-c', f'touch {canary}'],
                 tmp_path, fake_build)
    assert r.returncode == 0
    assert '-W 1920' in r.stdout and '-r 120' in r.stdout
    assert not canary.exists()          # printed, never executed


def test_e2e_dry_run_without_build_shows_bare(tmp_path):
    r = run_tool(['--dry-run', '--', 'mygame'], tmp_path,
                 tmp_path / 'nope')
    assert r.returncode == 0
    assert 'bare' in r.stdout


def test_e2e_forbidden_flag_refused(tmp_path, fake_build):
    r = run_tool(['--gs-arg', '-g', '--', 'true'], tmp_path, fake_build)
    assert r.returncode == 2
    assert 'NEVER' in r.stderr


def test_e2e_no_droppings(tmp_path, fake_build):
    run_tool(['--', 'sh', '-c', 'exit 0'], tmp_path, fake_build)
    run_tool(['--', 'sh', '-c', 'exit 9'], tmp_path, fake_build,
             {'FAKE_GS_EAT_STATUS': '1'})
    left = [f for f in os.listdir(tmp_path) if f.startswith('gswrap.')]
    assert left == []


def test_e2e_log_written(tmp_path, fake_build):
    run_tool(['--', 'sh', '-c', 'exit 7'], tmp_path, fake_build)
    log = (tmp_path / 'wrap.log').read_text()
    assert 'laundered' in log or 'exited 7' in log

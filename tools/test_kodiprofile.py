#!/usr/bin/env python3
"""Two resolvers, one answer: where Kodi's profile is.

`couchd/kodiprofile.py` and `server/kodiprofile.js` exist because the phone app
is Node and the console daemon is Python, and both need to read Kodi's
`userdata`. From 8 Aug 2026 that is no longer a constant: the Kodi 21 Flatpak
keeps it at `~/.var/app/tv.kodi.Kodi/data`, because the Flathub build exports
`KODI_DATA=${XDG_DATA_HOME}`.

Two implementations of one rule is exactly the shape that drifts, and the way
it drifts here is silent - the Node half keeps reading the old Kodi's jellyfin
credentials and reports "Jellyfin unavailable" while the Python half is happily
on the new profile. So the JS is actually EXECUTED (node is on the box; the
server runs on it) and its answers compared to the Python's, for every flavour
and for each of the derived paths.

The default matters as much as the mapping: with no flavour files on disk both
must answer `apt`, because that is what has been running all along and this
whole module set has to be inert until the switch is thrown.

Run:  couchd/.venv/bin/pytest tools/test_kodiprofile.py -q
"""
import json
import os
import subprocess
import sys

import pytest

HOME = os.path.expanduser('~')
COUCH = os.path.join(HOME, 'couch')
sys.path.insert(0, os.path.join(COUCH, 'couchd'))

import kodiprofile as py                                        # noqa: E402

NODE_PROBE = r'''
import * as k from '%s/server/kodiprofile.js';
const out = {
  flavour: k.flavour(),
  choice: k.flavour({ active: false }),
  profile: {}, userdata: {}, addons: {}, log: {}, addonData: {},
};
for (const name of Object.keys(k.FLAVOURS)) {
  out.profile[name] = k.profileDir(name);
  out.userdata[name] = k.userdata(name);
  out.addons[name] = k.addonsDir(name);
  out.log[name] = k.logPath(name);
  out.addonData[name] = k.addonData('plugin.video.jellyfin', name);
}
out.resolvedProfile = k.profileDir();
process.stdout.write(JSON.stringify(out));
''' % COUCH


def _node(env=None):
    """Run the JS resolver and hand back what it decided."""
    done = subprocess.run([_node_bin(), '--input-type=module', '-e', NODE_PROBE],
                          capture_output=True, text=True, timeout=30,
                          env=dict(os.environ, **(env or {})))
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _node_bin():
    for candidate in ('node', 'nodejs'):
        found = subprocess.run(['which', candidate], capture_output=True,
                               text=True)
        if found.returncode == 0:
            return found.stdout.strip()
    pytest.skip('node not on PATH')


@pytest.fixture(scope='module')
def js():
    return _node()


# =========================================================================
# the two halves agree
# =========================================================================
def test_both_halves_know_the_same_two_flavours(js):
    assert set(js['profile']) == set(py.FLAVOURS)
    assert set(js['profile']) == {'apt', 'flatpak'}


@pytest.mark.parametrize('name', ['apt', 'flatpak'])
def test_every_derived_path_matches(js, name):
    assert js['profile'][name] == py.profile_dir(name)
    assert js['userdata'][name] == py.userdata(name)
    assert js['addons'][name] == py.addons_dir(name)
    assert js['log'][name] == py.log_path(name)
    assert js['addonData'][name] == py.addon_data('plugin.video.jellyfin',
                                                  name)


def test_the_flatpak_profile_is_the_data_dir_not_a_dot_kodi(js):
    """The trap this whole module exists to avoid. The Flathub build patches
    kodi.sh with `export KODI_DATA=${XDG_DATA_HOME}`, so special://home is the
    app's data dir - NOT ~/.var/app/tv.kodi.Kodi/.kodi, which is what
    --persist=.kodi would have given and what everyone guesses."""
    expected = os.path.join(HOME, '.var', 'app', 'tv.kodi.Kodi', 'data')
    assert py.profile_dir('flatpak') == expected
    assert js['profile']['flatpak'] == expected
    assert not py.profile_dir('flatpak').endswith('.kodi')


def test_the_apt_profile_is_still_exactly_where_it_was(js):
    assert py.profile_dir('apt') == os.path.join(HOME, '.kodi')
    assert js['profile']['apt'] == os.path.join(HOME, '.kodi')


# =========================================================================
# the default: inert until the switch is thrown
# =========================================================================
def test_no_flavour_file_means_apt_on_both_sides(monkeypatch, tmp_path):
    """A box that has never launched through the flavour-aware kodi-tv: both
    halves must answer with the Kodi that has actually been running, or
    adopting this module would itself be the outage.

    Both halves get an INJECTED home. The first cut of this test read the
    live files for the JS side and asserted they were absent - true when it
    was written and false an hour later, the moment the migration actually
    ran. A test that passes because of what the box happens to be doing
    stops meaning anything the day the box does something else.
    """
    monkeypatch.setattr(py, 'ACTIVE_FILE', str(tmp_path / 'nope'))
    monkeypatch.setattr(py, 'FLAVOUR_FILE', str(tmp_path / 'nope-either'))
    assert py.flavour() == 'apt'
    assert py.profile_dir() == os.path.join(HOME, '.kodi')

    home = tmp_path / 'empty-home'
    (home / 'couch' / 'data').mkdir(parents=True)
    out = _node({'HOME': str(home)})
    assert out['flavour'] == 'apt'
    assert out['resolvedProfile'] == str(home / '.kodi')


def test_the_record_beats_the_choice(py_files):
    """kodi-tv writes the ACTIVE file at launch and a human edits the CHOICE.
    Between "Donnie picks flatpak" and "the next launch happens", the running
    Kodi is still the apt one and its profile is still the one to read."""
    py_files.choice('flatpak')
    py_files.active('apt')
    assert py.flavour() == 'apt'
    assert py.flavour(active=False) == 'flatpak'


def test_a_choice_with_no_launch_yet_is_still_apt(py_files):
    """THE REGRESSION. The first cut let the record fall back to the choice,
    and this is the state that broke it - the one that actually occurs, right
    after `kodi21-migrate switch` and before Kodi is relaunched: the choice
    says flatpak, nothing has launched it, apt-Kodi is still on screen.

    Reading the choice as though it were the record sent gestureconf to a
    profile that did not exist yet, where it found no settings.xml and fell
    back to DEFAULT_BINDINGS in silence - so the PS button quietly stopped
    doing what Donnie had bound it to, under a live console with a game
    suspended. An intention is not a fact.
    """
    py_files.choice('flatpak')                      # switch has run
    # ...and no active file at all, because nothing has launched since
    assert py.flavour() == 'apt'
    assert py.profile_dir() == os.path.join(HOME, '.kodi')
    assert py.flavour(active=False) == 'flatpak'    # the launcher still sees it


def test_the_js_half_does_not_fall_back_to_the_choice_either(tmp_path):
    """Same regression, executed in Node - where the symptom would have been
    'Jellyfin credentials unavailable', which reads like Jellyfin being down
    rather than like a path bug."""
    home = tmp_path / 'home'
    (home / 'couch' / 'data').mkdir(parents=True)
    (home / 'couch' / 'data' / 'kodi-flavour').write_text('flatpak\n')
    out = _node({'HOME': str(home)})
    assert out['flavour'] == 'apt'
    assert out['choice'] == 'flatpak'
    assert out['resolvedProfile'] == str(home / '.kodi')


def test_a_launched_flavour_moves_every_reader(py_files):
    py_files.choice('flatpak')
    py_files.active('flatpak')
    assert py.flavour() == 'flatpak'
    assert py.userdata().startswith(
        os.path.join(HOME, '.var', 'app', 'tv.kodi.Kodi', 'data'))


def test_a_typo_is_treated_as_absent_not_trusted(py_files):
    """This decides which directory the console's settings come from. A
    half-written file, a stray newline, `flatapk` - none of them may point a
    reader at a directory that does not exist."""
    py_files.active('flatapk')
    assert py.flavour() == 'apt'
    py_files.active('')
    assert py.flavour() == 'apt'
    py_files.active('  flatpak  \n')          # whitespace IS forgiven
    assert py.flavour() == 'flatpak'


def test_the_js_half_treats_a_typo_the_same_way(tmp_path):
    """Same case, executed in Node, because "unrecognised is absent" is a rule
    each half implements separately."""
    home = tmp_path / 'home'
    (home / 'couch' / 'data').mkdir(parents=True)
    (home / 'couch' / 'data' / 'kodi-flavour-active').write_text('flatapk')
    out = _node({'HOME': str(home)})
    assert out['flavour'] == 'apt'
    (home / 'couch' / 'data' / 'kodi-flavour-active').write_text('flatpak\n')
    out = _node({'HOME': str(home)})
    assert out['flavour'] == 'flatpak'
    assert out['resolvedProfile'] == str(
        home / '.var' / 'app' / 'tv.kodi.Kodi' / 'data')


@pytest.fixture
def py_files(tmp_path, monkeypatch):
    """The two flavour files, under tmp_path - never the live ones, which
    decide what the running console reads."""
    monkeypatch.setattr(py, 'ACTIVE_FILE', str(tmp_path / 'active'))
    monkeypatch.setattr(py, 'FLAVOUR_FILE', str(tmp_path / 'choice'))

    class Files:
        @staticmethod
        def active(word):
            (tmp_path / 'active').write_text(word)

        @staticmethod
        def choice(word):
            (tmp_path / 'choice').write_text(word)
    return Files


# =========================================================================
# the callers actually adopted it
# =========================================================================
#: The only places a literal ~/.kodi/userdata is allowed to survive, each
#: with the reason. Anything else is a reader that would keep looking at the
#: old profile after the switch, silently.
ALLOWED_LITERALS = {
    'couchd/gestureconf.py': 'the ImportError fallback - a deploy that lands '
                             'gestureconf without kodiprofile must still find '
                             'the bindings, and apt is the right guess',
}


def test_nothing_in_the_repo_hardcodes_the_kodi_profile_any_more():
    done = subprocess.run(
        ['grep', '-rn', '--include=*.py', '--include=*.js', r'\.kodi/userdata',
         os.path.join(COUCH, 'couchd'), os.path.join(COUCH, 'server'),
         os.path.join(COUCH, 'tools')],
        capture_output=True, text=True)
    offenders = []
    for line in done.stdout.splitlines():
        path, _, rest = line.partition(':')
        relative = os.path.relpath(path, COUCH)
        if os.path.basename(path).startswith('test_'):
            continue
        if 'kodiprofile' in os.path.basename(path):
            continue
        if relative in ALLOWED_LITERALS:
            continue
        body = rest.partition(':')[2].lstrip()
        if body.startswith(('#', '//', '*')):     # a comment describing it
            continue
        offenders.append(line)
    assert offenders == [], '\n'.join(offenders)

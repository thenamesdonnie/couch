#!/usr/bin/env python3
"""The migration itself, driven over fake profiles.

`tools/kodi21-migrate` cannot be rehearsed on the box: flatpak is not
installed until Donnie runs one sudo, and the steps that CAN run without it
(`profile`, `freeze-skin`) are exactly the two that touch the live console's
profile and the live television's skin. So they are run here against tmp_path
copies of the same shapes, with every module-level path injected - never the
real `~/.kodi`, never the real skin (the 5 Aug rule, applied to directories).

What is pinned is what would hurt:

  1. the profile copy carries the settings the whole console rides on, and
     LEAVES the things that must not travel - above all the hand-assembled
     inputstream.adaptive, which is a Debian binary addon built against Kodi
     20's ABI and Ubuntu's libc and would shadow the one the Flatpak compiles
     for itself.
  2. `freeze-skin` gets the version dance right in both directions. This is
     the step that can take the television down: Kodi 21 wants xbmc.gui
     5.17.0, Kodi 20 provides 5.16.0, no value satisfies both, and the skin
     is a symlink shared by whichever is running. The rollback must end up
     with a REAL directory pinned at 5.16.0 before the repo moves to 5.17.0.
  3. it is idempotent. A migration you cannot re-run is a migration you have
     to get right first time, in the evening, with the TV off.

Run:  couchd/.venv/bin/pytest tools/test_kodi21_migrate.py -q
"""
import importlib.machinery
import importlib.util
import os
import types
import sys

import pytest

HOME = os.path.expanduser('~')
TOOL = os.path.join(HOME, 'couch', 'tools', 'kodi21-migrate')


@pytest.fixture
def mig(tmp_path, monkeypatch):
    """kodi21-migrate with every real path moved under tmp_path.

    Also stubs `run` so no step can shell out to flatpak, pgrep or anything
    else - the two steps under test here are pure filesystem work and that is
    all they are allowed to be during the test.
    """
    spec = importlib.util.spec_from_loader(
        'kodi21_migrate', importlib.machinery.SourceFileLoader(
            'kodi21_migrate', TOOL))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    apt = tmp_path / 'apt-profile'
    new = tmp_path / 'flatpak-profile'
    skin = tmp_path / 'repo-skin'
    monkeypatch.setattr(module, 'APT_PROFILE', str(apt))
    monkeypatch.setattr(module, 'NEW_PROFILE', str(new))
    monkeypatch.setattr(module, 'SKIN_SRC', str(skin))
    # absolute, so kodiprofile's expanduser leaves them exactly as given
    monkeypatch.setattr(module.kodiprofile, 'FLAVOURS',
                        {'apt': str(apt), 'flatpak': str(new)})

    class NoRun:
        returncode = 1
        stdout = ''
        stderr = ''

    monkeypatch.setattr(module, 'run', lambda *a, **k: NoRun())

    return types.SimpleNamespace(
        mod=module, apt=apt, new=new, skin=skin,
        args=types.SimpleNamespace(force=False))


def build_profile(root, gui_version='5.16.0'):
    """A miniature of the real ~/.kodi, including the things that must not
    travel and the settings that must."""
    (root / 'userdata').mkdir(parents=True)
    (root / 'userdata' / 'guisettings.xml').write_text(
        '<settings version="2">\n'
        '  <setting id="services.webserver">true</setting>\n'
        '  <setting id="services.webserverport">8090</setting>\n'
        '  <setting id="services.esenabled" default="true">true</setting>\n'
        '  <setting id="lookandfeel.skin">skin.couch</setting>\n'
        '</settings>\n')
    for name in ('sources.xml', 'advancedsettings.xml', 'profiles.xml'):
        (root / 'userdata' / name).write_text('<x/>')
    (root / 'userdata' / 'keymaps').mkdir()
    (root / 'userdata' / 'keymaps' / 'gamepad-volume.xml').write_text('<x/>')
    (root / 'userdata' / 'addon_data' / 'peripheral.joystick').mkdir(
        parents=True)
    (root / 'userdata' / 'addon_data' / 'peripheral.joystick'
     / 'map.xml').write_text('<x/>')
    (root / 'userdata' / 'Database').mkdir()
    (root / 'userdata' / 'Database' / 'MyVideos121.db').write_bytes(b'sqlite')
    (root / 'userdata' / 'Thumbnails' / 'a').mkdir(parents=True)
    (root / 'userdata' / 'Thumbnails' / 'a' / 'x.jpg').write_bytes(b'jpg')
    # ...and the ones that must not travel
    (root / 'addons' / 'packages').mkdir(parents=True)
    (root / 'addons' / 'packages' / 'huge.zip').write_bytes(b'zip')
    (root / 'addons' / 'inputstream.adaptive' / 'lib').mkdir(parents=True)
    (root / 'addons' / 'inputstream.adaptive' / 'lib'
     / 'is.so').write_bytes(b'elf')
    (root / 'addons' / 'skin.copacetic').mkdir(parents=True)
    (root / 'addons' / 'skin.copacetic' / 'addon.xml').write_text('<x/>')
    (root / 'addons' / 'skin.arctic.zephyr.mod').mkdir(parents=True)
    (root / 'addons' / 'skin.arctic.zephyr.mod' / 'addon.xml').write_text('<x/>')
    (root / 'temp').mkdir()
    (root / 'temp' / 'kodi.log').write_text('log')
    # a real addon that SHOULD travel
    (root / 'addons' / 'plugin.video.jellyfin').mkdir(parents=True)
    (root / 'addons' / 'plugin.video.jellyfin' / 'addon.xml').write_text('<x/>')


def build_skin(root, gui_version='5.16.0'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'addon.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<addon id="skin.couch" version="1.0.0">\n'
        '\t<requires>\n'
        '\t\t<import addon="xbmc.gui" version="%s" />\n'
        '\t</requires>\n'
        '</addon>\n' % gui_version)
    (root / '16x9').mkdir(exist_ok=True)
    (root / '16x9' / 'Home.xml').write_text('<window/>')


# =========================================================================
# 1. the profile copy
# =========================================================================
def test_the_console_settings_arrive(mig, capsys):
    build_profile(mig.apt)
    assert mig.mod.profile(mig.args) == 0
    new = mig.new
    assert (new / 'userdata' / 'guisettings.xml').exists()
    assert (new / 'userdata' / 'sources.xml').exists()
    assert (new / 'userdata' / 'keymaps' / 'gamepad-volume.xml').exists()
    assert (new / 'userdata' / 'Database' / 'MyVideos121.db').exists()
    assert (new / 'addons' / 'plugin.video.jellyfin' / 'addon.xml').exists()


def test_the_dualsense_mapping_travels(mig):
    """addon_data/peripheral.joystick is the pad's button map. Without it
    every PS-button gesture aims at a button that no longer means what it
    meant, which would read as the gestures being broken."""
    build_profile(mig.apt)
    mig.mod.profile(mig.args)
    assert (mig.new / 'userdata' / 'addon_data' / 'peripheral.joystick'
            / 'map.xml').exists()


def test_the_debian_binary_addon_does_not_travel(mig):
    """The one that would fail confusingly: it is built against Kodi 20's
    binary-addon ABI and Ubuntu's libc, it needs a libwebm hand-placed in
    ~/.local/lib, and inside the runtime it would SHADOW the
    inputstream.adaptive the Flatpak compiles for itself - taking YouTube
    playback with it."""
    build_profile(mig.apt)
    mig.mod.profile(mig.args)
    assert not (mig.new / 'addons' / 'inputstream.adaptive').exists()


@pytest.mark.parametrize('unwanted', [
    'addons/packages',                 # a cache
    'addons/skin.copacetic',           # xbmc.gui 5.16.0, refused by Kodi 21
    'addons/skin.arctic.zephyr.mod',   # xbmc.gui 5.15.0, refused harder
    'temp',
])
def test_what_should_not_travel_does_not(mig, unwanted):
    build_profile(mig.apt)
    mig.mod.profile(mig.args)
    assert not (mig.new / unwanted).exists()


def test_the_copy_checks_the_settings_the_console_rides_on(mig, capsys):
    """A profile that arrives without the webserver is a console with no
    controller handoff, no phone app and no way in - and it would look like
    Kodi simply not starting. The copy says so instead."""
    build_profile(mig.apt)
    gui = mig.apt / 'userdata' / 'guisettings.xml'
    gui.write_text(gui.read_text().replace(
        '<setting id="services.webserver">true</setting>',
        '<setting id="services.webserver">false</setting>'))
    mig.mod.profile(mig.args)
    out = capsys.readouterr().out
    assert 'FAIL services.webserver' in out
    assert 'the console talks to Kodi over this' in out


def test_the_copy_is_idempotent_and_picks_up_later_changes(mig, capsys):
    build_profile(mig.apt)
    mig.mod.profile(mig.args)
    first = capsys.readouterr().out
    assert 'copied 0 file(s)' not in first

    mig.mod.profile(mig.args)
    assert 'copied 0 file(s)' in capsys.readouterr().out

    # a setting changed on the old profile between the rehearsal and the
    # real cutover: the second run must carry it over
    target = mig.apt / 'userdata' / 'sources.xml'
    target.write_text('<sources><changed/></sources>')
    os.utime(target, None)
    mig.mod.profile(mig.args)
    assert (mig.new / 'userdata' / 'sources.xml').read_text() \
        == '<sources><changed/></sources>'


def test_a_live_kodi_stops_the_copy(mig, monkeypatch):
    """Copying a live profile catches its sqlite databases mid-write."""
    build_profile(mig.apt)

    class Running:
        returncode = 0
        stdout = '4242\n'
        stderr = ''
    monkeypatch.setattr(mig.mod, 'run', lambda *a, **k: Running())
    with pytest.raises(mig.mod.Fail, match='Kodi is running'):
        mig.mod.profile(mig.args)
    mig.args.force = True
    assert mig.mod.profile(mig.args) == 0          # ...unless you insist


# =========================================================================
# 2. freeze-skin: the step that can take the television down
# =========================================================================
def test_the_rollback_gets_a_real_nexus_copy_before_the_repo_moves(mig):
    """The whole dance in one test. Before: apt-Kodi shares the repo skin by
    symlink, and the repo says 5.16.0. After: apt-Kodi owns a real directory
    still saying 5.16.0, and the repo - now 5.17.0 - is symlinked into the
    Flatpak profile. Get the order wrong and Kodi 20 refuses the skin and
    boots Estuary on the television."""
    build_skin(mig.skin, '5.16.0')
    apt_addons = mig.apt / 'addons'
    apt_addons.mkdir(parents=True)
    os.symlink(str(mig.skin), str(apt_addons / 'skin.couch'))

    assert mig.mod.freeze_skin(mig.args) == 0

    frozen = apt_addons / 'skin.couch'
    assert frozen.is_dir() and not frozen.is_symlink()
    assert 'version="5.16.0"' in (frozen / 'addon.xml').read_text()
    assert (frozen / '16x9' / 'Home.xml').exists()

    assert 'version="5.17.0"' in (mig.skin / 'addon.xml').read_text()

    live = mig.new / 'addons' / 'skin.couch'
    assert live.is_symlink()
    assert os.path.realpath(str(live)) == os.path.realpath(str(mig.skin))


def test_freeze_skin_is_idempotent(mig):
    build_skin(mig.skin, '5.16.0')
    apt_addons = mig.apt / 'addons'
    apt_addons.mkdir(parents=True)
    os.symlink(str(mig.skin), str(apt_addons / 'skin.couch'))

    mig.mod.freeze_skin(mig.args)
    mig.mod.freeze_skin(mig.args)

    # the frozen copy is NOT re-frozen from a repo that has since moved to
    # 5.17.0 - that would hand the rollback a skin Kodi 20 refuses
    frozen = apt_addons / 'skin.couch'
    assert 'version="5.16.0"' in (frozen / 'addon.xml').read_text()
    assert 'version="5.17.0"' in (mig.skin / 'addon.xml').read_text()


def test_a_live_kodi_stops_the_skin_swap(mig, monkeypatch):
    build_skin(mig.skin, '5.16.0')
    (mig.apt / 'addons').mkdir(parents=True)
    os.symlink(str(mig.skin), str(mig.apt / 'addons' / 'skin.couch'))

    class Running:
        returncode = 0
        stdout = '4242\n'
        stderr = ''
    monkeypatch.setattr(mig.mod, 'run', lambda *a, **k: Running())
    with pytest.raises(mig.mod.Fail, match='Kodi is running'):
        mig.mod.freeze_skin(mig.args)
    assert (mig.apt / 'addons' / 'skin.couch').is_symlink()   # untouched
    assert 'version="5.16.0"' in (mig.skin / 'addon.xml').read_text()


# =========================================================================
# 3. the shape of the thing
# =========================================================================
def test_every_override_carries_its_reason(mig):
    """Six months from now the permission set must not be a mystery."""
    flags = [flag for flag, _ in mig.mod.OVERRIDES]
    assert flags == ['--filesystem=home', '--filesystem=/tmp',
                     '--talk-name=org.freedesktop.Flatpak']
    for flag, why in mig.mod.OVERRIDES:
        assert len(why) > 40, flag


def test_every_skipped_path_carries_its_reason(mig):
    for path, why in mig.mod.PROFILE_SKIP.items():
        assert len(why) > 10, path


def test_all_stops_before_switching(mig):
    """`all` prepares; it does not change which Kodi launches. That is a
    decision, taken once, in front of the television."""
    assert 'switch' not in mig.mod.ALL
    assert 'rollback' not in mig.mod.ALL
    assert mig.mod.ALL[-1] == 'verify'


def test_the_tool_compiles():
    import subprocess
    subprocess.run([sys.executable, '-m', 'py_compile', TOOL], check=True)

#!/usr/bin/env python3
"""deploy-addons, and the one move that would quietly cut the parachute.

Since the Kodi 21 migration there are two profiles: `~/.kodi` (apt Kodi 20,
the rollback) and `~/.var/app/tv.kodi.Kodi/data` (Kodi 21, live). They are NOT
symmetrical, and the asymmetry is the whole subject of this file:

  * the Flatpak profile gets `skin.couch` as a SYMLINK into the git checkout,
    because that skin is edited constantly and now asks for xbmc.gui 5.17.0.
  * the apt profile gets a frozen REAL COPY, pinned at 5.16.0, because Kodi 20
    refuses 5.17.0 and no single value satisfies both.

So "deploy the skin to both profiles" is not a helpful thing to do - it is the
failure. `--profile both` is exactly what the patch-set README tells people to
run, and before the audit that call replaced the frozen copy with a symlink to
the 5.17.0 repo, moving the real directory aside under a `.replaced` suffix.
Nobody would notice until a rollback booted Estuary, at the worst possible
moment, which is the only moment anyone rolls back.

Run:  couchd/.venv/bin/pytest tools/test_deploy_addons.py -q
"""
import importlib.machinery
import importlib.util
import os
import types

import pytest

HOME = os.path.expanduser('~')
TOOL = os.path.join(HOME, 'couch', 'tools', 'deploy-addons')


@pytest.fixture
def dep(tmp_path, monkeypatch):
    """deploy-addons pointed at fake profiles and a fake addon source."""
    spec = importlib.util.spec_from_loader(
        'deploy_addons', importlib.machinery.SourceFileLoader(
            'deploy_addons', TOOL))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    apt = tmp_path / 'apt'
    new = tmp_path / 'flatpak'
    src = tmp_path / 'kodi-addons'
    (src / 'skin.couch' / '16x9').mkdir(parents=True)
    (src / 'skin.couch' / 'addon.xml').write_text('<addon>5.17.0</addon>')

    monkeypatch.setattr(module, 'ADDON_SRC', str(src))
    monkeypatch.setattr(module, 'OWN_ADDONS', [])
    monkeypatch.setattr(module, 'FILE_DROPS', [])
    monkeypatch.setattr(module, 'HAND_PATCHES', [])
    monkeypatch.setattr(module, 'LINKED_ADDONS',
                        {'skin.couch': str(src / 'skin.couch')})
    monkeypatch.setattr(module.kodiprofile, 'FLAVOURS',
                        {'apt': str(apt), 'flatpak': str(new)})
    for root in (apt, new):
        (root / 'addons').mkdir(parents=True)

    return types.SimpleNamespace(mod=module, apt=apt, new=new, src=src,
                                 args=types.SimpleNamespace(force=False))


def frozen_copy(profile, gui='5.16.0'):
    """What freeze-skin leaves in the apt profile: a real directory."""
    d = profile / 'addons' / 'skin.couch'
    (d / '16x9').mkdir(parents=True)
    (d / 'addon.xml').write_text('<addon>%s</addon>' % gui)
    return d


# =========================================================================
# the parachute
# =========================================================================
def test_a_frozen_skin_copy_is_never_replaced_by_a_symlink(dep, capsys):
    """AUDIT [A]. The rollback's skin must survive a deploy."""
    frozen = frozen_copy(dep.apt)
    dep.mod.deploy('apt', check=False)

    assert frozen.is_dir() and not frozen.is_symlink()
    assert frozen.joinpath('addon.xml').read_text() == '<addon>5.16.0</addon>'
    assert 'left alone' in capsys.readouterr().out


def test_nothing_is_moved_aside_either(dep):
    """The old behaviour renamed it to skin.couch.replaced, which is
    destruction with a longer name: Kodi does not load `.replaced`, so the
    rollback still had no skin."""
    frozen_copy(dep.apt)
    dep.mod.deploy('apt', check=False)
    assert not (dep.apt / 'addons' / 'skin.couch.replaced').exists()
    assert list((dep.apt / 'addons').iterdir()) == [
        dep.apt / 'addons' / 'skin.couch']


def test_profile_both_is_safe_which_is_what_the_readme_tells_you_to_run(dep):
    """The exact invocation in kodi-addons/copacetic-helper-patches/README.md.
    Both profiles end correct AND DIFFERENT: a frozen copy on one side, a live
    symlink on the other."""
    frozen_copy(dep.apt)
    for flavour in ('apt', 'flatpak'):
        dep.mod.deploy(flavour, check=False)

    apt_skin = dep.apt / 'addons' / 'skin.couch'
    new_skin = dep.new / 'addons' / 'skin.couch'
    assert apt_skin.is_dir() and not apt_skin.is_symlink()
    assert new_skin.is_symlink()
    assert os.path.realpath(str(new_skin)) == os.path.realpath(
        str(dep.src / 'skin.couch'))


# =========================================================================
# ...while still doing its actual job
# =========================================================================
def test_a_missing_link_is_still_created(dep):
    dep.mod.deploy('flatpak', check=False)
    assert (dep.new / 'addons' / 'skin.couch').is_symlink()


def test_a_symlink_pointing_somewhere_else_is_repaired(dep):
    """A stale symlink (an older checkout path, a moved repo) is ours to fix -
    it is not somebody's deliberate copy."""
    stale = dep.new / 'addons' / 'elsewhere'
    stale.mkdir()
    os.symlink(str(stale), str(dep.new / 'addons' / 'skin.couch'))
    dep.mod.deploy('flatpak', check=False)
    link = dep.new / 'addons' / 'skin.couch'
    assert link.is_symlink()
    assert os.path.realpath(str(link)) == os.path.realpath(
        str(dep.src / 'skin.couch'))


def test_a_correct_link_is_left_alone_and_counted_as_current(dep, capsys):
    os.symlink(str(dep.src / 'skin.couch'),
               str(dep.new / 'addons' / 'skin.couch'))
    dep.mod.deploy('flatpak', check=False)
    assert '1 file(s) already current' in capsys.readouterr().out


def test_check_mode_writes_nothing(dep):
    dep.mod.deploy('flatpak', check=True)
    assert not (dep.new / 'addons' / 'skin.couch').exists()

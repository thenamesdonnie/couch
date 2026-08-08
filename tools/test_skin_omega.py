#!/usr/bin/env python3
"""skin.couch against Kodi 21, and the one way to brick the TV with it.

Kodi 21's `addons/xbmc.gui/addon.xml` reads

    <addon id="xbmc.gui" version="5.17.0" ...>
      <backwards-compatibility abi="5.17.0"/>

and Kodi 20's carries no `backwards-compatibility` element at all. So a skin
asking for 5.16.0 is refused by 21, a skin asking for 5.17.0 is refused by 20,
and there is no value that satisfies both. The skin is a SYMLINK shared with
whichever Kodi is running, which makes the version number in `addon.xml` a
live wire: bumping it while apt-Kodi is the one launching drops the TV to
Estuary at its next restart, with nobody home.

That invariant is the last test in this file and it is the point of the file.

The rest pins the actual Omega work, which was small and is now done:

  * Kodi 21 deleted WINDOW_DIALOG_FAVOURITES (10134) - verified in
    xbmc/guilib/WindowIDs.h at 20.5-Nexus vs 21.3-Omega - leaving only
    WINDOW_FAVOURITES (10060). The name `favourites` therefore no longer
    translates and every condition using it is permanently false; the name
    `favouritesbrowser` translates on BOTH builds
    (xbmc/input/WindowTranslator.cpp, both tags). So DialogFavourites.xml is
    gone, MyFavourites.xml replaces it, and the skin's default menu entry
    points at the name that works either way.
  * everything else the bump touches was already satisfied here: the disabled
    slider textures, DialogColorPicker/colorbutton, and no use of
    Network.DHCPAddress (the only infolabel v21 removed).

Run:  couchd/.venv/bin/pytest tools/test_skin_omega.py -q
"""
import glob
import os
import re
import xml.etree.ElementTree as ET

import pytest

HOME = os.path.expanduser('~')
SKIN = os.path.join(HOME, 'couch', 'kodi-addons', 'skin.couch')
XML = os.path.join(SKIN, '16x9')

NEXUS_GUI = '5.16.0'
OMEGA_GUI = '5.17.0'

#: parked, not loaded - Kodi maps window XMLs by filename and this is not one.
#: Kept as the pre-Stagelight Home for reference, so it still names the dead
#: window and that is fine.
PARKED = {'Home.xml.copacetic'}

#: referenced-but-undefined include inherited from Copacetic 1.6.1, in the
#: music visualisation screen this box never opens. Pre-existing, unrelated to
#: Omega, listed so the integrity test below can be strict about everything
#: else.
KNOWN_DANGLING_INCLUDES = {'Like_focused'}


def skin_xml_files():
    return [p for p in sorted(glob.glob(os.path.join(SKIN, '**', '*.xml'),
                                        recursive=True))
            if os.path.basename(p) not in PARKED]


def loaded_text():
    """Every XML file Kodi will actually parse, as (path, text)."""
    for path in skin_xml_files():
        with open(path, encoding='utf-8') as handle:
            yield path, handle.read()


# =========================================================================
# the favourites move
# =========================================================================
def test_nothing_names_the_window_kodi_21_deleted():
    """`favourites` translated to WINDOW_DIALOG_FAVOURITES, which no longer
    exists. Conditions on it do not error - they go quietly, permanently
    false, which is the worst way for skin logic to fail."""
    offenders = []
    for path, text in loaded_text():
        for match in re.finditer(r'(Window\.Is|Window\.IsVisible|'
                                 r'ActivateWindow)\(favourites\)', text):
            offenders.append('%s: %s' % (os.path.relpath(path, SKIN),
                                         match.group(0)))
    assert offenders == [], '\n'.join(offenders)


def test_the_skin_setting_names_were_left_alone():
    """`Widget3_Content_Favourites` is a skin SETTING with the word in it,
    not a window reference. Blanket search-and-replace would have eaten nine
    widget slots; this pins that it did not."""
    variables = os.path.join(XML, 'Variables_Labels_Widgets.xml')
    text = open(variables, encoding='utf-8').read()
    assert text.count('_Content_Favourites)') == 9


def test_dialogfavourites_is_gone_and_myfavourites_replaces_it():
    assert not os.path.exists(os.path.join(XML, 'DialogFavourites.xml'))
    assert os.path.exists(os.path.join(XML, 'MyFavourites.xml'))


def test_myfavourites_declares_the_window_that_still_exists():
    root = ET.parse(os.path.join(XML, 'MyFavourites.xml')).getroot()
    assert root.tag == 'window'
    includes = [c.get('content') for c in root.find('controls')]
    assert 'favourites_Controls' in includes
    assert 'favourites_Views' in includes


def test_the_default_menu_entry_works_on_both_builds():
    """`favouritesbrowser` -> WINDOW_FAVOURITES in Nexus AND Omega
    (WindowTranslator.cpp, both tags), so this one entry does not need a
    flavour of its own."""
    data = os.path.join(SKIN, 'shortcuts', 'mainmenu.DATA.xml')
    text = open(data, encoding='utf-8').read()
    assert 'ActivateWindow(favouritesbrowser)' in text
    assert 'ActivateWindow(favourites)' not in text


# =========================================================================
# things the bump did NOT need, checked so we know they were checked
# =========================================================================
def test_the_disabled_slider_textures_are_already_there():
    defaults = open(os.path.join(XML, 'Defaults.xml'), encoding='utf-8').read()
    assert defaults.count('<texturesliderbardisabled') == 2
    assert defaults.count('<textureslidernibdisabled') == 2


def test_the_colour_picker_exists():
    assert os.path.exists(os.path.join(XML, 'DialogColorPicker.xml'))


def test_no_infolabel_that_v21_removed():
    """Network.DHCPAddress is the only one v21 dropped."""
    for path, text in loaded_text():
        assert 'Network.DHCPAddress' not in text, path


# =========================================================================
# structural integrity - the cheap net under any skin edit
# =========================================================================
def test_every_skin_xml_is_well_formed():
    bad = []
    for path in skin_xml_files():
        try:
            ET.parse(path)
        except ET.ParseError as e:
            bad.append('%s: %s' % (os.path.relpath(path, SKIN), e))
    assert bad == [], '\n'.join(bad)


def test_every_referenced_include_is_defined():
    """The failure mode of the favourites edit if it had gone wrong: a
    window referencing an include nobody defines renders empty, and Kodi says
    so only in the log."""
    defined, used = set(), {}
    for path, text in loaded_text():
        defined |= set(re.findall(r'<include name="([^"]+)"', text))
        for match in re.finditer(r'<include content="([^"$]+)"', text):
            used.setdefault(match.group(1), path)
    dangling = {name: path for name, path in used.items()
                if name not in defined and name not in KNOWN_DANGLING_INCLUDES}
    assert dangling == {}, dangling
    # ...and the two new ones really are defined, not merely unreferenced
    assert 'favourites_Controls' in defined
    assert 'favourites_Views' in defined


# =========================================================================
# the live wire
# =========================================================================
def gui_version():
    text = open(os.path.join(SKIN, 'addon.xml'), encoding='utf-8').read()
    match = re.search(r'<import addon="xbmc\.gui" version="([^"]+)"', text)
    assert match, 'skin.couch does not declare an xbmc.gui import'
    return match.group(1)


def test_the_gui_version_is_one_of_the_two_we_know_about():
    assert gui_version() in (NEXUS_GUI, OMEGA_GUI)


def test_the_skin_version_matches_the_kodi_that_will_load_it():
    """THE ONE THAT MATTERS.

    ~/.kodi/addons/skin.couch is a symlink to this repo, so apt-Kodi loads
    whatever addon.xml says right now. Bumping to 5.17.0 while apt-Kodi is
    still the launcher means the next Kodi restart - a crash, a reboot,
    anything - finds an incompatible skin and falls back to Estuary, on a
    television, with nobody in the room.

    The bump therefore belongs to the cutover, where tools/kodi21-migrate
    does it in the same breath as freezing a 5.16.0 copy into the apt profile
    and pointing the symlink at the Flatpak's. Until then: 5.16.0.
    """
    import sys
    sys.path.insert(0, os.path.join(HOME, 'couch', 'couchd'))
    import kodiprofile

    apt_skin = os.path.join(kodiprofile.addons_dir('apt'), 'skin.couch')
    apt_kodi_shares_this_skin = (
        os.path.islink(apt_skin)
        and os.path.realpath(apt_skin) == os.path.realpath(SKIN))

    if apt_kodi_shares_this_skin:
        assert gui_version() == NEXUS_GUI, (
            'skin.couch asks for xbmc.gui %s, but %s is still a symlink to '
            'this repo - apt-Kodi 20 would refuse the skin and boot Estuary. '
            'Freeze a Nexus copy into the apt profile first '
            '(tools/kodi21-migrate freeze-skin).' % (gui_version(), apt_skin))


@pytest.mark.skipif(
    not os.path.exists('/home/ds2000/couch/tools/kodi21-migrate'),
    reason='the migration tool is not present')
def test_the_migration_tool_owns_the_bump():
    """So the rule above has somewhere to be enforced from."""
    text = open('/home/ds2000/couch/tools/kodi21-migrate',
                encoding='utf-8').read()
    assert OMEGA_GUI in text and NEXUS_GUI in text

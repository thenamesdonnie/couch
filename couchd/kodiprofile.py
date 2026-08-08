#!/usr/bin/env python3
"""Where Kodi keeps its profile - which stopped being one answer on 8 Aug 2026.

Under apt-Kodi it is `~/.kodi`, as it has been since the box was built. Under
the Kodi 21 Flatpak it is `~/.var/app/tv.kodi.Kodi/data`, because the Flathub
build patches `kodi.sh` to `export KODI_DATA=${XDG_DATA_HOME}` - so it is not
`~/.kodi` and it is not `~/.var/app/tv.kodi.Kodi/.kodi` either, which are the
two guesses a reasonable person makes first.

Both builds stay installed for as long as apt-Kodi is the rollback, so the
answer is not "detect which one exists" - both exist. It is "which one did
`kodi-tv` last launch", and kodi-tv records exactly that:

    ~/couch/data/kodi-flavour-active     <- written at every launch
    ~/couch/data/kodi-flavour            <- the CHOICE, edited by hand

An absent active-flavour file means nothing has launched since the file was
introduced, which on a box that has been running apt-Kodi all along is
correctly read as `apt`. That default is what keeps this module inert until
the switch is thrown: every caller can adopt it today and see no change.

server/kodiprofile.js is the same rules for the Node side; the two are kept
in step by tools/test_kodiprofile.py, which reads both files.
"""
import os

__all__ = ['FLAVOURS', 'flavour', 'profile_dir', 'userdata', 'addon_data',
           'addons_dir', 'log_path', 'FLAVOUR_FILE', 'ACTIVE_FILE']

#: app id on Flathub. Not org.xbmc.Kodi, which 404s.
FLATPAK_APP_ID = 'tv.kodi.Kodi'

#: profile root per flavour.
FLAVOURS = {
    'apt': '~/.kodi',
    'flatpak': '~/.var/app/%s/data' % FLATPAK_APP_ID,
}

#: the choice (what the next launch will use) and the record (what the last
#: launch actually used). Readers want the record.
FLAVOUR_FILE = os.path.expanduser('~/couch/data/kodi-flavour')
ACTIVE_FILE = os.path.expanduser('~/couch/data/kodi-flavour-active')

DEFAULT = 'apt'


def _read(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.read().strip()
    except OSError:
        return ''


def flavour(active=True):
    """'apt' or 'flatpak'.

    `active=True` (the default, and what every reader wants) answers with the
    flavour that is actually running. `active=False` answers with the choice,
    which is what a launcher wants. An unrecognised word in either file is
    treated as absent rather than trusted: this decides which directory the
    console's settings are read from, and a typo must not send it somewhere
    that does not exist.
    """
    for path in ([ACTIVE_FILE, FLAVOUR_FILE] if active else [FLAVOUR_FILE]):
        word = _read(path)
        if word in FLAVOURS:
            return word
    return DEFAULT


def profile_dir(name=None):
    """special://home for the given (or running) flavour, absolute."""
    return os.path.expanduser(FLAVOURS[name or flavour()])


def userdata(name=None):
    return os.path.join(profile_dir(name), 'userdata')


def addon_data(addon_id, name=None):
    return os.path.join(userdata(name), 'addon_data', addon_id)


def addons_dir(name=None):
    return os.path.join(profile_dir(name), 'addons')


def log_path(name=None):
    """Kodi's own log. The Flatpak writes it inside its data dir like the apt
    build does, so this is just the profile root plus temp/kodi.log - but the
    root is the part that moved, and every reader of the log had it hardcoded.
    """
    return os.path.join(profile_dir(name), 'temp', 'kodi.log')

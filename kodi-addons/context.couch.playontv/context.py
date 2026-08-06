# -*- coding: utf-8 -*-
"""Context item entry: "Play on TV (HDR)".

Hands the selected movie/episode to the couch server, which wakes the LG TV,
opens its native Jellyfin app and starts playback there (real 4K HDR; the PC
path tonemaps). This script only extracts the Jellyfin id, fires the POST and
relays the server's stage snapshots as notifications. It runs in its own
Python invocation, so staying alive to poll costs the Kodi UI nothing; there
is deliberately no modal anywhere in this file.

CSRF: the couch server's cover is an Origin check on POSTs; requests that
carry no Origin header (curl, this script) pass by design, same as the phone
app's same-origin fetches. So: no token, and never add an Origin header here.
"""

import json
import os
import sys
import urllib.error
import urllib.request

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

import xbmc  # noqa: E402
import xbmcgui  # noqa: E402
import xbmcvfs  # noqa: E402

import playontv  # noqa: E402

BASE = 'http://localhost:8790'
HEADING = 'Play on TV'


def notify(message, error=False):
    icon = xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO
    xbmcgui.Dialog().notification(HEADING, message, icon, 4500, sound=False)


def listitem_facts():
    """What the selected ListItem carries, via sys.listitem with the InfoLabel
    fallback the jellyfin addon's own context script uses. Returns
    (jellyfinid property, kodi db id, media type); any of them may be empty.
    """
    prop = kodi_id = media = None
    try:
        li = sys.listitem
        tag = li.getVideoInfoTag()
        kodi_id = tag.getDbId()
        media = tag.getMediaType()
        prop = li.getProperty('jellyfinid')
    except AttributeError:
        pass
    if not prop:
        prop = xbmc.getInfoLabel('ListItem.Property(jellyfinid)') or None
    if not kodi_id or kodi_id == -1:
        kodi_id = xbmc.getInfoLabel('ListItem.DBID')
    if not media:
        media = xbmc.getInfoLabel('ListItem.DBTYPE')
    return prop, kodi_id, media


def post_play(item_id):
    """POST the handoff. Returns (http status, body text); (None, '') when the
    server is unreachable."""
    req = urllib.request.Request(
        BASE + '/api/tv/play',
        data=json.dumps({'itemId': item_id}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace')
        except OSError:
            return e.code, ''
    except (urllib.error.URLError, OSError):
        return None, ''


def fetch_status(seq):
    """One long-poll leg; the server holds up to ~25s, so the timeout sits
    just past that. None on any network trouble."""
    url = BASE + '/api/tv/play/status?seq=%s' % seq
    try:
        with urllib.request.urlopen(url, timeout=35) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def main():
    prop, kodi_id, media = listitem_facts()
    db_path = xbmcvfs.translatePath('special://database/jellyfin.db')
    item_id = playontv.resolve_item_id(prop, kodi_id, media, db_path)
    if not item_id:
        notify('Could not find this item on the Jellyfin server', error=True)
        return

    code, body = post_play(item_id)
    if code is None:
        notify('Couch server is not reachable', error=True)
        return
    ok, first, err = playontv.parse_start(code, body)
    if not ok:
        notify(err, error=True)
        return

    playontv.follow_stages(first, fetch_status, notify)


if __name__ == '__main__':
    main()

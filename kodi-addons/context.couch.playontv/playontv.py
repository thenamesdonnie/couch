"""Pure logic for the "Play on TV (HDR)" context item.

Everything here is importable without Kodi: finding the Jellyfin item id for
a library row, reading the couch server's answers, and walking the handoff
stages. The impure edges (sys.listitem, HTTP, xbmcgui notifications) live in
context.py and inject their results into these functions, which is what makes
tools/test_playontv.py possible on a headless box.

The id chain, in the order the jellyfin-for-kodi addon itself trusts:
  1. the ListItem's jellyfinid property (set on plugin:// rows),
  2. the jellyfin.db mapping table, keyed on (kodi_id, media_type), which is
     how native-mode library rows (plain DBID, no property) resolve.
"""

import json
import re
import sqlite3
import time

# The couch server refuses anything that is not exactly 32 lowercase hex.
ITEM_ID = re.compile(r'^[0-9a-f]{32}$')

# The only media types this feature makes sense for; also a guard so a stray
# season/set DBID can never resolve to some other table row's id.
PLAYABLE = ('movie', 'episode')

# Stages the server never leaves on its own once reached.
FINAL_STAGES = ('playing', 'failed', 'idle')

STAGE_TEXT = {
    'waking': 'Waking the TV',
    'launching': 'Opening Jellyfin on the TV',
    'connecting': 'Waiting for the TV to start playback',
    'playing': 'Playing on TV',
    'idle': 'Handoff ended',
}


def normalize_item_id(raw):
    """A Jellyfin id in any of the shapes the addon stores it in
    (plain 32-hex, dashed GUID, mixed case) -> canonical 32 lowercase hex,
    or None if it is not an id at all."""
    if not raw:
        return None
    s = str(raw).strip().lower().replace('-', '')
    return s if ITEM_ID.match(s) else None


def lookup_jellyfin_id(db_path, kodi_id, media_type):
    """(kodi_id, media_type) -> jellyfin id via the sync addon's mapping db.

    Opens read-only so a scan can never write (or create) the database, and
    answers None for anything unexpected: missing db, unsynced item, a type
    we do not play.
    """
    if media_type not in PLAYABLE:
        return None
    try:
        kodi_id = int(kodi_id)
    except (TypeError, ValueError):
        return None
    if kodi_id <= 0:
        return None
    try:
        con = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
    except sqlite3.Error:
        return None
    try:
        row = con.execute(
            'SELECT jellyfin_id FROM jellyfin WHERE kodi_id = ? AND media_type = ?',
            (kodi_id, media_type)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return normalize_item_id(row[0]) if row else None


def resolve_item_id(prop_id, kodi_id, media_type, db_path):
    """The full extraction chain: ListItem property first, database second."""
    return (normalize_item_id(prop_id)
            or lookup_jellyfin_id(db_path, kodi_id, media_type))


def parse_start(code, body):
    """The POST /api/tv/play answer -> (ok, first_status, error_message).

    200 with a stage snapshot means the handoff is running. Anything else
    (409 already busy, 503 not configured, proxy junk) becomes a short
    human message for the failure notification.
    """
    try:
        data = json.loads(body) if body else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if code == 200 and data.get('stage'):
        return True, data, None
    err = data.get('error') or ('couch server answered %s' % code)
    return False, None, err


def message_for(status):
    """One stage snapshot -> the notification line for it."""
    stage = status.get('stage')
    if stage == 'failed':
        return 'Failed: %s' % (status.get('error') or 'unknown error')
    if stage == 'playing':
        item = status.get('item') or {}
        name = item.get('name')
        return 'Playing on TV: %s' % name if name else 'Playing on TV'
    return STAGE_TEXT.get(stage, str(stage))


def follow_stages(first, fetch, notify, clock=time.monotonic,
                  max_seconds=180, max_misses=3):
    """Walk the handoff to a final stage, notifying once per stage change.

    first   -- the status snapshot the POST returned
    fetch   -- fetch(seq) -> next status dict, or None on a network error;
               expected to long-poll (the server holds ~25s), so this loop
               never sleeps itself
    notify  -- notify(message, error=bool); must not block
    Returns the last stage seen ('playing', 'failed', 'idle', 'lost', or
    whatever was current when the deadline passed).

    A long-poll that times out server-side answers with the SAME stage and
    seq; the stage-change check keeps that from re-notifying. max_seconds is
    a hard ceiling well above the server's own wake + session timeouts, so
    normally the server reaches playing or failed first.
    """
    status = first or {}
    last = None
    deadline = clock() + max_seconds
    misses = 0
    while True:
        stage = status.get('stage')
        if stage and stage != last:
            notify(message_for(status), error=(stage == 'failed'))
            last = stage
        if stage in FINAL_STAGES:
            return stage
        if clock() >= deadline:
            return last
        nxt = fetch(status.get('seq'))
        if nxt is None:
            misses += 1
            if misses >= max_misses:
                notify('Lost contact with the couch server', error=True)
                return 'lost'
            continue
        misses = 0
        status = nxt

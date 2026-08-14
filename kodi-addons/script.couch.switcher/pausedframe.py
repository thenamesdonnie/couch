# Pure helpers for the switcher's freeze-frame backdrop. No Kodi imports on
# purpose: default.py owns the window, the timer and the property; this file
# owns the two decisions that are worth unit-testing without a TV attached -
# "which jpg is the session's frame?" and "which appid is the session?".
#
# The frames are written by ~/.local/bin/pause-snap at suspend time as
#   <safe(appid)>__<epoch_ms>.jpg        (the fullscreen frame - what we want)
#   <safe(appid)>__<epoch_ms>.tile.jpg   (the poster crop - never ours)
# and cleared on resume. safe() below MUST mirror pause-snap's own sanitizer,
# because the prefix match only works if both sides mangle a shadPS4 eboot
# path the same way.
import os
import re

# How stale a capture may be and still be "this pause". The double-tap flow is
# freeze -> snapshot -> show kodi -> dialog, so a legitimate frame is seconds
# old at most; a minute covers a slow capture without ever resurrecting the
# frame of an earlier suspend that somehow escaped --clear.
FRESH_MS = 60_000
# Filesystem timestamps and time.time() can disagree by a hair; a capture
# "from the future" by more than this is somebody else's clock problem.
SKEW_MS = 2_000


def safe(appid):
    """pause-snap's filename mangle, verbatim (its safe()): the prefix half of
    every frame filename. Kept byte-identical so prefix matching cannot drift."""
    return re.sub(r'[^A-Za-z0-9._-]', '_', str(appid))[:100] or 'game'


def frame_epoch_ms(name):
    """The capture time a frame filename carries, or None for anything that is
    not a fullscreen frame (tiles, strays, unparsable names)."""
    if not name.endswith('.jpg') or name.endswith('.tile.jpg'):
        return None
    stem = name[:-len('.jpg')]
    sep = stem.rfind('__')
    if sep < 0:
        return None
    tail = stem[sep + 2:]
    if not tail.isdigit():
        return None
    return int(tail)


def newest_frame(dirpath, appid, now_ms, fresh_ms=FRESH_MS, skew_ms=SKEW_MS):
    """The newest FRESH fullscreen frame for this appid, as an absolute path,
    or None. Fresh means the filename's capture epoch is within fresh_ms of
    now: a stale frame from an older suspend must never float behind the
    sheet, so no-frame beats wrong-frame."""
    if not appid:
        return None
    prefix = safe(appid) + '__'
    try:
        names = os.listdir(dirpath)
    except OSError:
        return None
    best_name, best_ms = None, None
    for n in names:
        if not n.startswith(prefix):
            continue
        ms = frame_epoch_ms(n)
        if ms is None:
            continue
        if now_ms - ms > fresh_ms or ms - now_ms > skew_ms:
            continue
        if best_ms is None or ms > best_ms:
            best_name, best_ms = n, ms
    return os.path.join(dirpath, best_name) if best_name else None


def fullres_variant(path):
    """The native-resolution sibling of a wide frame, when pause-snap wrote
    one (<stem>.full.jpg beside <stem>.jpg). The switcher's backdrop covers a
    4K panel and the wide frame is phone-sized (960px), which upscales soft -
    Donnie, 15 Aug 2026: "freeze frame is low res". Freshness was already
    judged on the wide frame; the sibling shares its stamp by construction,
    so this is a name swap, never a second decision."""
    if not path or not path.endswith('.jpg') or path.endswith('.full.jpg'):
        return path
    cand = path[:-len('.jpg')] + '.full.jpg'
    return cand if os.path.exists(cand) else path


def session_appid(rows, fallback=''):
    """The paused session's appid, dug out of the same rows the list is built
    from. Proton games carry it in their window class (steam_app_<appid>);
    failing that, a frame that already landed carries it inside the thumb url
    the server attached (/api/art/game?p=<...>/<appid>__<ms>.jpg). When the
    rows are silent (a shadPS4 row whose capture has not landed yet), the
    caller's fallback - /tmp/game-suspended on this box - answers instead."""
    for w in rows:
        if not w.get('paused'):
            continue
        cls = str(w.get('cls') or '')
        if cls.startswith('steam_app_') and cls[len('steam_app_'):]:
            return cls[len('steam_app_'):]
        appid = _appid_from_thumb(str(w.get('thumb') or ''))
        if appid:
            return appid
    return fallback


def _appid_from_thumb(thumb):
    """<appid> out of /api/art/game?p=<urlencoded path ending appid__ms.jpg>."""
    marker = 'p='
    at = thumb.find(marker)
    if at < 0:
        return ''
    try:
        from urllib.parse import unquote
        frame = unquote(thumb[at + len(marker):].split('&')[0])
    except Exception:  # noqa: BLE001 - a mangled url is just "no answer"
        return ''
    name = os.path.basename(frame)
    if frame_epoch_ms(name) is None:
        return ''
    return name[:name.rfind('__')]

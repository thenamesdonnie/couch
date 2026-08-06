"""Pure logic for HDR auto-routing: which playback to intercept, and the
guards that stop it happening twice.

Importable without Kodi. The impure edges (Player callbacks, HTTP, stopping
playback, notifications) live in service.py, which is what makes
tools/test_autoroute.py runnable on a headless box.

The Jellyfin id extraction is NOT repeated here: service.py puts the
context.couch.playontv addon's directory on sys.path before importing this
module, so `playontv` below is that addon's own pure module. One extraction
chain, two callers.
"""
import json
import re

import playontv

# After a routed playback, ignore anything Kodi starts for this long. This is
# the anti-cascade rule: stopping a playlist item could in principle let Kodi
# advance to the next one, and each advance would otherwise be considered
# fresh. 30s comfortably covers the stop and the handoff's first stages.
QUIET_SECONDS = 30

# And a routed item itself is not reconsidered for this long. The important
# case is the direct loop (something re-triggers the same play), but it also
# gives Donnie an escape hatch: click the same film again inside the cooldown
# and it plays in Kodi, no setting to find.
COOLDOWN_SECONDS = 120


def playable(media_type):
    """Only real library films and episodes are ever intercepted. A container,
    a music video, a plain file, a YouTube item: all left to Kodi."""
    return str(media_type or '').lower() in playontv.PLAYABLE


def target_id(prop, kodi_id, media_type, db_path):
    """What is playing -> the Jellyfin id to ask the server about, or None.

    The media-type gate matters here in a way it does not for the context item:
    that one is filtered by its <visible> condition, this one sees every single
    thing Kodi starts. A jellyfinid property alone would otherwise let a
    trailer or a plugin row through.
    """
    if not playable(media_type):
        return None
    return playontv.resolve_item_id(prop, kodi_id, media_type, db_path)


# Last-resort id source: the file Kodi is actually playing. jellyfin-for-kodi
# runs in addon mode here (useDirectPaths=0), so a library row plays a
# plugin:// url that resolves to a Jellyfin stream url, and both shapes carry
# the item id. DELIBERATELY narrow: a bare "any 32 hex in the url" match would
# happily return an api_key or a device id.
PATH_ID = re.compile(
    r'(?:/Videos/|/Items/|[?&](?:id|item_?id)=)([0-9a-fA-F]{32}|[0-9a-fA-F-]{36})')


def id_from_path(path):
    """A playing file url -> the Jellyfin item id in it, or None."""
    m = PATH_ID.search(str(path or ''))
    return playontv.normalize_item_id(m.group(1)) if m else None


def has_identity(facts):
    """Does this (prop, kodi_id, media_type) triple carry enough to resolve?

    onPlayBackStarted can fire before the player has finished attaching the
    item, so the caller polls until this is true (or gives up).
    """
    if not facts:
        return False
    prop, kodi_id, media_type = facts
    if not media_type:
        return False
    if prop:
        return True
    return str(kodi_id or '').strip() not in ('', '0', '-1', 'None')


def wait_for_facts(get_facts, sleep, attempts=8, interval=0.25):
    """Poll get_facts() until it carries an identity. None if it never does.

    Deliberately short: this whole window is time the user spends watching
    Kodi open a file we are about to stop, so it is capped at ~2s and a miss
    simply means the playback stays in Kodi.
    """
    for i in range(attempts):
        facts = get_facts()
        if has_identity(facts):
            return facts
        if i + 1 < attempts:
            sleep(interval)
    return None


def parse_should_route(code, body):
    """The GET /api/tv/should-route answer -> (route, reason).

    Honest false on absolutely everything unexpected: no server (code None),
    an error code, junk, a body without route:true. The pre-existing behaviour
    (Kodi plays it) is always the safe answer, so there is never a reason to
    guess.
    """
    if code != 200:
        return False, ('couch server is not reachable' if code is None
                       else 'couch server answered %s' % code)
    try:
        data = json.loads(body) if body else {}
    except ValueError:
        return False, 'unreadable answer from the couch server'
    if not isinstance(data, dict):
        return False, 'unreadable answer from the couch server'
    # `is True`, not truthiness: the server always sends a real boolean, so a
    # string or a number in that field means something has gone wrong upstream
    # (a proxy, a rewritten body) and the answer is not to be trusted.
    return data.get('route') is True, str(data.get('reason') or '')


class RouteGuard:
    """The no-loop guard: one interception at a time, a quiet period after a
    routed one, and a per-item cooldown.

    claim() is the only way in. release(routed=False) forgets the item again,
    so a title the server said "no" to behaves completely normally on the next
    click; release(routed=True) keeps the cooldown and starts the quiet period.
    """

    def __init__(self, clock, quiet=QUIET_SECONDS, cooldown=COOLDOWN_SECONDS):
        self._clock = clock
        self._quiet = quiet
        self._cooldown = cooldown
        self._in_flight = None
        self._routed_at = None
        self._recent = {}

    def _prune(self, now):
        for item, at in list(self._recent.items()):
            if now - at >= self._cooldown:
                del self._recent[item]

    def claim(self, item_id):
        """True if this item may be considered now. Records the attempt."""
        now = self._clock()
        self._prune(now)
        if self._in_flight is not None:
            return False
        if self._routed_at is not None and now - self._routed_at < self._quiet:
            return False
        if item_id in self._recent:
            return False
        self._recent[item_id] = now
        self._in_flight = item_id
        return True

    def release(self, item_id, routed):
        if self._in_flight == item_id:
            self._in_flight = None
        if routed:
            self._routed_at = self._clock()
        else:
            self._recent.pop(item_id, None)

    @property
    def busy(self):
        return self._in_flight is not None

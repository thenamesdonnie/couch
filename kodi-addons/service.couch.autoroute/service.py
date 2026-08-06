# -*- coding: utf-8 -*-
"""HDR auto-route service: a plain click on an HDR film plays on the TV.

Donnie's ruling (7 Aug 2026): clicking a movie or episode should play it on
the LG's own Jellyfin app whenever the FILE is HDR or Dolby Vision, because
the PC path tonemaps those down to SDR. SDR keeps playing in Kodi exactly as
before. The "Play on TV (HDR)" context item and the phone button stay as
explicit overrides in both directions.

WHERE THIS INTERCEPTS, AND WHAT IT COSTS
----------------------------------------
This is a service addon holding an xbmc.Player subclass, acting on
onPlayBackStarted. Kodi therefore OPENS the file first: the busy dialog
appears and, on a slow file, a frame or two may show before playback is
stopped and the TV takes over. That flicker is real and it is the price.

The alternatives were investigated and rejected:

* A hook BEFORE Kodi starts. Kodi 20 has no pre-play veto for library items -
  nothing in the python API can answer "do not play this, I will handle it".
  Playlist/Player notifications all fire at or after the same moment as
  onPlayBackStarted.
* The jellyfin addon's own playback path. jellyfin-for-kodi runs in addon mode
  on this box (useDirectPaths=0), so a library row really does route through
  plugin.video.jellyfin before Kodi opens anything, and hooking it would be
  invisible. But that is a third-party addon we do not own: any patch there is
  lost on its next update, which is exactly the recurring-maintenance trap
  this console already has too much of (skin includes, Copacetic views). Not
  worth a saved second of flicker.
* onAVStarted instead. It is strictly LATER (first decoded frame), so it
  flickers more, not less. onPlayBackStarted is the earliest honest hook.

WHAT IT WILL NEVER DO
---------------------
* Fire for anything that is not a library movie or episode.
* Fire when the item does not resolve to a Jellyfin id.
* Fire when the couch server is unreachable, or answers anything other than a
  clean route:true (the server also refuses while a game session is live or
  while it is already handing a playback to the TV).
* Fire twice: one interception at a time, a quiet period afterwards, and a
  per-item cooldown (autoroute.RouteGuard).
* Stop a playback that is no longer the one it decided about: the playing file
  is re-checked immediately before the stop.

KILL SWITCH: this addon's "Auto-route HDR to the TV" setting, or the server
side `touch ~/couch/data/tv-autoroute-off`. Either being off stops it.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import xbmc  # noqa: E402
import xbmcaddon  # noqa: E402
import xbmcgui  # noqa: E402
import xbmcvfs  # noqa: E402

ADDON = xbmcaddon.Addon()
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

# The id extraction lives in the "Play on TV" addon; borrow it rather than
# grow a second copy. Declared as a <requires> import in addon.xml, so Kodi
# refuses to enable this service if that addon is missing.
_SHARED = xbmcvfs.translatePath(
    xbmcaddon.Addon('context.couch.playontv').getAddonInfo('path'))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import playontv  # noqa: E402
import autoroute  # noqa: E402

BASE = 'http://localhost:8790'
HEADING = 'Play on TV'


def log(msg):
    xbmc.log('[couch.autoroute] %s' % msg, xbmc.LOGINFO)


def notify(message, error=False):
    icon = xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO
    xbmcgui.Dialog().notification(HEADING, message, icon, 4500, sound=False)


def enabled():
    """Re-read every time, from a FRESH Addon handle: a long-lived one can hand
    back the value it was built with, and this switch has to take effect on the
    next click with no Kodi restart and no addon reload."""
    try:
        return xbmcaddon.Addon().getSettingBool('enabled')
    except Exception:  # a settings file that predates this setting
        return True


def playing_facts():
    """(jellyfinid property, kodi db id, media type) for what is playing now.

    Three sources, in falling order of trust: the player's own ListItem, the
    VideoPlayer InfoLabels, and finally the id inside the url being played
    (this box plays library rows through plugin.video.jellyfin, so the url
    carries it). Any of them may be empty; the caller polls until they are not.
    """
    prop = kodi_id = media = None
    player = xbmc.Player()
    try:
        li = player.getPlayingItem()
        tag = li.getVideoInfoTag()
        kodi_id = tag.getDbId()
        media = tag.getMediaType()
        prop = li.getProperty('jellyfinid')
    except Exception:
        pass
    if not kodi_id or kodi_id == -1:
        kodi_id = xbmc.getInfoLabel('VideoPlayer.DBID')
    if not media:
        media = xbmc.getInfoLabel('VideoPlayer.DBTYPE')
    if not prop:
        try:
            prop = autoroute.id_from_path(player.getPlayingFile())
        except Exception:
            prop = None
    return prop, kodi_id, media


def should_route(item_id):
    """Ask the server. Short timeout on purpose: every millisecond here is a
    millisecond of Kodi playing something it is about to stop."""
    url = BASE + '/api/tv/should-route?itemId=%s' % item_id
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace')
        except OSError:
            return e.code, ''
    except (urllib.error.URLError, OSError):
        return None, ''


def post_play(item_id):
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
    url = BASE + '/api/tv/play/status?seq=%s' % seq
    try:
        with urllib.request.urlopen(url, timeout=35) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except (urllib.error.URLError, OSError, ValueError):
        return None


class AutoRouter(xbmc.Player):
    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.guard = autoroute.RouteGuard(clock=time.monotonic)

    def onPlayBackStarted(self):
        # Player callbacks run on Kodi's thread: hand off immediately and do
        # every slow thing (polling for the item, HTTP, notifications) on ours.
        threading.Thread(target=self._guarded, daemon=True).start()

    def _guarded(self):
        try:
            self._consider()
        except Exception as e:  # a crash here must never take playback with it
            log('consider failed: %s' % e)

    def _sleep(self, seconds):
        return self.monitor.waitForAbort(seconds)

    def _consider(self):
        if not enabled():
            return
        facts = autoroute.wait_for_facts(playing_facts, self._sleep)
        if not facts:
            return
        prop, kodi_id, media = facts
        db_path = xbmcvfs.translatePath('special://database/jellyfin.db')
        item_id = autoroute.target_id(prop, kodi_id, media, db_path)
        if not item_id:
            return
        if not self.guard.claim(item_id):
            log('%s: not considered (guard)' % item_id)
            return

        routed = False
        try:
            # What we decided about. If Kodi has moved on to something else by
            # the time the answer lands, the decision is void: stopping then
            # would kill a playback nobody asked us about.
            deciding_on = self.getPlayingFile() if self.isPlayingVideo() else None
            if not deciding_on:
                return
            code, body = should_route(item_id)
            route, reason = autoroute.parse_should_route(code, body)
            log('%s: route=%s (%s)' % (item_id, route, reason))
            if not route:
                return
            if not self.isPlayingVideo() or self.getPlayingFile() != deciding_on:
                log('%s: playback moved on, leaving it alone' % item_id)
                return

            self.stop()
            routed = True
            notify('HDR, sending it to the TV')
            code, body = post_play(item_id)
            if code is None:
                notify('Couch server is not reachable', error=True)
                return
            ok, first, err = playontv.parse_start(code, body)
            if not ok:
                notify(err, error=True)
                return
            playontv.follow_stages(first, fetch_status, notify)
        finally:
            self.guard.release(item_id, routed)


def main():
    monitor = xbmc.Monitor()
    player = AutoRouter(monitor)
    log('watching for HDR playbacks')
    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break
    del player


if __name__ == '__main__':
    main()

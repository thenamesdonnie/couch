# The on-TV window switcher, opened by a double-tap of the PS button (see
# pad-home-watcher, which runs this addon over JSON-RPC once it has made sure
# Kodi owns the pad and the screen).
#
# It deliberately holds NO switching logic of its own: it asks the couch
# server for the same window list the phone's switcher shows and posts the
# same activate call back, so "picking Kodi mid-game suspends properly" and
# "picking a paused game resumes it" are decided in one place (server/
# screen.js) rather than drifting between the two remotes.
#
# The server is LAN-only and unauthenticated, and this runs on the same box,
# so localhost with a short timeout is the whole transport story. If it is
# down, say so in a notification and get out of the way - a switcher that
# hangs would freeze the room's only working input.
import json
import urllib.error
import urllib.request

import xbmc
import xbmcgui

API = "http://localhost:8790"
LIST_TIMEOUT = 3      # the server answers in ~100ms; anything slower is broken
ACT_TIMEOUT = 20      # activating suspends a game first, which takes a moment

# Kodi auto-repeats a held joystick button and the watcher can be asked twice
# in a burst, so the same window-property latch tvpoweroff uses keeps a second
# invocation from throwing away the first dialog's focus.
HOME = xbmcgui.Window(10000)
LATCH = "couch.switcher.open"


def get_windows():
    req = urllib.request.Request(API + "/api/windows")
    with urllib.request.urlopen(req, timeout=LIST_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8")).get("windows", [])


def activate(win_id):
    body = json.dumps({"id": win_id}).encode("utf-8")
    req = urllib.request.Request(API + "/api/windows/activate", data=body,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=ACT_TIMEOUT) as r:
        return r.read()


def notify(line):
    xbmcgui.Dialog().notification("Switch to", line, time=4000)


def main():
    try:
        wins = get_windows()
    except (urllib.error.URLError, OSError, ValueError) as e:
        xbmc.log("couch.switcher: window list failed: %s" % e, xbmc.LOGWARNING)
        notify("The couch server is not answering")
        return

    # Kodi is what the dialog is drawn on, so offering to switch to it would
    # be a no-op row. Everything else the server lists - games (titled
    # "... paused" while frozen, exactly as the phone shows them), Big
    # Picture, and the Desktop pseudo-entry - is a real destination.
    rows = [w for w in wins if not w.get("kodi")]
    if not rows:
        notify("Nothing else is running")
        return

    labels = [str(w.get("title") or w.get("id")) for w in rows] + ["Cancel"]
    choice = xbmcgui.Dialog().select("Switch to", labels)
    if choice < 0 or choice >= len(rows):
        xbmc.log("couch.switcher: cancelled", xbmc.LOGINFO)
        return

    target = rows[choice]
    xbmc.log("couch.switcher: activating %s (%s)"
             % (target.get("id"), target.get("title")), xbmc.LOGINFO)
    try:
        activate(str(target.get("id")))
    except (urllib.error.URLError, OSError, ValueError) as e:
        xbmc.log("couch.switcher: activate failed: %s" % e, xbmc.LOGWARNING)
        notify("Could not switch: %s" % e)


if HOME.getProperty(LATCH) == "1":
    xbmc.log("couch.switcher: already open, ignoring re-trigger", xbmc.LOGINFO)
else:
    HOME.setProperty(LATCH, "1")
    try:
        main()
    finally:
        HOME.clearProperty(LATCH)

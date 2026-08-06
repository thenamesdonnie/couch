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
#
# WINDOW ID, read this before debugging a "missed" show_switcher verdict: as
# of v1.2.0 the list is drawn in the addon's OWN animated window, so the
# dialog on screen is a python window (Kodi hands those 13000-13099), not the
# select dialog (12000) this used to open. couchd's _eff_show_switcher and
# tools/gesture-sweep's DISMISS_WINDOWS both name 12000 and must learn the
# range. Configure > Advanced > "Animated switcher dialog" turns the new
# window off and puts 12000 back without a redeploy.
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import xbmc
import xbmcaddon
import xbmcgui

# Kodi runs this file by path and does not promise the addon dir is on
# sys.path, so put it there before importing our own module. And because this
# addon is the room's only route back out of a frozen game, a missing or
# broken pausedframe.py (a half-copied deploy) costs the backdrop, never the
# switcher.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import pausedframe  # noqa: E402 - needs the sys.path line above
except Exception as _e:  # noqa: BLE001
    xbmc.log("couch.switcher: pausedframe helper unavailable (%s), "
             "freeze-frame backdrop off" % _e, xbmc.LOGWARNING)

    class pausedframe:  # noqa: N801 - stands in for the module
        @staticmethod
        def newest_frame(*_a, **_k):
            return None

        @staticmethod
        def session_appid(_rows, fallback=""):
            return ""

API = "http://localhost:8790"
LIST_TIMEOUT = 3      # the server answers in ~100ms; anything slower is broken
ACT_TIMEOUT = 20      # activating suspends a game first, which takes a moment

HEADING = "Switch to"

# Kodi auto-repeats a held joystick button and the watcher can be asked twice
# in a burst, so the same window-property latch tvpoweroff uses keeps a second
# invocation from throwing away the first dialog's focus.
HOME = xbmcgui.Window(10000)
LATCH = "couch.switcher.open"

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo("path")

# resources/skins/Default/1080i/script-couch-switcher.xml, drawn by
# SwitcherDialog below. The res folder name and the argument must agree.
DIALOG_XML = "script-couch-switcher.xml"
DIALOG_SKIN = "Default"
DIALOG_RES = "1080i"
# The one control id this file and the XML share. NOT 2, 3, 4, 12 or 50-59:
# WindowXML claims those (view/sort buttons and the media container) and
# swallows their clicks before python's onClick ever runs - the list was id 3
# once and every select press died as "WindowXML: Internal sort button not
# implemented" in the log.
LIST_ID = 9000

# The freeze-frame backdrop. pause-snap drops the paused game's last rendered
# frame in PAUSED_DIR at suspend time; the XML's bottom-most image control is
# bound to PROP_FRAME on THIS window and stays hidden while it is empty, so
# "no frame" is pixel-identical to the dialog before this feature existed.
# The capture can land a beat AFTER the dialog opens (freeze -> snapshot ->
# show kodi -> dialog is the flow, and the snapshot usually finishes within a
# second of the freeze), hence the short background poll rather than a single
# look at open.
PAUSED_DIR = os.path.expanduser("~/couch/data/paused")
PROP_FRAME = "couch.pausedframe"
FRAME_POLL_S = 0.2          # one directory listing every 200ms...
FRAME_POLL_FOR_S = 3.0      # ...for at most 3s, then the backdrop stays dim

ACTION_PREVIOUS_MENU = 10   # Esc / pad B, on skins that map it
ACTION_NAV_BACK = 92        # what Input.Back and the pad's B send


class SwitcherDialog(xbmcgui.WindowXMLDialog):
    """The switcher list, in a window the addon owns so it can animate.

    Why not the stock select dialog: the entrance is the point. DialogSelect
    belongs to the skin, an addon cannot animate a skin's window without
    editing the skin, and skin edits on this box do not survive skin updates.
    A WindowXMLDialog is the only way an addon gets <animation> of its own.

    What it deliberately does NOT change is the answer it gives back. `choice`
    carries exactly what xbmcgui.Dialog().select() returned: the index of the
    picked row, len(rows) for the trailing Cancel entry, and -1 for a
    dismissal. main() below is untouched by the swap.

    THE ONE THING THAT DOES CHANGE is the window id. Kodi hands python windows
    an id out of the 13000-13099 pool; a select dialog is 12000. Anything that
    identifies this dialog by window id has to learn the new range - see the
    note on animated_dialog() and the addon's news entry.
    """
    rows = ()
    choice = -1
    appid = ""              # the paused session's appid; "" = no live session
    _filled = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set once, ever: tells the frame poll the dialog is done with it.
        self._frame_stop = threading.Event()

    def onInit(self):
        # Kodi can re-init a window (a skin reload, a resolution change); the
        # list is built once so a re-init cannot duplicate the rows. But every
        # init opens with nothing focused (WINDOW_INIT's default-focus attempt
        # runs before this callback, against a then-empty list), so focus is
        # re-asserted on every init, not just the filling one - a bare early
        # return here would leave a re-inited window deaf to the pad.
        if self._filled:
            self.setFocusId(LIST_ID)
            return
        self._filled = True
        self._start_frame_watch()
        try:
            items = []
            for w in self.rows:
                li = xbmcgui.ListItem(label=str(w.get("title") or w.get("id")))
                # The freeze-frame the server already attaches to a paused
                # game (screen.js -> /api/art/game). Same picture the phone
                # switcher shows; absent on everything else, and the layout
                # hides the slot when it is.
                thumb = w.get("thumb")
                if thumb:
                    li.setArt({"thumb": API + thumb, "icon": API + thumb})
                items.append(li)
            items.append(xbmcgui.ListItem(label="Cancel"))
            lst = self.getControl(LIST_ID)
            lst.reset()
            lst.addItems(items)
            lst.selectItem(0)
            self.setFocusId(LIST_ID)
        except Exception as e:   # noqa: BLE001 - see below
            # A window that drew wrong must not strand the room in a modal it
            # cannot read. Close immediately (choice stays -1, i.e. cancel)
            # and leave the reason in the log.
            xbmc.log("couch.switcher: dialog init failed: %s" % e,
                     xbmc.LOGERROR)
            self.close()

    def onClick(self, controlId):
        if controlId == LIST_ID:
            self.choice = self.getControl(LIST_ID).getSelectedPosition()
            self.close()

    def onAction(self, action):
        # Kodi runs the base window's OnAction before this, so navigation and
        # the built-in back handling already happened; this only makes the
        # cancel answer explicit rather than relying on the default.
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.choice = -1
            self.close()

    def close(self):
        # Every exit funnels through here (row picked, backed out, init
        # failure), so this is the one place the frame poll gets told to stop.
        self._frame_stop.set()
        super().close()

    # -- the freeze-frame backdrop -------------------------------------------

    def _start_frame_watch(self):
        """Put the paused game's freeze-frame behind the sheet.

        The capture can trail the dialog by a beat (pause-snap is still
        writing while show-kodi and this window race it), so one look at open
        is not enough: check now, and if the frame is not there yet, watch for
        it from a small daemon thread - a 200ms wait on an Event, not a spin,
        and never on the UI thread - for up to 3s, stopping the moment the
        frame lands or the dialog closes. If nothing ever lands the property
        stays empty and the dialog looks exactly as it always has.
        """
        if not self.appid:
            return              # no live game session - nothing to show
        if self._set_frame_if_ready():
            return
        threading.Thread(target=self._frame_poll, daemon=True,
                         name="couch-switcher-frame").start()

    def _frame_poll(self):
        deadline = time.monotonic() + FRAME_POLL_FOR_S
        while not self._frame_stop.wait(FRAME_POLL_S):
            if self._set_frame_if_ready() or time.monotonic() >= deadline:
                return

    def _set_frame_if_ready(self):
        try:
            frame = pausedframe.newest_frame(PAUSED_DIR, self.appid,
                                             int(time.time() * 1000))
            if not frame:
                return False
            self.setProperty(PROP_FRAME, frame)
            return True
        except Exception as e:  # noqa: BLE001 - decoration must never cost the dialog
            xbmc.log("couch.switcher: freeze-frame lookup failed: %s" % e,
                     xbmc.LOGWARNING)
            return True         # do not keep retrying a broken path


def animated_dialog():
    """The rollback switch (Configure > Advanced).

    Off puts the stock select dialog back verbatim - no animation, and window
    12000 again. That matters because couchd verifies this gesture landed by
    watching the current window id, so "turn the new window off" has to be one
    setting rather than a redeploy.
    """
    try:
        return ADDON.getSettingBool("ui.animated_dialog")
    except Exception:  # noqa: BLE001 - a settings read must never cost the gesture
        return True


def select_window(rows):
    """Ask the room where to go. Returns select()'s contract: a row index,
    len(rows) for Cancel, -1 for dismissed."""
    labels = [str(w.get("title") or w.get("id")) for w in rows] + ["Cancel"]
    if not animated_dialog():
        return xbmcgui.Dialog().select(HEADING, labels)
    try:
        dlg = SwitcherDialog(DIALOG_XML, ADDON_PATH, DIALOG_SKIN, DIALOG_RES)
    except Exception as e:  # noqa: BLE001 - missing/unreadable window XML
        # The switcher is the flagship gesture and the only route back out of
        # a game from the couch: a missing texture or a bad XML path costs the
        # animation, never the switcher.
        xbmc.log("couch.switcher: custom dialog unavailable (%s), using the "
                 "stock select dialog" % e, xbmc.LOGWARNING)
        return xbmcgui.Dialog().select(HEADING, labels)
    try:
        dlg.rows = rows
        dlg.appid = pausedframe.session_appid(rows, fallback=_suspended_appid())
        dlg.doModal()
        return dlg.choice
    finally:
        dlg._frame_stop.set()   # doModal can raise; the poll must still die
        del dlg


def _suspended_appid():
    """The control daemon's own record of what it froze - the same file the
    couch server reads. Only consulted when the rows carry no appid (a shadPS4
    session whose capture has not landed yet); absent file means no session,
    which correctly leaves the backdrop off."""
    try:
        with open("/tmp/game-suspended", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


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

    choice = select_window(rows)
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

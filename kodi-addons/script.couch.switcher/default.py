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
import urllib.error
import urllib.request

import xbmc
import xbmcaddon
import xbmcgui

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
LIST_ID = 3                 # the one control id this file and the XML share

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
    _filled = False

    def onInit(self):
        # Kodi can re-init a window (a skin reload, a resolution change); the
        # list is built once so a re-init cannot duplicate the rows.
        if self._filled:
            return
        self._filled = True
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
        dlg.doModal()
        return dlg.choice
    finally:
        del dlg


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

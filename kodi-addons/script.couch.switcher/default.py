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
import re
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

# Same rule for the sandbox crossing (docs/kodi21-flatpak-migration.md): a
# missing couchhost.py costs the paused backdrop on the Flatpak, never the
# switcher, and on the apt build the fallback IS the old code.
try:
    from couchhost import host_read  # noqa: E402 - needs the sys.path line
except Exception as _e:  # noqa: BLE001
    xbmc.log("couch.switcher: couchhost unavailable (%s), reading host "
             "paths directly" % _e, xbmc.LOGWARNING)

    def host_read(path, timeout=3.0):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return None

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

# The power bar above the switch row. Text rather than symbols (Donnie's call,
# 8 Aug): the three actions differ only in WHICH things get turned off, and a
# 44px glyph cannot carry "controller" against "controller and TV" without
# ambiguity. Each entry names an action that script.tvpoweroff already
# implements - the switcher holds no power logic of its own, exactly as it
# holds no switching logic of its own, so "quit the game politely first" has
# one home and cannot drift between the two menus.
POWER_ID = 9010
POWER_ADDON = "script.tvpoweroff"
POWER_ACTIONS = [("Quit game", "quit"),
                 ("Controller off", "pad_off"),
                 ("Controller + TV off", "all_off")]

# The Spotify bar, sharing the power strip's row on its right half. Drawn
# only while the couch server says a phone session is live on the spotifyd
# receiver (GET /api/spotify -> {active:true}); the XML gates the whole
# section on PROP_SPOTIFY so an idle receiver leaves the sheet exactly as it
# was before this feature existed. Unlike every other pick in this dialog a
# media action does NOT close it: skipping is a repeat-press activity, so the
# click fires the command, redraws Play/Pause and the now-playing label from
# the server's answer, and stays open until B backs out.
MEDIA_ID = 9020
PROP_SPOTIFY = "couch.spotify"
PROP_SPOTIFY_LABEL = "couch.spotify.label"
MEDIA_TIMEOUT = 2     # status is ~3 local busctl calls behind the server

# The pills draw icons, not words (Donnie's call, 15 Aug - the opposite of
# the power bar's rule, and rightly: pause/previous/next ARE the three
# glyphs every remote on earth taught). Play/pause sits FIRST so walking
# right off the power bar lands on the button that matters. The icon rides
# each ListItem as an absolute path property: relative texture lookup for
# $INFO textures is not worth trusting across Kodi versions, an absolute
# path cannot miss. Labels are still set ("Pause"/"Play"/...) - the toggle
# logic and the XML's no-icon fallback both read them.
MEDIA_ART = os.path.join(ADDON_PATH, "resources", "skins", "Default", "media")

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
ACTION_MOVE_LEFT = 1        # the four navigation actions, for the strip
ACTION_MOVE_RIGHT = 2       # seam below - Kodi's ids, not ours
ACTION_MOVE_UP = 3
ACTION_MOVE_DOWN = 4


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
    power = ""              # a POWER_ACTIONS key when the bar was used
    spotify = None          # /api/spotify answer, fetched before doModal
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
                li = xbmcgui.ListItem(
                    label=pretty_title(str(w.get("title") or w.get("id"))))
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

            # The power bar. Filled here and not by the XML so the labels live
            # beside the actions they fire.
            try:
                bar = self.getControl(POWER_ID)
                bar.reset()
                bar.addItems([xbmcgui.ListItem(label=lbl)
                              for lbl, _ in POWER_ACTIONS])
                bar.selectItem(0)
            except Exception as e:  # noqa: BLE001
                # No bar is a switcher without power options; a switcher that
                # failed to open is the room stuck in a game. Never trade the
                # second for the first.
                xbmc.log("couch.switcher: power bar unavailable (%s)" % e,
                         xbmc.LOGWARNING)

            # The Spotify bar. Same rule as the power bar: its absence is a
            # poorer sheet, never a missing switcher.
            try:
                self._fill_media()
            except Exception as e:  # noqa: BLE001
                xbmc.log("couch.switcher: spotify bar unavailable (%s)" % e,
                         xbmc.LOGWARNING)

            # Focus the SWITCH row, never the power bar: the stick must not
            # start on anything that turns the television off.
            self._strip_focus = LIST_ID
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
        elif controlId == POWER_ID:
            idx = self.getControl(POWER_ID).getSelectedPosition()
            if 0 <= idx < len(POWER_ACTIONS):
                self.power = POWER_ACTIONS[idx][1]
            self.close()
        elif controlId == MEDIA_ID:
            self._media_click(self.getControl(MEDIA_ID).getSelectedPosition())

    def onAction(self, action):
        # Kodi runs the base window's OnAction before this, so navigation
        # and the built-in back handling already happened; by the time we
        # see a move action the focus has already landed.
        aid = action.getId()
        if aid in (ACTION_MOVE_LEFT, ACTION_MOVE_RIGHT,
                   ACTION_MOVE_UP, ACTION_MOVE_DOWN):
            self._join_strip(aid)
        elif aid in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.choice = -1
            self.close()

    def _join_strip(self, aid):
        """Make the power bar and the Spotify bar feel like ONE strip.

        They are two lists, and a Kodi list remembers its own selected item
        - so walking right off the power bar used to teleport to wherever
        the Spotify bar last was ("it will jump if it was on pause before",
        Donnie, 15 Aug). The XML cannot fix it (onleft/onright name a
        control, not a position), so it is repaired here the moment a
        LEFT/RIGHT lands focus on the other bar: entering rightwards starts
        at its first pill, entering leftwards (the wrap around the screen
        edge) at its last. UP/DOWN only refresh the bookkeeping - a
        vertical entry into a bar keeping its old spot is fine.
        """
        try:
            now = self.getFocusId()
        except Exception:  # noqa: BLE001 - bookkeeping must never cost input
            return
        prev, self._strip_focus = getattr(self, "_strip_focus", None), now
        if (aid not in (ACTION_MOVE_LEFT, ACTION_MOVE_RIGHT)
                or now == prev
                or now not in (POWER_ID, MEDIA_ID)
                or prev not in (POWER_ID, MEDIA_ID)):
            return
        try:
            bar = self.getControl(now)
            bar.selectItem(0 if aid == ACTION_MOVE_RIGHT else bar.size() - 1)
        except Exception as e:  # noqa: BLE001
            xbmc.log("couch.switcher: strip seam skipped: %s" % e,
                     xbmc.LOGWARNING)

    def close(self):
        # Every exit funnels through here (row picked, backed out, init
        # failure), so this is the one place the frame poll gets told to stop.
        self._frame_stop.set()
        super().close()

    # -- the Spotify bar -----------------------------------------------------

    @staticmethod
    def _media_item(label, icon):
        li = xbmcgui.ListItem(label=label)
        li.setProperty("icon", os.path.join(MEDIA_ART, icon))
        return li

    def _fill_media(self):
        st = self.spotify or {}
        if not st.get("active"):
            return              # no phone session - the XML keeps it hidden
        bar = self.getControl(MEDIA_ID)
        bar.reset()
        playing = bool(st.get("playing"))
        bar.addItems([
            self._media_item("Pause" if playing else "Play",
                             "icon-pause.png" if playing else "icon-play.png"),
            self._media_item("Previous", "icon-prev.png"),
            self._media_item("Next", "icon-next.png"),
        ])
        bar.selectItem(0)       # play/pause leads - it is the point
        self._set_media_label(st)
        self.setProperty(PROP_SPOTIFY, "1")

    def _set_media_label(self, st):
        # Sits beside the amber dot as the media cluster's eyebrow line, so
        # it is just the music: "Track - Artist", or the service name when
        # spotifyd has a session but nothing loaded yet.
        now = " - ".join(x for x in (st.get("track"), st.get("artist")) if x)
        self.setProperty(PROP_SPOTIFY_LABEL, now if now else "Spotify")

    def _media_click(self, idx):
        if not 0 <= idx < 3:
            return
        pausing = False
        if idx == 0:
            # An explicit verb chosen by the pill's CURRENT label, never
            # MPRIS PlayPause: the toggle races its own read-back (verified
            # live 15 Aug - two quick PlayPauses left the player paused,
            # because spotifyd's reported state lags the command it just
            # took). Play/Pause are idempotent, and they let the pill be
            # redrawn from intent below instead of from that stale read.
            bar = self.getControl(MEDIA_ID)
            pausing = bar.getListItem(0).getLabel() == "Pause"
            cmd = "pause" if pausing else "play"
        else:
            cmd = "previous" if idx == 1 else "next"
        # Inline, not a thread: the round trip is ~300ms (the server re-reads
        # status after firing the command) and a click that answers with its
        # own redraw is worth a beat of held frame.
        try:
            st = spotify_command(cmd)
        except Exception as e:  # noqa: BLE001
            xbmc.log("couch.switcher: spotify %s failed: %s"
                     % (cmd, e), xbmc.LOGWARNING)
            return
        try:
            if not st.get("active"):
                # The phone walked away mid-press. Park focus somewhere real
                # BEFORE hiding the bar, or the pad would be steering a
                # control that no longer draws.
                self.setFocusId(LIST_ID)
                self.clearProperty(PROP_SPOTIFY)
                return
            if idx == 0:
                item = self.getControl(MEDIA_ID).getListItem(0)
                item.setLabel("Play" if pausing else "Pause")
                item.setProperty("icon", os.path.join(
                    MEDIA_ART,
                    "icon-play.png" if pausing else "icon-pause.png"))
            # A skip leaves play/pause as it was; only the track line moves.
            self._set_media_label(st)
        except Exception as e:  # noqa: BLE001
            xbmc.log("couch.switcher: spotify redraw failed: %s" % e,
                     xbmc.LOGWARNING)

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
            self.setProperty(PROP_FRAME, pausedframe.fullres_variant(frame))
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
    labels = [pretty_title(str(w.get("title") or w.get("id")))
              for w in rows] + ["Cancel"]
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
        dlg.spotify = _spotify_status()
        dlg.doModal()
        if dlg.power:
            # A power action was picked, so there is no window to switch to.
            # Sentinel rather than an index: the caller must not be able to
            # confuse "turn the TV off" with "row 2".
            return ("power", dlg.power)
        return dlg.choice
    finally:
        dlg._frame_stop.set()   # doModal can raise; the poll must still die
        del dlg


def _suspended_appid():
    """The control daemon's own record of what it froze - the same file the
    couch server reads. Only consulted when the rows carry no appid (a shadPS4
    session whose capture has not landed yet); absent file means no session,
    which correctly leaves the backdrop off."""
    # /tmp is a private tmpfs inside the Kodi 21 Flatpak, so this goes
    # through couchhost - a plain open() there would read an empty sandbox
    # and drop the backdrop on every shadPS4 pause.
    return (host_read("/tmp/game-suspended") or "").strip()


def pretty_title(title):
    """A card title, not a window title.

    shadPS4 names its window "shadPS4 v0.17.0 | CUSA00900 - Bloodborne
    <01.09> · paused" and that engineering string was on the deck in 36px
    SemiBold. Strip the emulator preamble and the version tag, keep
    whatever trails it (the " · paused" marker matters). Anything that
    does not match the pattern passes through untouched - Steam windows,
    Big Picture and Desktop already carry human names."""
    m = re.match(r"^shadPS4\b[^|]*\|\s*[A-Z]+\d+\s*-\s*(.*)$", title)
    if not m:
        return title
    return re.sub(r"\s*<[^>]*>", "", m.group(1)).strip()


def _spotify_status():
    """What the spotifyd receiver is doing, or {} - never an exception.

    {} and {"active": False} both leave the bar hidden, so a slow or absent
    endpoint (an older server without /api/spotify, say) degrades to the
    sheet as it was before the bar existed."""
    try:
        req = urllib.request.Request(API + "/api/spotify")
        with urllib.request.urlopen(req, timeout=MEDIA_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - decoration must never cost the dialog
        xbmc.log("couch.switcher: spotify status failed: %s" % e,
                 xbmc.LOGWARNING)
        return {}


def spotify_command(cmd):
    """Fire a transport command; returns the server's fresh status so the
    bar can redraw itself from the answer."""
    req = urllib.request.Request(API + "/api/spotify/" + cmd, data=b"{}",
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


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
    if isinstance(choice, tuple) and choice[0] == "power":
        action = choice[1]
        xbmc.log("couch.switcher: power action %r -> %s"
                 % (action, POWER_ADDON), xbmc.LOGINFO)
        # Over JSON-RPC, not executebuiltin: a builtin issued while this
        # dialog is still tearing down is dispatched against a GUI that is
        # mid-teardown and is silently lost (observed 8 Aug with
        # ActivateWindow - the log line printed and nothing happened).
        xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "Addons.ExecuteAddon",
            "params": {"addonid": POWER_ADDON, "params": [action]},
        }))
        return
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

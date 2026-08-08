# Shown by holding the PS button (see userdata/keymaps/gamepad-poweroff.xml).
# The console's quick menu: quit the game you are in, turn off the TV and
# controller together, or just the controller.
# There is no way to truly power a DualSense off from the host over Bluetooth,
# so the pad is disconnected instead; it blinks briefly, then sleeps on its own
# idle timeout. The PC itself stays on; the server keeps running behind a dark
# screen.
#
# The entries are built as a list of (label, action) pairs rather than a fixed
# menu read back by index, because the first entry is conditional: "Quit <game>"
# only exists while a game session does. Comparing a returned index against
# hard-coded 0/1/2 would silently shift every action along by one the moment
# that entry appears, which is exactly the bug this shape makes impossible.
import os
import re
import struct
import time

import xbmc
import xbmcgui

# Under the Kodi 21 Flatpak `tv`, `game-launch` and `bluetoothctl` are all
# outside the sandbox, and so are the /tmp session flags this menu reads to
# decide whether there is a game to quit. couchhost is the crossing; on the
# apt build every call through it is a plain passthrough.
# See docs/kodi21-flatpak-migration.md.
from couchhost import host_popen, host_read

MAC = "AA:BB:CC:DD:EE:FF"
TV = "/home/ds2000/.local/bin/tv"
GAME_LAUNCH = "/home/ds2000/.local/bin/game-launch"
# Movie night: cinema-watch plays trailers before library films while this
# flag exists. It lives here because this menu is the console's quick menu.
MOVIE_NIGHT = "/home/ds2000/.local/state/movie-night"

# game-launch's session flags, read exactly as server/sys.js gameSession()
# reads them: "<launcher pid> <mode> [<appid>]", and a separate flag file that
# exists only while the game is frozen. Either one means there is a game to
# quit - a suspended game is still a game.
SESSION = "/tmp/game-session"
SUSPENDED = "/tmp/game-suspended"
STEAMAPPS = os.path.expanduser("~/.steam/steam/steamapps")
# Naming the game is a nicety, not a feature: the menu is the room's only way
# out of a stuck game, so the whole lookup runs under a wall-clock budget and
# every failure falls back to the generic label rather than delaying the
# dialog by even a visible frame.
NAME_BUDGET = 0.30


def _read(path):
    # Reading the flags wrong is not a cosmetic failure here: a menu that
    # cannot see the session offers "turn off the TV" with no "quit game"
    # above it, mid-game.
    return (host_read(path) or "").strip()


def session_appid():
    """What game-launch says is running, or None.

    Mirrors server/sys.js: field 3 when the mode carries an id (steam 570,
    shadps4 /path/eboot.bin), otherwise the mode itself (bigpicture, shadps4).
    """
    parts = _read(SESSION).split()
    if not parts:
        # A suspended flag with no session is stale; the watcher repairs it,
        # and offering to quit nothing would be worse than offering nothing.
        return None
    if len(parts) > 2:
        return parts[2]
    return parts[1] if len(parts) > 1 else "game"


def _library_dirs():
    """Every steamapps directory Steam knows about, primary first."""
    dirs = [STEAMAPPS]
    txt = _read(os.path.join(STEAMAPPS, "libraryfolders.vdf"))
    for path in re.findall(r'"path"\s+"([^"]*)"', txt):
        candidate = os.path.join(path, "steamapps")
        if candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _steam_name(appid, deadline):
    """The 'name' field of appmanifest_<appid>.acf - the same string the Games
    row and the phone's library label the tile with."""
    for d in _library_dirs():
        if time.monotonic() > deadline:
            return ""
        txt = _read(os.path.join(d, "appmanifest_%s.acf" % appid))
        m = re.search(r'"name"\s+"([^"]*)"', txt)
        if m:
            return m.group(1)
    return ""


def _sfo_title(path):
    """TITLE out of a PS4 dump's sce_sys/param.sfo (see games.py's _sfo)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return ""
    if data[:4] != b"\x00PSF":
        return ""
    try:
        key_start, data_start, count = struct.unpack_from("<III", data, 8)
        for i in range(count):
            koff, fmt, length, _max, doff = struct.unpack_from("<HHIII", data, 20 + i * 16)
            ks = key_start + koff
            if data[ks:data.index(b"\x00", ks)] != b"TITLE":
                continue
            raw = data[data_start + doff:data_start + doff + length]
            return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
    except Exception:
        return ""
    return ""


def game_name(appid, budget=NAME_BUDGET):
    """Best-effort title for a session id. "" means 'call it a game'."""
    deadline = time.monotonic() + budget
    try:
        if not appid:
            return ""
        if appid == "bigpicture":
            return "Big Picture"
        if appid == "shadps4":
            return "shadPS4"
        if appid.isdigit():
            return _steam_name(appid, deadline)
        if os.path.isabs(appid):
            # A shadPS4 eboot path: the dump's own metadata, else its folder.
            gdir = os.path.dirname(appid)
            if time.monotonic() <= deadline:
                title = _sfo_title(os.path.join(gdir, "sce_sys", "param.sfo"))
                if title:
                    return title
            return os.path.basename(gdir)
    except Exception as e:  # a label must never be able to break the menu
        xbmc.log("tvpoweroff: name lookup failed: %s" % e, xbmc.LOGWARNING)
    return ""


def _spawn(argv):
    # start_new_session so these outlive this short-lived script process.
    host_popen(argv, start_new_session=True)


def quit_game():
    """Leave the game, stay exactly where we are: Kodi stays up, the TV stays
    on and the pad stays connected. game-launch closes the game politely, so
    games that save on quit save."""
    _spawn([GAME_LAUNCH, "quit"])
    xbmc.log("tvpoweroff: fired game quit only", xbmc.LOGINFO)


def all_off():
    # Any running or paused game gets a polite close first, so games that save
    # on quit save; the TV doesn't need to stay on for that.
    _spawn([GAME_LAUNCH, "quit"])
    _spawn([TV, "off"])
    _spawn(["/usr/bin/bluetoothctl", "disconnect", MAC])
    xbmc.log("tvpoweroff: fired game quit, 'tv off' and pad disconnect", xbmc.LOGINFO)


def pad_off():
    _spawn(["/usr/bin/bluetoothctl", "disconnect", MAC])
    xbmc.log("tvpoweroff: pad disconnect only", xbmc.LOGINFO)


def toggle_movie_night():
    if os.path.exists(MOVIE_NIGHT):
        os.remove(MOVIE_NIGHT)
        xbmcgui.Dialog().notification("Movie night", "Trailers off", time=4000)
        xbmc.log("tvpoweroff: movie night off", xbmc.LOGINFO)
    else:
        with open(MOVIE_NIGHT, "w") as f:
            f.write("2")
        xbmcgui.Dialog().notification(
            "Movie night", "Two trailers before each film", time=4000)
        xbmc.log("tvpoweroff: movie night on", xbmc.LOGINFO)


def build_options():
    """The menu, in order: (label, action). action None means 'do nothing'."""
    options = []
    appid = session_appid()
    if appid:
        name = game_name(appid)
        options.append(("Quit %s" % name if name else "Quit game", quit_game))
    options.append(("Turn off TV and controller", all_off))
    options.append(("Turn off controller only", pad_off))
    options.append(("Movie night trailers: %s"
                    % ("on" if os.path.exists(MOVIE_NIGHT) else "off"),
                    toggle_movie_night))
    options.append(("Cancel", None))
    return options


def main():
    options = build_options()
    try:
        choice = xbmcgui.Dialog().contextmenu([label for label, _ in options])
    finally:
        HOME.clearProperty(LATCH)
    if 0 <= choice < len(options) and options[choice][1] is not None:
        options[choice][1]()
    else:
        xbmc.log("tvpoweroff: cancelled", xbmc.LOGINFO)


# Kodi auto-repeats a held joystick button, so the keymap's holdtime action can
# fire again while the menu is already up. Each re-fire used to open a fresh
# dialog and throw away the focus, which looked like the button unselecting
# itself. A window-property latch makes every extra invocation exit quietly.
HOME = xbmcgui.Window(10000)
LATCH = "tvpoweroff.open"

if HOME.getProperty(LATCH) == "1":
    xbmc.log("tvpoweroff: already open, ignoring re-trigger", xbmc.LOGINFO)
else:
    HOME.setProperty(LATCH, "1")
    # The latch is cleared as soon as the dialog closes (inside main), so a
    # slow action - game-launch quit is a spawn, but be strict anyway - can
    # never leave the menu unopenable.
    try:
        main()
    finally:
        HOME.clearProperty(LATCH)

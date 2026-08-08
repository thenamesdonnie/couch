# Local addition for the living-room console build. NOT part of the upstream
# script.copacetic.helper - re-apply after any addon update.
#
# The home screen's Games row: every installed Steam game, read straight from
# Steam's own install manifests on each load, so the row updates itself as
# games are installed and removed. Selecting one hands off to
# ~/.local/bin/game-launch, which moves the controller between Kodi and the
# game and puts the right thing on screen.
#
# It also lists PS4 games emulated with shadPS4: any decrypted dump dropped
# under ~/Games/ps4 shows up as its own tile, named and cover-arted from the
# dump's own metadata, and a "shadPS4" tile opens the emulator's library. Both
# launch through the same game-launch handoff as Steam.
import glob
import json
import os
import re
import struct
import subprocess
import sys
import urllib.parse

import xbmcgui
import xbmcplugin

# Everything this file spawns - game-launch and the three ~/couch/tools
# fetchers - is a host program, and under the Kodi 21 Flatpak the sandbox has
# neither them nor the host python3 they run under. couchhost carries the
# argv out through flatpak-spawn there and changes nothing on the apt build.
# It is vendored beside this file because an addon that imports from ~/couch
# breaks the day ~/couch moves; the copies are pinned byte-identical by
# tools/test_couchhost.py. See docs/kodi21-flatpak-migration.md.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from couchhost import host_popen, host_read
except Exception:                                            # noqa: BLE001
    # The Games row is the console's front door. A missing helper costs the
    # sandbox crossing, never the row.
    host_popen = subprocess.Popen

    def host_read(path, timeout=3.0):
        try:
            with open(path, encoding='utf-8', errors='replace') as handle:
                return handle.read()
        except OSError:
            return None

STEAMAPPS = os.path.expanduser('~/.steam/steam/steamapps')
LIBCACHE = os.path.expanduser('~/.steam/debian-installation/appcache/librarycache')
STEAM_ICON = os.path.expanduser('~/.steam/debian-installation/deb-installer/steam-launcher/icons/256/steam.png')
LAUNCHER = os.path.expanduser('~/.local/bin/game-launch')

# PS4 emulation: the emulator itself, and the folder where decrypted game dumps
# live (each dump is its own subfolder with an eboot.bin and an sce_sys/).
SHADPS4_APP = os.path.expanduser('~/.local/share/shadps4/Shadps4-sdl.AppImage')
PS4_DIR = os.path.expanduser('~/games/ps4')
GAMEPAD_ICON = 'special://skin/media/icons/icon_gamepad_home.png'
# Portrait (2:3) logo tiles so the app entries fill the poster grid like games
# instead of a square logo getting zoom-cropped.
STEAM_TILE = os.path.expanduser('~/.local/share/game-tiles/steam.png')
SHADPS4_TILE = os.path.expanduser('~/.local/share/game-tiles/shadps4.png')
# Square variants for the home row: portrait art centre-cropped to a square
# loses the skin's rounding mask along with the crop, so square thumbs only.
STEAM_TILE_SQ = os.path.expanduser('~/.local/share/game-tiles/steam-sq.png')
SHADPS4_TILE_SQ = os.path.expanduser('~/.local/share/game-tiles/shadps4-sq.png')

# Freeze-frames of paused games, written at suspend time by
# ~/.local/bin/pause-snap: the last frame the game rendered before it was
# frozen, so its tile shows where the player left off rather than the same
# capsule as every other game on the row. Filenames carry the capture time
# because Kodi re-checks a cached local texture's hash only about once a day -
# a stable name would leave the row showing the frame from the LAST time this
# game was paused. Missing directory, missing frame and stale frame all fall
# straight back to Steam's art, which is what an unpaused game shows anyway.
PAUSED_DIR = os.path.expanduser('~/couch/data/paused')

# Steam's own plumbing installs like a game; nobody wants a tile for a runtime.
PLUMBING = re.compile(r'proton|steam linux runtime|steamworks common', re.I)

# Composed square tiles for the Stagelight home row: Steam's capsule art puts
# the title text wherever it likes, so a square centre-crop regularly beheads
# the logo. Steam ships the logo SEPARATELY (logo.png, transparent), so the
# tile is composed instead: hero art centre-cropped square with the logo
# scaled and pasted dead centre. Cached per game, rebuilt when the source art
# changes; every failure falls back to the uncomposed art.
COMPOSED_DIR = os.path.expanduser('~/.local/share/game-tiles/composed')
TILE_SIZE = 600

# Unified recency: game-launch touches ~/.local/share/game-tiles/lastplayed/<key>
# on every fresh launch (key = steam appid, or a PS4 dump's folder name), so
# Steam AND shadPS4 games share one "most recently played" order. Steam's own
# manifest LastPlayed is still read and max()'d in, so a game played through
# Steam directly (not via the couch) still floats up.
LASTPLAYED_DIR = os.path.expanduser('~/.local/share/game-tiles/lastplayed')


def _stamp(key):
    try:
        return int(os.path.getmtime(os.path.join(LASTPLAYED_DIR, str(key))))
    except OSError:
        return 0


# Playtime + last-played for the stats line under the focused game (PS5-style).
# Steam keeps per-app playtime (minutes) and LastPlayed in localconfig.vdf;
# shadPS4 keeps H:M:S per serial in play_time.txt. All local, no network.
_STEAM_USERDATA = os.path.expanduser('~/.steam/steam/userdata')
_PS4_PLAYTIME = os.path.expanduser('~/.local/share/shadPS4/play_time.txt')


def _steam_playtimes():
    out = {}
    try:
        for sid in os.listdir(_STEAM_USERDATA):
            cfg = os.path.join(_STEAM_USERDATA, sid, 'config', 'localconfig.vdf')
            if not os.path.isfile(cfg):
                continue
            txt = open(cfg, encoding='utf-8', errors='replace').read()
            m = re.search(r'"apps"\s*\{', txt)
            body = txt[m.end():] if m else txt
            for am in re.finditer(
                    r'"(\d+)"\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*?)\}', body):
                pt = re.search(r'"Playtime"\s*"(\d+)"', am.group(2))
                if pt:
                    out[am.group(1)] = int(pt.group(1))
    except OSError:
        pass
    return out


def _ps4_playtime_min(serial):
    try:
        for line in open(_PS4_PLAYTIME, encoding='utf-8', errors='replace'):
            parts = line.split()
            if len(parts) == 2 and parts[0] == serial:
                h, m, s = (parts[1].split(':') + ['0', '0'])[:3]
                return int(h) * 60 + int(m)
    except OSError:
        pass
    return 0


def _fmt_playtime(minutes):
    if minutes <= 0:
        return ''
    if minutes < 60:
        return '%d min played' % minutes
    h = minutes / 60.0
    return '%.0f hours played' % h if h >= 10 else '%.1f hours played' % h


def _fmt_lastplayed(ts):
    if not ts:
        return ''
    import time
    d = max(0, int(time.time()) - ts)
    if d < 3600:
        return 'Played just now'
    if d < 86400:
        return 'Played %dh ago' % (d // 3600)
    if d < 86400 * 14:
        n = d // 86400
        return 'Played %d day%s ago' % (n, '' if n == 1 else 's')
    return 'Played %d weeks ago' % (d // (86400 * 7))

# Steam's client caches heroes at 1920x620; the CDN has 3840x1240 versions
# which ~/couch/tools/fetch-steam-heroes mirrors here. The listing prefers a
# mirrored hero for fanart (the 4K home background) and quietly re-runs the
# fetcher at most once a day so new installs pick theirs up.
HERO_DIR = os.path.expanduser('~/.local/share/game-tiles/heroes')
HERO_FETCHER = os.path.expanduser('~/couch/tools/fetch-steam-heroes')
HERO_STAMP = os.path.join(HERO_DIR, '.last-fetch')

# Achievement counts (got/total) cached by tools/fetch-steam-achievements,
# refreshed hourly in the background. Empty until the Steam profile's "Game
# details" privacy is Public - the row just shows no achievement line then.
ACH_CACHE = os.path.expanduser('~/.local/share/game-tiles/achievements.json')
ACH_FETCHER = os.path.expanduser('~/couch/tools/fetch-steam-achievements')
ACH_STAMP = os.path.expanduser('~/.local/share/game-tiles/.ach-fetch')


def _achievements():
    try:
        return json.load(open(ACH_CACHE))
    except Exception:
        return {}


def _ach_refresh():
    try:
        import time
        if (not os.path.isfile(ACH_STAMP)
                or time.time() - os.path.getmtime(ACH_STAMP) > 3600):
            open(ACH_STAMP, 'w').close()
            host_popen(['python3', ACH_FETCHER], start_new_session=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            trophies = os.path.expanduser('~/couch/tools/ps4-trophies')
            if os.path.isfile(trophies):
                host_popen(['python3', trophies, '--placeholder'],
                           start_new_session=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            warmer = os.path.expanduser('~/couch/tools/warm-loading-cards')
            if os.path.isfile(warmer):
                host_popen(['python3', warmer], start_new_session=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            sizer = os.path.expanduser('~/couch/tools/warm-game-sizes')
            if os.path.isfile(sizer):
                host_popen(['python3', sizer], start_new_session=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _hero_refresh():
    try:
        import time
        if (not os.path.isfile(HERO_STAMP)
                or time.time() - os.path.getmtime(HERO_STAMP) > 24 * 3600):
            os.makedirs(HERO_DIR, exist_ok=True)
            open(HERO_STAMP, 'w').close()
            host_popen(['python3', HERO_FETCHER], start_new_session=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _composed_tile(appid, art):
    src = art.get('fanart') or art.get('poster') or art.get('thumb')
    logo = art.get('clearlogo')
    if not src:
        return None
    if not logo:
        # No separate logo to centre: the portrait capsule usually carries its
        # title near the middle, so its centre crop is the best square there is.
        src = art.get('poster') or src
    out = os.path.join(COMPOSED_DIR, '%s.png' % appid)
    try:
        stamp = max(os.path.getmtime(p) for p in (src, logo) if p)
        if os.path.isfile(out) and os.path.getmtime(out) >= stamp:
            return out
        from PIL import Image
        os.makedirs(COMPOSED_DIR, exist_ok=True)
        base = Image.open(src).convert('RGB')
        side = min(base.size)
        cx, cy = base.width // 2, base.height // 2
        base = base.crop((cx - side // 2, cy - side // 2,
                          cx + side // 2, cy + side // 2))
        base = base.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
        if logo:
            lg = Image.open(logo).convert('RGBA')
            scale = min(TILE_SIZE * 0.76 / lg.width, TILE_SIZE * 0.46 / lg.height, 1.0)
            lg = lg.resize((max(1, int(lg.width * scale)),
                            max(1, int(lg.height * scale))), Image.LANCZOS)
            base = base.convert('RGBA')
            base.alpha_composite(lg, ((TILE_SIZE - lg.width) // 2,
                                      (TILE_SIZE - lg.height) // 2))
        base.convert('RGB').save(out)
        return out
    except Exception:
        return None


def _field(key, txt):
    m = re.search(r'"%s"\s+"([^"]*)"' % key, txt)
    return m.group(1) if m else ''


def _games():
    out = []
    for path in glob.glob(os.path.join(STEAMAPPS, 'appmanifest_*.acf')):
        try:
            txt = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        appid = _field('appid', txt)
        name = _field('name', txt)
        if not appid or not name or PLUMBING.search(name):
            continue
        try:
            if not int(_field('StateFlags', txt)) & 4:  # 4 = fully installed
                continue
        except ValueError:
            continue
        try:
            last = int(_field('LastPlayed', txt) or 0)
        except ValueError:
            last = 0
        try:
            size = int(_field('SizeOnDisk', txt) or 0)
        except ValueError:
            size = 0
        out.append((name, appid, max(last, _stamp(appid)), size))
    return out  # (name, appid, last, size); games_route sorts the merged row


SIZE_CACHE = os.path.expanduser('~/.local/share/game-tiles/sizes.json')


def _fmt_size(nbytes):
    if nbytes <= 0:
        return ''
    gb = nbytes / 1073741824.0
    if gb >= 10:
        return '%d GB' % round(gb)
    if gb >= 1:
        return '%.1f GB' % gb
    return '%d MB' % max(1, round(nbytes / 1048576.0))


def _dir_size_cached(path):
    """What ~/couch/tools/warm-game-sizes last measured, or 0.

    A READER, deliberately. This used to key the cache on the game folder's
    own mtime and walk the tree on a miss - and a directory's mtime does not
    move when its CONTENTS grow, only when its own entries do, so a game that
    gained 11 GB of mods three levels down kept its old number for ever
    (measured: Bloodborne's tile said 29.3 GB for a 40.5 GB game). Meanwhile
    the miss path was a 28,778-file walk, 267ms, with the player waiting on a
    directory listing.

    Invalidating harder would have made the stall more common, not less. The
    walk lives in the hourly warmer now; a size up to an hour stale is worth
    having, a listing that stalls to compute one is not. 0 renders as no size
    at all, which is the honest answer before the first warm.
    """
    try:
        cache = json.load(open(SIZE_CACHE))
    except Exception:
        return 0
    ent = cache.get(path)
    if isinstance(ent, list) and len(ent) > 1:
        return ent[1] or 0
    return 0


def _art(appid):
    base = os.path.join(LIBCACHE, appid)
    art = {}
    # Steam caches the portrait capsule as library_600x900.jpg (older caches
    # named it library_capsule.jpg); the header is landscape. Looking for the
    # old name only meant EVERY tile fell back to the header and got zoom-cropped.
    for key, names in (('poster', ('library_600x900.jpg', 'library_capsule.jpg')),
                       ('fanart', ('library_hero.jpg',)),
                       ('thumb', ('header.jpg', 'library_header.jpg'))):
        for fname in names:
            hit = glob.glob(os.path.join(base, '**', fname), recursive=True)
            if hit:
                art[key] = hit[0]
                break
    # Steam fills its art cache lazily, so fall back through whatever exists
    # rather than leaving a game as a bare label.
    if not art.get('thumb'):
        for alt in ('poster', 'fanart'):
            if art.get(alt):
                art['thumb'] = art[alt]
                break
    logo = os.path.join(base, 'logo.png')
    if os.path.exists(logo):
        art['clearlogo'] = logo
    hero2x = os.path.join(HERO_DIR, '%s.jpg' % appid)
    if os.path.isfile(hero2x):
        art['fanart'] = hero2x
    return art


def _paused_frame(appid):
    """The newest freeze-frame for a paused game, for the CARD only.

    pause-snap writes <appid>__<epoch_ms>.jpg and keeps only the newest, so
    the last name in sort order is the current capture. Returns '' when there
    is nothing to show.

    THE TILE KEEPS ITS OWN ART. This used to hand back thumb/poster overrides
    as well, so a paused game's tile in the row became the screencap - which
    made sense when the freeze-frame had nowhere else to live. It has a
    dedicated card now (Home.xml reads CouchPausedSnap), and showing the same
    frame twice cost the row the thing that makes it scannable: every game
    recognisable by its own cover. A paused game is still marked - it carries
    the "- paused" label and the card - it just no longer stops looking like
    itself. (pause-snap's 2:3 `.tile.jpg` crop existed only for this and is
    now unused; it is left alone rather than chased out of the writer.)
    """
    safe = re.sub(r'[^A-Za-z0-9._-]', '_', str(appid))[:100]
    try:
        names = os.listdir(PAUSED_DIR)
    except OSError:
        return ''
    frames = sorted(n for n in names
                    if n.startswith(safe + '__') and n.endswith('.jpg')
                    and not n.endswith('.tile.jpg'))
    if not frames:
        return ''
    return os.path.join(PAUSED_DIR, frames[-1])


def _sfo(path):
    # param.sfo is a small binary key/value blob PS4 dumps carry in sce_sys.
    # Just enough of a parser to pull TITLE (and whatever else) out of it.
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return {}
    if data[:4] != b'\x00PSF':
        return {}
    try:
        key_start, data_start, count = struct.unpack_from('<III', data, 8)
        out = {}
        for i in range(count):
            koff, fmt, length, _max, doff = struct.unpack_from('<HHIII', data, 20 + i * 16)
            ks = key_start + koff
            key = data[ks:data.index(b'\x00', ks)].decode('utf-8', 'replace')
            raw = data[data_start + doff:data_start + doff + length]
            if fmt == 0x0404:  # int32
                out[key] = struct.unpack_from('<I', raw)[0]
            else:              # utf8 (0x0204) / utf8-special (0x0004)
                out[key] = raw.split(b'\x00', 1)[0].decode('utf-8', 'replace')
        return out
    except Exception:
        return {}


def _ps4_games():
    # A subfolder is a game if it has an eboot.bin. Name and cover come from the
    # dump's own sce_sys, so a properly dumped game just appears with the right
    # title and art; the folder name is the fallback if metadata is missing.
    out = []
    if not os.path.isdir(PS4_DIR):
        return out
    for entry in os.listdir(PS4_DIR):
        # Update/patch folders (e.g. CUSA00900-patch) also carry an eboot.bin
        # but are not games in their own right - shadPS4 overlays them on the
        # base automatically, so they must not become their own tiles.
        if entry.endswith('-patch') or entry.endswith('-UPDATE'):
            continue
        gdir = os.path.join(PS4_DIR, entry)
        eboot = os.path.join(gdir, 'eboot.bin')
        if not os.path.isfile(eboot):
            continue
        sfo = os.path.join(gdir, 'sce_sys', 'param.sfo')
        title = _sfo(sfo).get('TITLE') if os.path.isfile(sfo) else ''
        # PS4 icon0 is square (512x512); a portrait cover.png (2:3) in the game
        # folder is preferred so the tile fills without cropping the square art.
        # A hand-placed tile.png (square key art) beats both for the home row's
        # square tiles; cover.png still serves the portrait poster grids.
        cover = os.path.join(gdir, 'cover.png')
        icon0 = os.path.join(gdir, 'sce_sys', 'icon0.png')
        tile = os.path.join(gdir, 'tile.png')
        art = cover if os.path.isfile(cover) else (icon0 if os.path.isfile(icon0) else '')
        thumb = tile if os.path.isfile(tile) else art
        out.append((title or entry, eboot, art, thumb, _stamp(entry)))
    return out  # (title, eboot, art, thumb, last); merged + sorted in games_route


def games_route(info, params):
    handle = int(sys.argv[1])

    if info == 'launch_game':
        target = params.get('id', '')
        if target == 'bigpicture':
            cmd = [LAUNCHER, 'bigpicture']
        elif target == 'shadps4':
            cmd = [LAUNCHER, 'shadps4']
        elif target.startswith('ps4:'):
            cmd = [LAUNCHER, 'shadps4', urllib.parse.unquote(target[4:])]
        else:
            cmd = [LAUNCHER, 'steam', target]
        # The launch flourish: home's focused tile zooms and the screen fades
        # to black under it (Home.xml reads this property) - the dark cover
        # also hides the Kodi -> Big Picture flip until the curtain takes
        # over. The alarm self-clears it so a failed launch cannot strand a
        # black home screen.
        try:
            import xbmc
            xbmcgui.Window(10000).setProperty('CouchLaunching', '1')
            xbmc.executebuiltin(
                'AlarmClock(couchlaunchclear,'
                'ClearProperty(CouchLaunching,home),00:00:12,silent)')
        except Exception:
            pass
        # Detached: the launcher outlives this interpreter and always hands
        # the controller back, however the game ends.
        host_popen(cmd, start_new_session=True)
        if handle >= 0:
            xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    # Present as movie content so Copacetic's grid renders it like the Movies
    # screen: portrait poster tiles, which (unlike the wide landscape default)
    # centre and fit a short row instead of overflowing the right edge. Steam
    # capsule art is already portrait; the icon-only tiles below carry a poster
    # too so they sit in the grid cleanly.
    xbmcplugin.setContent(handle, 'movies')

    # A frozen game keeps its place on the row, marked, and picking it thaws it.
    suspended = (host_read('/tmp/game-suspended') or '').strip()

    _hero_refresh()
    _ach_refresh()
    steam_pt = _steam_playtimes()
    ach = _achievements()

    # One merged, recency-sorted list of every game (Steam + PS4), so the row
    # leads with whatever was played last regardless of platform. Never-played
    # (last 0) fall to the end, alphabetical. The app tiles come after.
    entries = []  # (last, name_lower, kind, payload)
    for name, appid, last, size in _games():
        entries.append((last, name.lower(), 'steam', (name, appid, size)))
    for title, eboot, icon, thumb, last in _ps4_games():
        entries.append((last, title.lower(), 'ps4', (title, eboot, icon, thumb)))
    entries.sort(key=lambda e: (-e[0], e[1]))

    li = []
    for last, _key, kind, payload in entries:
        if kind == 'steam':
            name, appid, size = payload
            label = f'{name} · paused' if appid == suspended else name
            item = xbmcgui.ListItem(label, offscreen=True)
            art = _art(appid)
            tile = _composed_tile(appid, art)
            if tile:
                art['thumb'] = tile
            if appid == suspended:
                # The card owns the freeze-frame, and only the card: the
                # backdrop keeps the hero art and the tile keeps its cover.
                snap = _paused_frame(appid)
                if snap:
                    item.setProperty('CouchPausedSnap', snap)
            item.setArt(art)
            item.setProperty('CouchPlaytime', _fmt_playtime(steam_pt.get(appid, 0)))
            item.setProperty('CouchLastPlayed', _fmt_lastplayed(last))
            if ach.get(appid):
                item.setProperty('CouchAchievements', ach[appid] + ' achievements')
            item.setProperty('CouchSize', _fmt_size(size))
            item.setProperty('appid', appid)
            li.append((f'{sys.argv[0]}?info=launch_game&id={appid}', item, False))
        else:
            title, eboot, icon, thumb = payload
            paused4 = suspended and suspended == eboot
            item = xbmcgui.ListItem(
                f'{title} · paused' if paused4 else title, offscreen=True)
            serial0 = os.path.basename(os.path.dirname(eboot))
            art = {}
            if icon or thumb:
                art = {'thumb': thumb or icon, 'poster': icon or thumb,
                       'icon': icon or thumb}
            # PS4 games have no Steam CDN hero; use a hand-placed 4K hero at
            # heroes/<serial>.jpg for the home backdrop, else the 1080p pic1.
            hero = os.path.join(HERO_DIR, '%s.jpg' % serial0)
            if os.path.isfile(hero):
                art['fanart'] = hero
            else:
                pic1 = os.path.join(os.path.dirname(eboot), 'sce_sys', 'pic1.png')
                if os.path.isfile(pic1):
                    art['fanart'] = pic1
            logo = os.path.expanduser(
                '~/.local/share/game-tiles/logos/%s.png'
                % os.path.basename(os.path.dirname(eboot)))
            if os.path.isfile(logo):
                art['clearlogo'] = logo
            if paused4:
                snap = _paused_frame(eboot)
                if snap:
                    item.setProperty('CouchPausedSnap', snap)
            if art:
                item.setArt(art)
            serial = os.path.basename(os.path.dirname(eboot))
            item.setProperty('CouchPlaytime', _fmt_playtime(_ps4_playtime_min(serial)))
            item.setProperty('CouchLastPlayed', _fmt_lastplayed(last))
            if ach.get(serial):
                item.setProperty('CouchAchievements', ach[serial] + ' trophies')
            item.setProperty('CouchSize', _fmt_size(_dir_size_cached(os.path.dirname(eboot))))
            item.setProperty('appid', serial)
            gid = 'ps4:' + urllib.parse.quote(eboot, safe='')
            li.append((f'{sys.argv[0]}?info=launch_game&id={gid}', item, False))

    bp = xbmcgui.ListItem('Big Picture', offscreen=True)
    bp_poster = STEAM_TILE if os.path.exists(STEAM_TILE) else STEAM_ICON
    bp_thumb = STEAM_TILE_SQ if os.path.exists(STEAM_TILE_SQ) else bp_poster
    bp.setArt({'thumb': bp_thumb, 'poster': bp_poster, 'icon': STEAM_ICON})
    li.append((f'{sys.argv[0]}?info=launch_game&id=bigpicture', bp, False))

    # The emulator itself: opens shadPS4's own controller-driven library.
    if os.path.exists(SHADPS4_APP):
        shad = xbmcgui.ListItem('shadPS4', offscreen=True)
        s_poster = SHADPS4_TILE if os.path.exists(SHADPS4_TILE) else GAMEPAD_ICON
        s_thumb = SHADPS4_TILE_SQ if os.path.exists(SHADPS4_TILE_SQ) else s_poster
        shad.setArt({'thumb': s_thumb, 'poster': s_poster, 'icon': GAMEPAD_ICON})
        li.append((f'{sys.argv[0]}?info=launch_game&id=shadps4', shad, False))

    xbmcplugin.addDirectoryItems(handle, li)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)

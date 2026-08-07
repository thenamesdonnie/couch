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
import os
import re
import struct
import subprocess
import sys
import urllib.parse

import xbmcgui
import xbmcplugin

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
        out.append((name, appid))
    return sorted(out, key=lambda g: g[0].lower())


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
    return art


def _paused_art(appid):
    """The newest freeze-frame pair for a paused game, as art overrides.

    pause-snap writes <appid>__<epoch_ms>.jpg (the 16:9 frame) beside
    <appid>__<epoch_ms>.tile.jpg (a 2:3 centre crop for the poster grid), and
    keeps only the newest pair, so the last name in sort order is the current
    capture. Returns {} when there is nothing to show.
    """
    safe = re.sub(r'[^A-Za-z0-9._-]', '_', str(appid))[:100]
    try:
        names = os.listdir(PAUSED_DIR)
    except OSError:
        return {}
    frames = sorted(n for n in names
                    if n.startswith(safe + '__') and n.endswith('.jpg')
                    and not n.endswith('.tile.jpg'))
    if not frames:
        return {}
    frame = os.path.join(PAUSED_DIR, frames[-1])
    tile = frame[:-len('.jpg')] + '.tile.jpg'
    # The row is a portrait poster grid, so the tile gets the 2:3 crop and the
    # full frame becomes the backdrop behind the highlighted game.
    art = {'thumb': frame, 'fanart': frame}
    art['poster'] = tile if os.path.isfile(tile) else frame
    return art


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
        cover = os.path.join(gdir, 'cover.png')
        icon0 = os.path.join(gdir, 'sce_sys', 'icon0.png')
        art = cover if os.path.isfile(cover) else (icon0 if os.path.isfile(icon0) else '')
        out.append((title or entry, eboot, art))
    return sorted(out, key=lambda g: g[0].lower())


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
        # Detached: the launcher outlives this interpreter and always hands
        # the controller back, however the game ends.
        subprocess.Popen(cmd, start_new_session=True)
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
    suspended = ''
    try:
        with open('/tmp/game-suspended') as f:
            suspended = f.read().strip()
    except OSError:
        pass

    li = []
    for name, appid in _games():
        label = f'{name} · paused' if appid == suspended else name
        item = xbmcgui.ListItem(label, offscreen=True)
        art = _art(appid)
        tile = _composed_tile(appid, art)
        if tile:
            art['thumb'] = tile
        if appid == suspended:
            # ...wearing the frame it was frozen on. Clearlogo stays: the
            # game's name over its own last frame is the point.
            art.update(_paused_art(appid))
        item.setArt(art)
        li.append((f'{sys.argv[0]}?info=launch_game&id={appid}', item, False))

    # Emulated PS4 dumps, each launching straight into its own game.
    for title, eboot, icon in _ps4_games():
        item = xbmcgui.ListItem(title, offscreen=True)
        if icon:
            item.setArt({'thumb': icon, 'poster': icon, 'icon': icon})
        gid = 'ps4:' + urllib.parse.quote(eboot, safe='')
        li.append((f'{sys.argv[0]}?info=launch_game&id={gid}', item, False))

    bp = xbmcgui.ListItem('Big Picture', offscreen=True)
    bp_poster = STEAM_TILE if os.path.exists(STEAM_TILE) else STEAM_ICON
    bp.setArt({'thumb': bp_poster, 'poster': bp_poster, 'icon': STEAM_ICON})
    li.append((f'{sys.argv[0]}?info=launch_game&id=bigpicture', bp, False))

    # The emulator itself: opens shadPS4's own controller-driven library.
    if os.path.exists(SHADPS4_APP):
        shad = xbmcgui.ListItem('shadPS4', offscreen=True)
        s_poster = SHADPS4_TILE if os.path.exists(SHADPS4_TILE) else GAMEPAD_ICON
        shad.setArt({'thumb': s_poster, 'poster': s_poster, 'icon': GAMEPAD_ICON})
        li.append((f'{sys.argv[0]}?info=launch_game&id=shadps4', shad, False))

    xbmcplugin.addDirectoryItems(handle, li)
    xbmcplugin.endOfDirectory(handle)

# Local addition (Stagelight): the achievements grid for the focused game.
# Reads the per-game detail cached by ~/couch/tools/fetch-steam-achievements
# (Steam schema + the player's unlock state) and renders each as a tile with
# its Steam icon, name, description and an Unlocked/Locked property the skin
# colours. Unlocked first, then locked. Empty (no cache / private) -> no items.
import json
import os
import sys

import xbmcgui
import xbmcplugin

DETAIL_DIR = os.path.expanduser('~/.local/share/game-tiles/achievements')


def achievements_route(params):
    handle = int(sys.argv[1])
    xbmcplugin.setContent(handle, 'games')
    appid = params.get('appid', '')
    try:
        rows = json.load(open(os.path.join(DETAIL_DIR, '%s.json' % appid)))
    except Exception:
        rows = []
    items = []
    for a in rows:
        li = xbmcgui.ListItem(a.get('name', ''), offscreen=True)
        icon = a.get('icon', '')
        li.setArt({'thumb': icon, 'icon': icon})
        li.setProperty('desc', a.get('desc', ''))
        li.setProperty('unlocked', '1' if a.get('unlocked') else '')
        li.setInfo('game', {'title': a.get('name', ''),
                            'plot': a.get('desc', '')})
        # display-only; a harmless self-path keeps Kodi from dropping it
        li.setProperty('IsPlayable', 'false')
        items.append((sys.argv[0], li, False))
    xbmcplugin.addDirectoryItems(handle, items)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)

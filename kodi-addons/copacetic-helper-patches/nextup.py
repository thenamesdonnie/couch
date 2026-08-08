# Local addition for the living-room console build. NOT part of the upstream
# script.copacetic.helper - re-apply after any addon update.
#
# The Stagelight Library's "Next up" row, with Donnie's frontier rule
# (8 Aug 2026): a show's FRONTIER is the furthest episode you have finished,
# in season/episode order. If the episode you are partway through IS at (or
# past) the frontier, you are genuinely mid-episode - the show belongs to
# the Continue row alone and is skipped here. If the half-watched episode
# sits BEHIND the frontier (an old resume, probably watched elsewhere), it
# is stale: recommend the first unwatched episode after the frontier and
# ignore the stale one. Shows are ordered by last played, newest first.
import json
import sys

import xbmc
import xbmcgui
import xbmcplugin


def _json(method, params):
    out = xbmc.executeJSONRPC(json.dumps(
        {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}))
    return json.loads(out).get('result', {})


def _pos(ep):
    return (ep.get('season', 0), ep.get('episode', 0))


def nextup_route():
    handle = int(sys.argv[1])
    xbmcplugin.setContent(handle, 'episodes')

    shows = _json('VideoLibrary.GetTVShows', {
        'properties': ['title'],
        'sort': {'method': 'lastplayed', 'order': 'descending'},
        'filter': {'field': 'inprogress', 'operator': 'true', 'value': ''},
        'limits': {'end': 25},
    }).get('tvshows', [])

    items = []
    for show in shows:
        eps = _json('VideoLibrary.GetEpisodes', {
            'tvshowid': show['tvshowid'],
            'properties': ['season', 'episode', 'playcount', 'resume',
                           'title', 'showtitle', 'art', 'plot', 'rating',
                           'firstaired', 'runtime', 'file'],
        }).get('episodes', [])
        eps = [e for e in eps if e.get('season', 0) > 0]  # no specials

        watched = [e for e in eps if e.get('playcount', 0) > 0]
        inprog = [e for e in eps
                  if e.get('resume', {}).get('position', 0) > 0
                  and e.get('playcount', 0) == 0]
        frontier = max((_pos(e) for e in watched), default=None)
        inprog_max = max((_pos(e) for e in inprog), default=None)

        # Mid-episode at the frontier: Continue owns this show.
        if inprog_max and (frontier is None or inprog_max >= frontier):
            continue

        candidates = [e for e in eps
                      if e.get('playcount', 0) == 0
                      and e.get('resume', {}).get('position', 0) == 0
                      and (frontier is None or _pos(e) > frontier)]
        if not candidates:
            continue
        nxt = min(candidates, key=_pos)

        li = xbmcgui.ListItem(nxt.get('title', ''), offscreen=True)
        li.setInfo('video', {
            'mediatype': 'episode',
            'tvshowtitle': nxt.get('showtitle', show.get('title', '')),
            'title': nxt.get('title', ''),
            'season': nxt.get('season', 0),
            'episode': nxt.get('episode', 0),
            'plot': nxt.get('plot', ''),
            'rating': nxt.get('rating', 0),
            'aired': nxt.get('firstaired', ''),
            'duration': nxt.get('runtime', 0),
        })
        art = nxt.get('art', {}) or {}
        li.setArt({'thumb': art.get('thumb', ''),
                   'fanart': art.get('tvshow.fanart', art.get('fanart', '')),
                   'clearlogo': art.get('tvshow.clearlogo', '')})
        li.setProperty('IsPlayable', 'true')
        items.append((nxt.get('file', ''), li, False))

    xbmcplugin.addDirectoryItems(handle, items)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


def continue_route():
    """The Continue row, frontier-filtered: only in-progress episodes AT a
    show's frontier (its furthest finished point). A resume stranded BEHIND
    the frontier is stale - probably watched elsewhere - and is hidden, not
    cleared: nothing is written back to the library or Jellyfin, so the
    resume point survives in the show's own episode list. (Donnie, 8 Aug:
    hide beats telling Jellyfin to forget.)"""
    handle = int(sys.argv[1])
    xbmcplugin.setContent(handle, 'episodes')

    shows = _json('VideoLibrary.GetTVShows', {
        'properties': ['title'],
        'sort': {'method': 'lastplayed', 'order': 'descending'},
        'filter': {'field': 'inprogress', 'operator': 'true', 'value': ''},
        'limits': {'end': 25},
    }).get('tvshows', [])

    items = []
    for show in shows:
        eps = _json('VideoLibrary.GetEpisodes', {
            'tvshowid': show['tvshowid'],
            'properties': ['season', 'episode', 'playcount', 'resume',
                           'title', 'showtitle', 'art', 'plot', 'rating',
                           'firstaired', 'runtime', 'file'],
        }).get('episodes', [])
        eps = [e for e in eps if e.get('season', 0) > 0]
        watched = [e for e in eps if e.get('playcount', 0) > 0]
        inprog = [e for e in eps
                  if e.get('resume', {}).get('position', 0) > 0
                  and e.get('playcount', 0) == 0]
        frontier = max((_pos(e) for e in watched), default=None)
        seen = set()
        for e in sorted(inprog, key=_pos):
            if frontier is not None and _pos(e) < frontier:
                continue  # stale resume behind the frontier: hidden
            if _pos(e) in seen:
                continue  # duplicate library entries for one episode
            seen.add(_pos(e))
            li = xbmcgui.ListItem(e.get('title', ''), offscreen=True)
            li.setInfo('video', {
                'mediatype': 'episode',
                'tvshowtitle': e.get('showtitle', show.get('title', '')),
                'title': e.get('title', ''),
                'season': e.get('season', 0),
                'episode': e.get('episode', 0),
                'plot': e.get('plot', ''),
                'rating': e.get('rating', 0),
                'aired': e.get('firstaired', ''),
                'duration': e.get('runtime', 0),
            })
            art = e.get('art', {}) or {}
            li.setArt({'thumb': art.get('thumb', ''),
                       'fanart': art.get('tvshow.fanart', art.get('fanart', '')),
                       'clearlogo': art.get('tvshow.clearlogo', '')})
            li.setProperty('IsPlayable', 'true')
            items.append((e.get('file', ''), li, False))

    xbmcplugin.addDirectoryItems(handle, items)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)




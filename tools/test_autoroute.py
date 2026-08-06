#!/usr/bin/env python3
"""Unit tests for the HDR auto-route service addon's pure logic (autoroute.py).

Pure functions only: deciding what may be intercepted, pulling an item id out
of the url Kodi is playing, reading the server's routing answer, and the
no-loop guard. No Kodi, no network, no live paths - the mapping database is
built in pytest's tmp_path with the schema plugin.video.jellyfin creates, the
same way tools/test_playontv.py does it.

The impure edges (the Player callback, urllib, stopping playback,
notifications) live in service.py and are only checkable on the box with Kodi
up.

Run:  couchd/.venv/bin/pytest tools/test_autoroute.py -q
"""
import importlib.machinery
import importlib.util
import os
import sqlite3
import sys

ADDONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'kodi-addons')

# autoroute imports playontv, exactly as it does inside Kodi: the entry point
# puts the "Play on TV" addon's directory on sys.path first. Reproducing that
# contract here is deliberate - if the two ever stop lining up, this import
# fails and the test suite says so.
_SHARED = os.path.join(ADDONS, 'context.couch.playontv')
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

_spec = importlib.util.spec_from_loader(
    'autoroute', importlib.machinery.SourceFileLoader(
        'autoroute', os.path.join(ADDONS, 'service.couch.autoroute', 'autoroute.py')))
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)

MOVIE_ID = 'ba859e08966be52986a1dc0aff17deb5'
EPISODE_ID = '0f5067c18ed08bd36347db55d35a0801'


def make_db(tmp_path):
    path = str(tmp_path / 'jellyfin.db')
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE jellyfin(
        jellyfin_id TEXT UNIQUE, media_folder TEXT, jellyfin_type TEXT, media_type TEXT,
        kodi_id INTEGER, kodi_fileid INTEGER, kodi_pathid INTEGER, parent_id INTEGER,
        checksum INTEGER, jellyfin_parent_id TEXT)""")
    con.executemany('INSERT INTO jellyfin VALUES (?,?,?,?,?,?,?,?,?,?)', [
        (MOVIE_ID, 'f', 'Movie', 'movie', 2, 2, 1, None, '{}', 'p'),
        (EPISODE_ID, 'f', 'Episode', 'episode', 2, 9, 1, 4, '{}', 'p'),
        ('538b7811c151a280abde6dd6e569ad37', 'f', 'Season', 'season', 2, None, None, 4, '{}', 'p'),
    ])
    con.commit()
    con.close()
    return path


class Clock:
    """A hand-wound monotonic clock."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def tick(self, seconds):
        self.t += seconds


# -- what may be intercepted at all ------------------------------------------

def test_library_movie_and_episode_resolve(tmp_path):
    db = make_db(tmp_path)
    assert ar.target_id(None, 2, 'movie', db) == MOVIE_ID
    assert ar.target_id(None, 2, 'episode', db) == EPISODE_ID


def test_containers_and_non_video_are_never_intercepted(tmp_path):
    db = make_db(tmp_path)
    for media in ('season', 'tvshow', 'musicvideo', 'song', '', None, 'set'):
        assert ar.target_id(None, 2, media, db) is None


def test_a_jellyfin_id_alone_does_not_get_a_trailer_routed(tmp_path):
    # THE guard that matters here and not in the context item: the context
    # menu is filtered by its <visible> condition, this service sees every
    # single thing Kodi starts. A jellyfinid property on a non-library row
    # must not be enough on its own.
    db = make_db(tmp_path)
    assert ar.target_id(MOVIE_ID, -1, 'movie', db) == MOVIE_ID
    for media in ('', None, 'video', 'unknown'):
        assert ar.target_id(MOVIE_ID, -1, media, db) is None


def test_unsynced_item_is_not_intercepted(tmp_path):
    assert ar.target_id(None, 999, 'movie', make_db(tmp_path)) is None


def test_missing_database_is_not_intercepted(tmp_path):
    assert ar.target_id(None, 2, 'movie', str(tmp_path / 'nope.db')) is None


def test_playable_gate_is_case_insensitive():
    assert ar.playable('Movie') and ar.playable('EPISODE')
    assert not ar.playable('Season') and not ar.playable(None)


# -- the id inside the url being played --------------------------------------

def test_plugin_and_stream_urls_give_up_their_id():
    for url in (
            'plugin://plugin.video.jellyfin/?mode=play&id=%s' % MOVIE_ID,
            'plugin://plugin.video.jellyfin/?id=%s&mode=play&dbid=2' % MOVIE_ID,
            'http://localhost:8096/Videos/%s/stream?static=true' % MOVIE_ID,
            'http://localhost:8096/Items/%s/Download' % MOVIE_ID,
            'plugin://plugin.video.jellyfin/?item_id=%s' % MOVIE_ID,
    ):
        assert ar.id_from_path(url) == MOVIE_ID


def test_dashed_guid_in_a_url_is_canonicalised():
    dashed = 'BA859E08-966B-E529-86A1-DC0AFF17DEB5'
    assert ar.id_from_path('plugin://plugin.video.jellyfin/?id=%s' % dashed) == MOVIE_ID


def test_a_url_full_of_hex_does_not_yield_a_fake_id():
    # An api_key or a device id is 32 hex too. Matching those would send the
    # server hunting for an item that does not exist, or worse, the wrong one.
    for url in (
            'http://localhost:8096/Videos/stream?api_key=%s' % ('f' * 32),
            'http://localhost:8096/x?DeviceId=%s' % ('c' * 32),
            'smb://nas/films/The Batman (2022)/The Batman.mkv',
            '', None, 'plugin://plugin.video.youtube/play/?video_id=abc',
    ):
        assert ar.id_from_path(url) is None


# -- waiting for the player to have an item ----------------------------------

def test_identity_needs_a_media_type_and_something_to_key_on():
    assert ar.has_identity((MOVIE_ID, -1, 'movie'))
    assert ar.has_identity((None, 2, 'movie'))
    assert not ar.has_identity((MOVIE_ID, 2, ''))     # no type yet
    assert not ar.has_identity((None, '-1', 'movie'))  # nothing to key on
    assert not ar.has_identity((None, '', 'movie'))
    assert not ar.has_identity((None, 0, 'movie'))
    assert not ar.has_identity(None)


def test_facts_that_arrive_late_are_waited_for():
    # onPlayBackStarted can beat the player to its own ListItem.
    answers = [(None, '', ''), (None, '', ''), (None, 2, 'movie')]
    slept = []
    got = ar.wait_for_facts(lambda: answers.pop(0), slept.append)
    assert got == (None, 2, 'movie')
    assert slept == [0.25, 0.25]  # no sleep after the successful read


def test_facts_that_never_arrive_give_up_quietly():
    slept = []
    got = ar.wait_for_facts(lambda: (None, '', ''), slept.append, attempts=4)
    assert got is None
    assert len(slept) == 3  # and never sleeps after the last attempt


# -- reading the server's answer ---------------------------------------------

def test_route_true_is_the_only_yes():
    assert ar.parse_should_route(200, '{"route":true,"reason":"HDR10 on the TV app"}') == \
        (True, 'HDR10 on the TV app')


def test_sdr_is_a_reasoned_no():
    route, reason = ar.parse_should_route(200, '{"route":false,"reason":"SDR, Kodi plays it"}')
    assert route is False and 'SDR' in reason


def test_an_unreachable_server_never_routes():
    route, reason = ar.parse_should_route(None, '')
    assert route is False
    assert 'not reachable' in reason


def test_error_codes_and_junk_never_route():
    for code, body in ((500, 'boom'), (404, ''), (502, '<html>bad gateway</html>'),
                       (200, 'not json'), (200, '[]'), (200, ''), (200, 'null')):
        assert ar.parse_should_route(code, body)[0] is False


def test_a_body_without_a_real_boolean_never_routes():
    # Only JSON true routes. A string or a number in that field means a proxy
    # or something else rewrote the body, and a guess is not worth a stopped
    # playback.
    for body in ('{}', '{"reason":"who knows"}', '{"route":"yes"}', '{"route":1}',
                 '{"route":"true"}'):
        assert ar.parse_should_route(200, body)[0] is False


# -- the no-loop guard -------------------------------------------------------

def test_one_interception_at_a_time():
    g = ar.RouteGuard(clock=Clock())
    assert g.claim(MOVIE_ID)
    assert not g.claim(EPISODE_ID)  # something else started while we were deciding
    assert not g.claim(MOVIE_ID)
    assert g.busy


def test_a_routed_item_does_not_re_trigger():
    clock = Clock()
    g = ar.RouteGuard(clock=clock)
    assert g.claim(MOVIE_ID)
    g.release(MOVIE_ID, routed=True)
    assert not g.busy
    assert not g.claim(MOVIE_ID)
    clock.tick(60)          # past the quiet period, still inside the cooldown
    assert not g.claim(MOVIE_ID)
    clock.tick(70)          # past both
    assert g.claim(MOVIE_ID)


def test_a_routed_playback_quiets_everything_briefly():
    # The cascade case: stopping a playlist item could let Kodi advance to the
    # next one, and each advance would otherwise look like a fresh click.
    clock = Clock()
    g = ar.RouteGuard(clock=clock)
    g.claim(MOVIE_ID)
    g.release(MOVIE_ID, routed=True)
    assert not g.claim(EPISODE_ID)
    clock.tick(31)
    assert g.claim(EPISODE_ID)


def test_an_item_we_did_not_route_behaves_normally_next_click():
    # An SDR film answered "no": clicking it again must not be swallowed.
    g = ar.RouteGuard(clock=Clock())
    g.claim(MOVIE_ID)
    g.release(MOVIE_ID, routed=False)
    assert g.claim(MOVIE_ID)


def test_a_second_click_inside_the_cooldown_plays_in_kodi():
    # Donnie's escape hatch, and it is deliberate: click it again and it stays
    # here, no setting to go and find.
    clock = Clock()
    g = ar.RouteGuard(clock=clock)
    g.claim(MOVIE_ID)
    g.release(MOVIE_ID, routed=True)
    clock.tick(35)
    assert not g.claim(MOVIE_ID)


def test_the_guard_does_not_grow_forever():
    clock = Clock()
    g = ar.RouteGuard(clock=clock)
    for i in range(50):
        item = '%032x' % i
        g.claim(item)
        g.release(item, routed=False)
        clock.tick(1)
    clock.tick(200)
    g.claim(MOVIE_ID)
    assert len(g._recent) == 1


def test_release_by_a_stranger_does_not_free_the_slot():
    g = ar.RouteGuard(clock=Clock())
    g.claim(MOVIE_ID)
    g.release(EPISODE_ID, routed=False)
    assert g.busy


# -- house style -------------------------------------------------------------

def test_no_em_dashes_anywhere_in_the_addon():
    addon_dir = os.path.join(ADDONS, 'service.couch.autoroute')
    for root, _dirs, files in os.walk(addon_dir):
        if '__pycache__' in root:
            continue
        for name in files:
            with open(os.path.join(root, name), encoding='utf-8') as f:
                assert '—' not in f.read(), name

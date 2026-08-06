#!/usr/bin/env python3
"""Unit tests for the Play on TV context addon's pure logic (playontv.py).

Pure functions only: turning a ListItem's facts into a Jellyfin item id
(property first, then the sync addon's jellyfin.db mapping), reading the
couch server's POST answer, and walking the handoff stages with fakes for
fetch/notify/clock. No Kodi, no live paths, no network - databases are built
in pytest's tmp_path with the same schema plugin.video.jellyfin creates.
The impure edges (sys.listitem, urllib, xbmcgui) live in context.py and are
only checkable on the box with Kodi up.

Run:  couchd/.venv/bin/pytest tools/test_playontv.py -q
"""
import importlib.machinery
import importlib.util
import os
import sqlite3

_spec = importlib.util.spec_from_loader(
    'playontv', importlib.machinery.SourceFileLoader(
        'playontv', os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..',
            'kodi-addons', 'context.couch.playontv', 'playontv.py')))
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)

MOVIE_ID = 'ba859e08966be52986a1dc0aff17deb5'
EPISODE_ID = '0f5067c18ed08bd36347db55d35a0801'


def make_db(tmp_path):
    """The mapping table exactly as plugin.video.jellyfin creates it."""
    path = str(tmp_path / 'jellyfin.db')
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE jellyfin(
        jellyfin_id TEXT UNIQUE, media_folder TEXT, jellyfin_type TEXT, media_type TEXT,
        kodi_id INTEGER, kodi_fileid INTEGER, kodi_pathid INTEGER, parent_id INTEGER,
        checksum INTEGER, jellyfin_parent_id TEXT)""")
    rows = [
        (MOVIE_ID, 'f', 'Movie', 'movie', 2, 2, 1, None, '{}', 'p'),
        (EPISODE_ID, 'f', 'Episode', 'episode', 2, 9, 1, 4, '{}', 'p'),
        ('538b7811c151a280abde6dd6e569ad37', 'f', 'Season', 'season', 2, None, None, 4, '{}', 'p'),
    ]
    con.executemany('INSERT INTO jellyfin VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    con.commit()
    con.close()
    return path


# -- normalize_item_id --------------------------------------------------------

def test_plain_32_hex_passes():
    assert pt.normalize_item_id(MOVIE_ID) == MOVIE_ID


def test_dashed_guid_and_case_are_canonicalised():
    # The addon's UserData carries ids in GUID form; the server only takes
    # plain lowercase hex.
    assert pt.normalize_item_id('BA859E08-966B-E529-86A1-DC0AFF17DEB5') == MOVIE_ID


def test_junk_is_refused():
    for bad in (None, '', '-1', 'plugin://plugin.video.jellyfin/?id=x',
                MOVIE_ID[:-1], MOVIE_ID + 'a', 'z' * 32):
        assert pt.normalize_item_id(bad) is None


# -- lookup_jellyfin_id -------------------------------------------------------

def test_movie_and_episode_share_a_kodi_id_but_resolve_apart(tmp_path):
    # kodi_id 2 exists as a movie AND an episode (separate Kodi tables), so
    # media_type must be part of the key or movies would claim episodes.
    db = make_db(tmp_path)
    assert pt.lookup_jellyfin_id(db, 2, 'movie') == MOVIE_ID
    assert pt.lookup_jellyfin_id(db, 2, 'episode') == EPISODE_ID


def test_dbid_arrives_as_infolabel_string(tmp_path):
    # The fallback path hands DBID over as the string InfoLabel gives.
    db = make_db(tmp_path)
    assert pt.lookup_jellyfin_id(db, '2', 'movie') == MOVIE_ID


def test_unsynced_item_is_none(tmp_path):
    assert pt.lookup_jellyfin_id(make_db(tmp_path), 999, 'movie') is None


def test_containers_never_resolve(tmp_path):
    # A season row exists for kodi_id 2, but only movie/episode may play.
    db = make_db(tmp_path)
    assert pt.lookup_jellyfin_id(db, 2, 'season') is None
    assert pt.lookup_jellyfin_id(db, 2, 'tvshow') is None
    assert pt.lookup_jellyfin_id(db, 2, '') is None


def test_bad_dbid_is_none(tmp_path):
    db = make_db(tmp_path)
    for bad in (None, '', '-1', 0, 'abc'):
        assert pt.lookup_jellyfin_id(db, bad, 'movie') is None


def test_missing_db_is_none_and_not_created(tmp_path):
    path = str(tmp_path / 'nope.db')
    assert pt.lookup_jellyfin_id(path, 2, 'movie') is None
    assert not os.path.exists(path)  # mode=ro must never create it


# -- resolve_item_id ----------------------------------------------------------

def test_property_wins_over_database(tmp_path):
    db = make_db(tmp_path)
    assert pt.resolve_item_id(EPISODE_ID, 2, 'movie', db) == EPISODE_ID


def test_bad_property_falls_back_to_database(tmp_path):
    db = make_db(tmp_path)
    assert pt.resolve_item_id('', 2, 'movie', db) == MOVIE_ID
    assert pt.resolve_item_id('not-an-id', 2, 'episode', db) == EPISODE_ID


def test_nothing_resolves_to_none(tmp_path):
    assert pt.resolve_item_id('', -1, 'movie', str(tmp_path / 'nope.db')) is None


# -- parse_start --------------------------------------------------------------

def test_started_ok():
    ok, first, err = pt.parse_start(200, '{"stage":"waking","seq":1}')
    assert ok and first['stage'] == 'waking' and err is None


def test_busy_409_surfaces_the_server_message():
    ok, first, err = pt.parse_start(
        409, '{"error":"already handing a playback to the TV, give it a moment"}')
    assert not ok and first is None and 'give it a moment' in err


def test_unconfigured_503_surfaces_the_server_message():
    ok, _, err = pt.parse_start(503, '{"error":"TV control is not configured on the box (tv.json missing)"}')
    assert not ok and 'not configured' in err


def test_junk_body_becomes_a_generic_message():
    ok, _, err = pt.parse_start(502, '<html>bad gateway</html>')
    assert not ok and '502' in err
    ok, _, err = pt.parse_start(200, '[]')
    assert not ok and '200' in err


# -- message_for --------------------------------------------------------------

def test_stage_messages():
    assert pt.message_for({'stage': 'waking'}) == 'Waking the TV'
    assert pt.message_for({'stage': 'playing'}) == 'Playing on TV'
    assert pt.message_for({'stage': 'playing', 'item': {'name': 'Dune'}}) == \
        'Playing on TV: Dune'


def test_failed_message_carries_the_server_error():
    msg = pt.message_for({'stage': 'failed', 'failedStage': 'waking',
                          'error': 'the TV never answered'})
    assert msg == 'Failed: the TV never answered'
    assert pt.message_for({'stage': 'failed'}) == 'Failed: unknown error'


def test_no_em_dashes_anywhere_user_visible():
    # Donnie's rule: no em dashes in copy. Covers every stage text and the
    # source of both addon files.
    for text in pt.STAGE_TEXT.values():
        assert '—' not in text
    addon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                             'kodi-addons', 'context.couch.playontv')
    for name in ('playontv.py', 'context.py', 'addon.xml'):
        with open(os.path.join(addon_dir, name), encoding='utf-8') as f:
            assert '—' not in f.read(), name


# -- follow_stages ------------------------------------------------------------

class Script:
    """A scripted server: fetch(seq) pops the next snapshot."""

    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.seqs_seen = []

    def fetch(self, seq):
        self.seqs_seen.append(seq)
        return self.snapshots.pop(0) if self.snapshots else None


class Notes:
    def __init__(self):
        self.lines = []

    def __call__(self, message, error=False):
        self.lines.append((message, error))


def test_happy_path_notifies_each_stage_once():
    script = Script([
        {'stage': 'launching', 'seq': 2},
        {'stage': 'connecting', 'seq': 3},
        {'stage': 'playing', 'seq': 4, 'item': {'name': 'Dune'}},
    ])
    notes = Notes()
    final = pt.follow_stages({'stage': 'waking', 'seq': 1}, script.fetch, notes)
    assert final == 'playing'
    assert [m for m, _ in notes.lines] == [
        'Waking the TV', 'Opening Jellyfin on the TV',
        'Waiting for the TV to start playback', 'Playing on TV: Dune']
    assert not any(err for _, err in notes.lines)
    assert script.seqs_seen == [1, 2, 3]  # long-polls with the seq it last saw


def test_longpoll_timeout_repeats_do_not_renotify():
    # A 25s server-side timeout answers with the SAME stage and seq.
    same = {'stage': 'waking', 'seq': 1}
    script = Script([same, same, {'stage': 'playing', 'seq': 2}])
    notes = Notes()
    final = pt.follow_stages(same, script.fetch, notes)
    assert final == 'playing'
    assert [m for m, _ in notes.lines] == ['Waking the TV', 'Playing on TV']


def test_failed_stage_is_final_and_marked_error():
    script = Script([
        {'stage': 'failed', 'seq': 2, 'failedStage': 'launching',
         'error': 'Jellyfin app never appeared'},
    ])
    notes = Notes()
    final = pt.follow_stages({'stage': 'waking', 'seq': 1}, script.fetch, notes)
    assert final == 'failed'
    assert notes.lines[-1] == ('Failed: Jellyfin app never appeared', True)


def test_network_loss_gives_up_after_three_misses():
    script = Script([])  # every fetch answers None
    notes = Notes()
    final = pt.follow_stages({'stage': 'waking', 'seq': 1}, script.fetch, notes)
    assert final == 'lost'
    assert len(script.seqs_seen) == 3
    assert notes.lines[-1] == ('Lost contact with the couch server', True)


def test_one_miss_then_recovery_continues():
    script = Script([None, {'stage': 'playing', 'seq': 2}])
    notes = Notes()
    final = pt.follow_stages({'stage': 'waking', 'seq': 1}, script.fetch, notes)
    assert final == 'playing'


def test_deadline_stops_a_stuck_handoff():
    clock = iter(range(0, 10000, 100)).__next__  # each call is +100s
    same = {'stage': 'connecting', 'seq': 5}
    script = Script([same] * 50)
    notes = Notes()
    final = pt.follow_stages(same, script.fetch, notes,
                             clock=clock, max_seconds=180)
    assert final == 'connecting'
    assert len(script.seqs_seen) <= 3


def test_empty_first_snapshot_does_not_crash():
    notes = Notes()
    final = pt.follow_stages({}, Script([]).fetch, notes)
    assert final == 'lost'

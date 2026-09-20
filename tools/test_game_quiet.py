#!/usr/bin/env python3
"""Tests for tools/game-quiet, the session-long hush over torrents and whisper.

NOTHING here touches the live box. qBittorrent is a stdlib http.server on an
ephemeral port that speaks whichever WebAPI dialect the test asks for, and
systemctl is a stub script on PATH that writes its arguments to a file under
tmp_path. The state file, the log and the .env are all tmp_path paths handed
over via the tool's env seams, so a failing test cannot pause a real torrent,
stop a real unit or leave anything in /tmp.

The two properties worth most of this file:

  * `off` restores EXACTLY the set `on` recorded, so a torrent Donnie paused by
    hand beforehand is still paused afterwards. The fake server records every
    hash it is handed, and the tests assert on that recording rather than on
    our own log lines;
  * nothing here ever exits non-zero except a mistyped command. This tool sits
    on the game-launch path, and half the tests below are a dead qBittorrent,
    a missing password or a 404 from the wrong dialect, each of which must
    still be exit 0.

Run:  couchd/.venv/bin/python -m pytest tools/test_game_quiet.py -q
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'game-quiet')

PASSWORD = 'not-the-real-one'
USER = 'admin'
HASHES = ['aaaa1111', 'bbbb2222', 'cccc3333']


def load():
    """Import the tool for the pure-logic tests. Importing it runs no I/O."""
    if not os.path.exists(TOOL):
        pytest.skip('tools/game-quiet not present')
    loader = importlib.machinery.SourceFileLoader('game_quiet_under_test', TOOL)
    spec = importlib.util.spec_from_loader('game_quiet_under_test', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def gq():
    return load()


# =========================================================================
# the fake qBittorrent
# =========================================================================
class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_a):
        pass                                        # no server noise in pytest -q

    # -- helpers --------------------------------------------------------
    def _send(self, code, body=b'', headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        if code != 204:                             # a 204 must carry no body,
            self.send_header('Content-Length', str(len(body)))   # not even a
        self.end_headers()                          # zero-length one
        if body:
            self.wfile.write(body)

    def _authed(self):
        cookie = self.headers.get('Cookie') or ''
        if self.server.login_style == 'nocookie':   # whitelisted: no cookie needed
            return True
        if 'SID=' in cookie or 'QBT_SID=' in cookie:
            return True
        self._send(403, b'Forbidden')
        return False

    def _form(self):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n).decode()
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

    # -- routes ---------------------------------------------------------
    def do_GET(self):
        s = self.server
        path, _, query = self.path.partition('?')
        q = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}
        s.calls.append(('GET', path, q))
        if path == '/api/v2/torrents/info':
            if not self._authed():
                return
            if q.get('filter') not in s.filters:
                return self._send(400, b'bad filter')
            body = json.dumps([{'hash': h, 'state': 'downloading'}
                               for h in s.running]).encode()
            return self._send(200, body, [('Content-Type', 'application/json')])
        self._send(404, b'Not Found')

    def do_POST(self):
        s = self.server
        form = self._form()
        s.calls.append(('POST', self.path, form))
        if self.path == '/api/v2/auth/login':
            if (form.get('username'), form.get('password')) != (s.user, s.password):
                return self._send(200, b'Fails.')   # a refusal is a 200, always
            if s.login_style == '204':
                # What THIS box actually answers: no body at all, the session
                # in the headers. See login_verdict.
                return self._send(204, b'', [('Set-Cookie', 'QBT_SID=fake; path=/')])
            if s.login_style == 'nocookie':
                return self._send(200, b'Ok.')      # inside an auth whitelist
            return self._send(200, b'Ok.', [('Set-Cookie', 'SID=fake; path=/')])
        want = {'halt': f'/api/v2/torrents/{s.dialect["halt"]}',
                'go': f'/api/v2/torrents/{s.dialect["go"]}'}
        for kind, route in want.items():
            if self.path == route:
                if not self._authed():
                    return
                hashes = [h for h in (form.get('hashes') or '').split('|') if h]
                s.acted.append((kind, hashes))
                if kind == 'halt':
                    s.running = [h for h in s.running if h not in hashes]
                else:
                    s.running += [h for h in hashes if h not in s.running]
                return self._send(200, b'Ok.')
        # Anything else, including the other dialect's verbs, is a 404 - which
        # is exactly what a real qBittorrent of the wrong major version does.
        self._send(404, b'Not Found')


class FakeQb:
    """A qBittorrent that speaks one dialect and remembers what it was told."""

    def __init__(self, running=(), dialect='pause', filters=('resumed',),
                 user=USER, password=PASSWORD, login_style='ok'):
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.httpd.running = list(running)
        self.httpd.login_style = login_style
        self.httpd.dialect = ({'halt': 'pause', 'go': 'resume'} if dialect == 'pause'
                              else {'halt': 'stop', 'go': 'start'})
        self.httpd.filters = tuple(filters)
        self.httpd.user, self.httpd.password = user, password
        self.httpd.calls = []
        self.httpd.acted = []
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return 'http://127.0.0.1:%d' % self.httpd.server_address[1]

    @property
    def acted(self):
        return self.httpd.acted

    @property
    def running(self):
        return self.httpd.running

    @property
    def calls(self):
        return self.httpd.calls

    def paused_hashes(self):
        return [h for kind, hs in self.acted if kind == 'halt' for h in hs]

    def resumed_hashes(self):
        return [h for kind, hs in self.acted if kind == 'go' for h in hs]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def qb():
    made = []

    def make(**kw):
        s = FakeQb(**kw)
        made.append(s)
        return s
    yield make
    for s in made:
        s.close()


# =========================================================================
# the fake jellyfin
# =========================================================================
class JfHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_a):
        pass

    def _send(self, code, body=b''):
        self.send_response(code)
        if code != 204:
            self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authed(self):
        auth = self.headers.get('Authorization') or ''
        if self.server.api_key and self.server.api_key in auth:
            return True
        self._send(401, b'Unauthorized')
        return False

    def do_GET(self):
        s = self.server
        s.calls.append(('GET', self.path))
        if self.path == '/ScheduledTasks':
            if not self._authed():
                return
            body = json.dumps(s.tasks).encode()
            return self._send(200, body)
        self._send(404, b'Not Found')

    def _running(self, method):
        s = self.server
        s.calls.append((method, self.path))
        prefix = '/ScheduledTasks/Running/'
        if not self.path.startswith(prefix):
            return self._send(404, b'Not Found')
        if not self._authed():
            return
        task_id = urllib.parse.unquote(self.path[len(prefix):])
        if method == 'DELETE':
            s.stopped.append(task_id)
            for t in s.tasks:
                if t.get('Id') == task_id:
                    t['State'] = 'Idle'
        else:
            s.started.append(task_id)
            for t in s.tasks:
                if t.get('Id') == task_id:
                    t['State'] = 'Running'
        self._send(204)

    def do_DELETE(self):
        self._running('DELETE')

    def do_POST(self):
        self._running('POST')


class FakeJellyfin:
    """A Jellyfin that has some tasks and remembers what it was told to do."""

    def __init__(self, tasks=(), api_key='jf-key'):
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), JfHandler)
        self.httpd.tasks = [dict(t) for t in tasks]
        self.httpd.api_key = api_key
        self.httpd.calls = []
        self.httpd.stopped = []
        self.httpd.started = []
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return 'http://127.0.0.1:%d' % self.httpd.server_address[1]

    @property
    def stopped(self):
        return self.httpd.stopped

    @property
    def started(self):
        return self.httpd.started

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def jf():
    made = []

    def make(**kw):
        s = FakeJellyfin(**kw)
        made.append(s)
        return s
    yield make
    for s in made:
        s.close()


RUNNING_TASK = {'Id': 'seg-1', 'Name': 'Detect and Analyze Media Segments',
                'State': 'Running'}
IDLE_TASK = {'Id': 'lib-1', 'Name': 'Scan Media Library', 'State': 'Idle'}


# =========================================================================
# the fake systemctl
# =========================================================================
STUB = """#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
with open(os.environ['GQ_STUB_LOG'], 'a') as f:
    f.write(' '.join(args) + '\\n')
statefile = os.environ['GQ_STUB_STATE']
with open(statefile) as f:
    cur = f.read().strip()
if 'is-active' in args:
    print(cur)
    sys.exit(0 if cur == 'active' else 3)
if 'stop' in args:
    open(statefile, 'w').write('inactive')
    sys.exit(0)
if 'start' in args:
    open(statefile, 'w').write('active')
    sys.exit(0)
sys.exit(1)
"""


class Box:
    """One isolated console: tmp paths, a PATH with our systemctl on it."""

    def __init__(self, tmp_path, url=None, password=PASSWORD, user=None,
                 whisper='active', env_lines=None, jf_url=None, jf_key='jf-key'):
        self.tmp = tmp_path
        self.state = tmp_path / 'game-quiet.state'
        self.log = tmp_path / 'game-quiet.log'
        self.envfile = tmp_path / 'dot-env'
        self.stub_log = tmp_path / 'systemctl.calls'
        self.stub_state = tmp_path / 'unit.state'
        self.stub_state.write_text(whisper)
        self.stub_log.write_text('')

        if env_lines is None:
            env_lines = []
            if url:
                env_lines.append(f'QBITTORRENT_URL={url}')
            if user:
                env_lines.append(f'QBITTORRENT_USER={user}')
            if password is not None:
                env_lines.append(f'QBITTORRENT_PASSWORD={password}')
            if jf_url:
                env_lines.append(f'JELLYFIN_URL={jf_url}')
                env_lines.append(f'JELLYFIN_API_KEY={jf_key}')
        self.envfile.write_text('\n'.join(env_lines) + '\n')

        bindir = tmp_path / 'bin'
        bindir.mkdir(exist_ok=True)
        stub = bindir / 'systemctl'
        stub.write_text(STUB)
        stub.chmod(0o755)
        self.bindir = bindir

    def env(self):
        return {
            'PATH': f'{self.bindir}:{os.environ.get("PATH", "/usr/bin:/bin")}',
            'HOME': str(self.tmp),                  # nothing may find the real ~
            'GAME_QUIET_STATE': str(self.state),
            'GAME_QUIET_LOG': str(self.log),
            'GAME_QUIET_ENV': str(self.envfile),
            'GAME_QUIET_UNIT': 'whisper-asr.service',
            'GQ_STUB_LOG': str(self.stub_log),
            'GQ_STUB_STATE': str(self.stub_state),
        }

    def run(self, *args):
        r = subprocess.run([sys.executable, TOOL, *args], capture_output=True,
                           text=True, env=self.env(), timeout=60)
        return r

    # -- what happened --------------------------------------------------
    def state_json(self):
        return json.loads(self.state.read_text())

    def systemctl_calls(self):
        return [ln for ln in self.stub_log.read_text().splitlines() if ln]

    def unit(self):
        return self.stub_state.read_text().strip()

    def logtext(self):
        return self.log.read_text() if self.log.exists() else ''


@pytest.fixture
def box(tmp_path):
    def make(**kw):
        return Box(tmp_path, **kw)
    return make


def assert_quiet_success(result):
    """Every path but a typo is exit 0. Asserted everywhere, because this is
    the property the launcher depends on."""
    assert result.returncode == 0, result.stderr


# =========================================================================
# pure logic
# =========================================================================
def test_env_parsing_quotes_comments_and_export(gq):
    env = gq.parse_env(
        '# a comment\n'
        '\n'
        'QBITTORRENT_USER=admin\n'
        'QBITTORRENT_PASSWORD="hunter two"\n'
        "QBITTORRENT_URL='http://localhost:8080'\n"
        'export OTHER=thing\n'
        'RAGGED   =  spaced  \n'
        'NOT_A_LINE\n')
    assert env['QBITTORRENT_USER'] == 'admin'
    assert env['QBITTORRENT_PASSWORD'] == 'hunter two'
    assert env['QBITTORRENT_URL'] == 'http://localhost:8080'
    assert env['OTHER'] == 'thing'
    assert env['RAGGED'] == 'spaced'
    assert 'NOT_A_LINE' not in env


def test_env_keeps_a_password_that_merely_contains_quotes(gq):
    """Only a MATCHING surrounding pair is stripping, so a password with an
    apostrophe in it survives intact."""
    assert gq.parse_env("P=don't\n")['P'] == "don't"
    assert gq.parse_env('P="mid"dle"\n')['P'] == 'mid"dle'


def test_settings_defaults_and_the_required_password(gq):
    url, user, password = gq.qb_settings({'QBITTORRENT_PASSWORD': 'p'}, environ={})
    assert (url, user, password) == (gq.DEFAULT_URL, gq.DEFAULT_USER, 'p')
    with pytest.raises(gq.QuietError):
        gq.qb_settings({'QBITTORRENT_USER': 'admin'}, environ={})


def test_settings_prefer_a_real_environment_variable(gq):
    _url, _user, password = gq.qb_settings({'QBITTORRENT_PASSWORD': 'file'},
                                           environ={'QBITTORRENT_PASSWORD': 'env'})
    assert password == 'env'


def test_hashes_from_info_ignores_junk(gq):
    got = gq.hashes_from_info([{'hash': 'a'}, {'nope': 1}, 'string', {'hash': ''},
                               {'infohash_v1': 'b'}])
    assert got == ['a', 'b']
    with pytest.raises(gq.QuietError):
        gq.hashes_from_info({'not': 'a list'})


def test_verb_order_puts_the_recorded_dialect_first(gq):
    assert gq.verb_order('halt') == [('pause', 'pause'), ('stop', 'stop')]
    assert gq.verb_order('go', 'stop') == [('stop', 'start'), ('pause', 'resume')]
    assert gq.verb_order('go', 'nonsense') == [('pause', 'resume'), ('stop', 'start')]


@pytest.mark.parametrize('code, body, cookies, why', [
    (204, '', ['QBT_SID'], 'this box: 204, empty body, cookie'),
    (200, '', ['QBT_SID'], '2xx with a cookie and nothing else'),
    (200, 'Ok.', ['SID'], 'the classic dialect'),
    (200, 'Ok.', [], 'no cookie, but it said Ok (auth whitelist)'),
    (204, '', ['qbt_sid'], 'cookie name case is not ours to rely on'),
])
def test_login_verdict_accepts_every_way_of_saying_yes(gq, code, body, cookies, why):
    assert gq.login_verdict(code, body, cookies) is None, why


@pytest.mark.parametrize('code, body, cookies, expect', [
    (200, 'Fails.', ['SID'], 'refused'),       # a cookie cannot rescue a Fails.
    (200, 'Fails.', [], 'refused'),
    (204, '', [], 'no session cookie'),        # 2xx alone proves nothing
    (200, '', ['OTHER'], 'no session cookie'),
])
def test_login_verdict_refusals(gq, code, body, cookies, expect):
    problem = gq.login_verdict(code, body, cookies)
    assert problem and expect in problem


def test_describe_reads_like_a_sentence(gq):
    assert gq.describe(None) == 'nothing is quieted'
    line = gq.describe({'when': '12:00', 'torrents': {'hashes': ['a', 'b']},
                        'whisper': {'unit': 'whisper-asr.service', 'stopped': True}})
    assert line == 'quiet since 12:00: 2 torrents paused, whisper-asr.service stopped'
    assert 'nothing needed quieting' in gq.describe({'when': '12:00'})


# =========================================================================
# on
# =========================================================================
def test_on_pauses_and_records_exactly_the_running_set(box, qb):
    server = qb(running=HASHES)
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))

    assert server.paused_hashes() == HASHES
    st = b.state_json()
    assert st['torrents']['hashes'] == HASHES
    assert st['torrents']['vocab'] == 'pause'
    assert st['whisper']['stopped'] is True
    assert b.unit() == 'inactive'


def test_on_with_no_running_torrents_records_an_empty_set(box, qb):
    server = qb(running=[])
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    assert server.paused_hashes() == []
    assert b.state_json()['torrents']['hashes'] == []
    assert 'no torrents were running' in b.logtext()


def test_double_on_keeps_the_first_restore_set(box, qb):
    """The trap this guards: a second `on` that re-reads the running torrents
    would record an empty list (we just paused them all) and `off` would then
    resume nothing at all."""
    server = qb(running=HASHES)
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    first = b.state_json()

    assert_quiet_success(b.run('on'))
    assert b.state_json() == first
    assert server.paused_hashes() == HASHES           # not paused a second time
    assert 'already quiet' in b.logtext()


def test_the_204_login_dialect_this_box_actually_speaks(box, qb):
    """Live integration, 22 Aug: our qBittorrent answers the login with HTTP
    204, an empty body and QBT_SID in the headers. Reading the body alone
    called that a refusal and quieted nothing."""
    server = qb(running=HASHES, login_style='204')
    b = box(url=server.url)
    r = b.run('on')
    assert_quiet_success(r)
    assert 'login refused' not in r.stderr
    assert server.paused_hashes() == HASHES
    assert b.state_json()['torrents']['hashes'] == HASHES


def test_the_204_dialect_round_trips_through_off(box, qb):
    server = qb(running=HASHES, login_style='204')
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    assert_quiet_success(b.run('off'))
    assert server.resumed_hashes() == HASHES
    assert not b.state.exists()


def test_a_whitelisted_webui_without_a_cookie_still_works(box, qb):
    server = qb(running=HASHES, login_style='nocookie')
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    assert server.paused_hashes() == HASHES


def test_on_survives_a_missing_password(box, qb):
    server = qb(running=HASHES)
    b = box(url=server.url, password=None)
    r = b.run('on')
    assert_quiet_success(r)
    assert 'QBITTORRENT_PASSWORD is not set' in r.stderr
    assert server.paused_hashes() == []                # never even tried
    st = b.state_json()
    assert st['torrents']['hashes'] == []
    assert 'QBITTORRENT_PASSWORD' in st['torrents']['error']
    # the other half still happened
    assert st['whisper']['stopped'] is True


def test_on_survives_a_wrong_password(box, qb):
    server = qb(running=HASHES)
    b = box(url=server.url, password='wrong')
    r = b.run('on')
    assert_quiet_success(r)
    assert 'login refused' in r.stderr
    assert server.paused_hashes() == []
    assert b.state_json()['whisper']['stopped'] is True


def test_on_survives_an_unreachable_qbittorrent(box, qb):
    """The one that matters most: qBittorrent's container is down and a game
    still has to launch."""
    server = qb(running=HASHES)
    dead = server.url
    server.close()
    b = box(url=dead)
    r = b.run('on')
    assert_quiet_success(r)
    assert 'torrents not quieted' in r.stderr
    assert b.logtext().strip() != ''
    assert b.state_json()['torrents']['hashes'] == []
    assert b.state_json()['whisper']['stopped'] is True


def test_on_leaves_whisper_alone_when_it_is_not_running(box, qb):
    server = qb(running=[])
    b = box(url=server.url, whisper='inactive')
    assert_quiet_success(b.run('on'))
    assert b.state_json()['whisper']['stopped'] is False
    assert [c for c in b.systemctl_calls() if 'stop' in c] == []


# =========================================================================
# off
# =========================================================================
def test_off_resumes_exactly_what_on_paused(box, qb):
    """Two torrents Donnie paused by hand before the session are not in the
    running set, so they must not come back."""
    server = qb(running=HASHES)
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    assert_quiet_success(b.run('off'))

    assert server.resumed_hashes() == HASHES
    assert sorted(server.running) == sorted(HASHES)
    assert b.unit() == 'active'
    assert not b.state.exists()


def test_off_without_a_state_file_does_nothing(box, qb):
    server = qb(running=HASHES)
    b = box(url=server.url)
    r = b.run('off')
    assert_quiet_success(r)
    assert server.acted == []
    assert b.systemctl_calls() == []
    assert 'nothing was quieted' in r.stderr


def test_off_starts_whisper_only_if_we_stopped_it(box, qb):
    server = qb(running=[])
    b = box(url=server.url, whisper='inactive')
    assert_quiet_success(b.run('on'))
    assert_quiet_success(b.run('off'))
    assert b.unit() == 'inactive'
    assert [c for c in b.systemctl_calls() if c.startswith('start')] == []


def test_off_removes_the_state_file_even_when_the_restore_fails(box, qb):
    server = qb(running=HASHES)
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    server.close()                                   # qBittorrent dies mid-session

    r = b.run('off')
    assert_quiet_success(r)
    assert not b.state.exists()
    assert 'NOT resumed' in r.stderr
    assert b.unit() == 'active'                      # the other half still restored


def test_off_ignores_a_corrupt_state_file_but_still_clears_it(box, qb):
    server = qb(running=HASHES)
    b = box(url=server.url)
    b.state.write_text('{ this is not json')
    r = b.run('off')
    assert_quiet_success(r)
    assert not b.state.exists()
    assert server.acted == []


# =========================================================================
# the two dialects
# =========================================================================
def test_a_five_x_qbittorrent_is_found_by_the_404_and_recorded(box, qb):
    server = qb(running=HASHES, dialect='stop')
    b = box(url=server.url)
    r = b.run('on')
    assert_quiet_success(r)

    assert server.paused_hashes() == HASHES
    assert b.state_json()['torrents']['vocab'] == 'stop'
    assert '/api/v2/torrents/pause is not there (404)' in r.stderr
    posts = [p for _m, p, _f in server.calls if p.endswith('/stop')]
    assert posts == ['/api/v2/torrents/stop']


def test_off_speaks_the_recorded_dialect_first(box, qb):
    server = qb(running=HASHES, dialect='stop')
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    before = len(server.calls)
    assert_quiet_success(b.run('off'))

    assert server.resumed_hashes() == HASHES
    tried = [p for _m, p, _f in server.calls[before:]
             if p.startswith('/api/v2/torrents/')]
    assert tried == ['/api/v2/torrents/start']       # no wasted 404 on /resume


def test_a_rejected_resumed_filter_falls_back_to_running(box, qb):
    server = qb(running=HASHES, dialect='stop', filters=('running',))
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    assert b.state_json()['torrents']['hashes'] == HASHES
    filters = [q.get('filter') for m, p, q in server.calls
               if p == '/api/v2/torrents/info']
    assert filters == ['resumed', 'running']


# =========================================================================
# status and usage
# =========================================================================
def test_status_is_one_line_either_way(box, qb):
    server = qb(running=HASHES)
    b = box(url=server.url)
    r = b.run('status')
    assert_quiet_success(r)
    assert r.stdout.strip() == 'nothing is quieted'

    assert_quiet_success(b.run('on'))
    r = b.run('status')
    assert_quiet_success(r)
    assert len(r.stdout.strip().splitlines()) == 1
    assert '3 torrents paused' in r.stdout
    assert 'whisper-asr.service stopped' in r.stdout


def test_status_changes_nothing(box, qb):
    server = qb(running=HASHES)
    b = box(url=server.url)
    assert_quiet_success(b.run('on'))
    calls, units = len(server.calls), b.systemctl_calls()
    assert_quiet_success(b.run('status'))
    assert len(server.calls) == calls
    assert b.systemctl_calls() == units
    assert b.state.exists()


@pytest.mark.parametrize('argv', [[], ['wibble'], ['on', 'now'], ['off', '--force']])
def test_bad_usage_exits_two(box, argv):
    b = box()
    assert b.run(*argv).returncode == 2


def test_help_exits_zero(box):
    b = box()
    r = b.run('--help')
    assert r.returncode == 0
    assert 'game-quiet on' in r.stdout


# =========================================================================
# jellyfin
# =========================================================================
def test_on_stops_running_jellyfin_tasks_and_records_them(tmp_path, qb, jf):
    server = qb(running=HASHES)
    media = jf(tasks=[RUNNING_TASK, IDLE_TASK])
    box = Box(tmp_path, url=server.url, jf_url=media.url)
    r = box.run('on')
    assert r.returncode == 0
    assert media.stopped == ['seg-1'], 'only the RUNNING task is stopped'
    recorded = box.state_json()['jellyfin']['stopped']
    assert [t['id'] for t in recorded] == ['seg-1']
    assert recorded[0]['name'] == 'Detect and Analyze Media Segments'


def test_off_restarts_exactly_the_recorded_tasks(tmp_path, qb, jf):
    server = qb(running=HASHES)
    media = jf(tasks=[RUNNING_TASK, IDLE_TASK])
    box = Box(tmp_path, url=server.url, jf_url=media.url)
    assert box.run('on').returncode == 0
    assert box.run('off').returncode == 0
    assert media.started == ['seg-1'], 'the stopped task is put back, nothing else'
    assert not box.state.exists()


def test_no_api_key_leaves_jellyfin_alone_and_still_exits_zero(tmp_path, qb, jf):
    server = qb(running=HASHES)
    media = jf(tasks=[RUNNING_TASK])
    box = Box(tmp_path, url=server.url)          # no jf_url: no key in .env
    r = box.run('on')
    assert r.returncode == 0
    assert media.stopped == []
    state = box.state_json()
    assert state['jellyfin'] == {'stopped': []}
    assert 'error' not in state['jellyfin'], 'an unconfigured box is not a failure'
    assert 'JELLYFIN_API_KEY is not set' in r.stderr


def test_dead_jellyfin_is_a_recorded_error_and_torrents_still_pause(tmp_path, qb):
    server = qb(running=HASHES)
    box = Box(tmp_path, url=server.url, jf_url='http://127.0.0.1:1')
    r = box.run('on')
    assert r.returncode == 0
    assert server.paused_hashes() == HASHES, 'a dead Jellyfin must not cost the torrents'
    state = box.state_json()
    assert state['jellyfin'].get('error'), 'a key that goes nowhere IS a failure'


def test_status_mentions_stopped_jellyfin_tasks(tmp_path, qb, jf):
    server = qb(running=HASHES)
    media = jf(tasks=[RUNNING_TASK])
    box = Box(tmp_path, url=server.url, jf_url=media.url)
    assert box.run('on').returncode == 0
    r = box.run('status')
    assert '1 Jellyfin task stopped' in r.stdout


def test_running_tasks_from_is_defensive(gq):
    with pytest.raises(gq.QuietError):
        gq.running_tasks_from({'not': 'a list'})
    tasks = gq.running_tasks_from([
        RUNNING_TASK, IDLE_TASK, 'garbage', {'State': 'Running'},   # no Id
        {'Id': ' pad ', 'Name': None, 'State': 'Running'},
    ])
    assert tasks == [
        {'id': 'seg-1', 'name': 'Detect and Analyze Media Segments'},
        {'id': 'pad', 'name': 'unnamed task'},
    ]

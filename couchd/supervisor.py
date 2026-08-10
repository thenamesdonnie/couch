#!/usr/bin/env python3
"""The supervisor wire - stage 2's input process talking to stage 1's daemon.

ONE file defines the whole thing: the message grammar, the uid check, the
listening end (couchd) and the connecting end (inputproc). Two files defining
half a protocol each is how a wire drifts.

    inputproc  --connect-->  ~/couch/shadow/couchd.sock  <--listen--  couchd

THE LOAD-BEARING DECISION: the wire carries OBSERVATIONS, NOT DECISIONS.

inputproc sends the raw BTN_MODE press and release events with their KERNEL
timestamps, and nothing else about them. couchd keeps its own PressTracker and
its own state machine and classifies them itself, exactly as it does today
from evdev. It would have been less code to send "ps-hold" down the wire and
have couchd act on it - and it would have quietly destroyed the flip
machinery:

  * SR4 says both stacks must decide identically. If couchd consumed
    inputproc's classification, couchd would no longer be deciding at all: it
    would be a slave to the input process, the two could not disagree even in
    principle, and the shadow corpus the morning differ reads would be
    comparing a stack against itself. Sending timestamps keeps both stacks
    running the same arithmetic over the same input, which is the property the
    whole cutover rests on.
  * it also dissolves the name-filter problem for free. couchd's PadObserver
    finds devices by the name "DualSense Wireless Controller", and once
    inputproc grabs the pad the only thing on the box called that is hidden
    while what IS visible is called "Microsoft X-Box 360 pad". Over this wire
    couchd never needs to see the device at all, only its events.

Transport, in one paragraph: AF_UNIX SOCK_STREAM, newline-delimited JSON, one
object per line, no framing beyond the newline and no replies. couchd LISTENS
(it is the long-lived one, and it must be reachable before inputproc starts),
inputproc CONNECTS and reconnects on its own with backoff. Every line is
validated on receipt: a malformed one is counted and skipped, never fatal - a
supervisor that can be crashed by a bad line is a supervisor an input process
can kill.

SR1 (the uid check): a connection is accepted only from ds2000 or from the
couchd-input service user, resolved BY NAME at runtime through the passwd
database - never a hardcoded number, because uids for system users are
allocated at install time and differ per box.

SR7 (never block the input fast path): the sending end is a BOUNDED queue plus
a sender thread. A full queue DROPS and counts. An input process must never
stall because a supervisor is slow, wedged or gone - a dropped observation
costs couchd one gesture, a blocked write costs the room its controller.
"""
import errno
import json
import math
import os
import pwd
import queue
import socket
import struct
import threading
import time

HOME = os.path.expanduser('~')
SHADOW_DIR = os.environ.get('COUCHD_SHADOW_DIR',
                            os.path.join(HOME, 'couch', 'shadow'))
SOCK_NAME = 'couchd.sock'

PROTOCOL_VERSION = 1

# Who may drive the wire. NAMES, resolved through passwd at runtime: the
# couchd-input uid is whatever useradd --system picked on this box, and a
# number baked in here would be wrong on the next one (and, worse, might be
# RIGHT for some unrelated account).
DESKTOP_USER = 'ds2000'
SERVICE_USER = 'couchd-input'
ALLOWED_USERS = (DESKTOP_USER, SERVICE_USER)

# The socket file's mode. ~/couch/shadow carries a u:couchd-input ACL
# (stage2/INSTALL.md step 5) and a DEFAULT ACL granting it rw on anything
# created there - but a POSIX ACL's mask is taken from the create mode's GROUP
# bits, so a socket bound under the usual 0022 umask (0755, group r-x) would
# mask that rw entry down to r-- and the service user's connect() would get
# EACCES. Bind under 0007 so the mask lands rw, then chmod to exactly 0660.
SOCK_UMASK = 0o007
SOCK_MODE = 0o660

# Queue sizes. The send side is small on purpose: 256 pending observations is
# already ~a minute of furious button mashing, and anything beyond it is a
# supervisor that is not coming back, in which case the right answer is to drop
# and say so rather than to grow.
SEND_QUEUE = 256
RECV_QUEUE = 4096
MAX_LINE = 8192              # a longer "line" is garbage or an attack, not JSON
RECONNECT_MIN = 0.25
RECONNECT_MAX = 5.0
ACCEPT_TIMEOUT = 0.5         # how often the accept thread checks for stop
READ_TIMEOUT = 0.5


class ProtocolError(ValueError):
    """A line that is not a message. Always caught; never propagated."""


# =========================================================================
# the grammar
# =========================================================================
def _num(msg, key, required=True, default=None):
    v = msg.get(key, default)
    if v is None:
        if required:
            raise ProtocolError(f'{key} missing')
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ProtocolError(f'{key} is not a number: {v!r}')
    if not math.isfinite(v):
        raise ProtocolError(f'{key} is not finite: {v!r}')
    return float(v)


def _int(msg, key, required=True, default=None):
    v = msg.get(key, default)
    if v is None:
        if required:
            raise ProtocolError(f'{key} missing')
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise ProtocolError(f'{key} is not an integer: {v!r}')
    return v


def _bool(msg, key, default=None):
    v = msg.get(key, default)
    if v is None:
        return None
    if not isinstance(v, bool):
        raise ProtocolError(f'{key} is not a boolean: {v!r}')
    return v


def _str(msg, key, choices=None, required=True, default=None):
    v = msg.get(key, default)
    if v is None:
        if required:
            raise ProtocolError(f'{key} missing')
        return None
    if not isinstance(v, str):
        raise ProtocolError(f'{key} is not a string: {v!r}')
    if choices is not None and v not in choices:
        raise ProtocolError(f'{key}={v!r} is not one of {sorted(choices)}')
    return v


def _v_press(msg):
    """One raw BTN_MODE event. The ONLY input-carrying message there is.

    `value` 2 (autorepeat) is passed through rather than filtered: the kernel
    does not autorepeat BTN_*, but if something ever does, the consumer's own
    PressTracker.feed() already ignores it, and filtering here would be this
    wire making a decision.
    """
    out = {'value': _int(msg, 'value'), 'kernel_t': _num(msg, 'kernel_t')}
    if out['value'] not in (0, 1, 2):
        raise ProtocolError(f"value={out['value']} is not 0, 1 or 2")
    return out


def _v_pad(msg):
    """The physical pad appeared or went away, as the owner of it sees it."""
    return {'state': _str(msg, 'state', {'attached', 'detached'}),
            'node': _str(msg, 'node', required=False),
            'why': _str(msg, 'why', required=False),
            'grabbed': _bool(msg, 'grabbed')}


def _v_hello(msg):
    """Who is on the other end, and does it actually own the pad."""
    pid = _int(msg, 'pid')
    if pid <= 0:
        raise ProtocolError(f'pid={pid} is not a pid')
    return {'pid': pid, 'version': _int(msg, 'version', default=PROTOCOL_VERSION),
            'owns_input': _bool(msg, 'owns_input', default=False),
            'sender': _str(msg, 'sender', required=False)}


def _v_health(msg):
    """The sender's own health tick - above all its DROP count, which is the
    only way this end can learn that observations went missing."""
    drops = _int(msg, 'drops', default=0)
    if drops < 0:
        raise ProtocolError(f'drops={drops} is negative')
    return {'drops': drops, 'owns_input': _bool(msg, 'owns_input'),
            'degraded': _str(msg, 'degraded', required=False),
            'state': _str(msg, 'state', required=False)}


VALIDATORS = {'press': _v_press, 'pad': _v_pad, 'hello': _v_hello,
              'health': _v_health}
KINDS = tuple(sorted(VALIDATORS))


def encode(kind, **fields):
    """One message -> one line of bytes, newline included.

    Validated on the way OUT as well as on the way in, against the same
    table. A sender free to emit something the receiver will refuse is a
    silent data loss: the bytes go down the wire, the far end counts a
    malformed line, and nobody on this side ever learns the observation did
    not arrive.
    """
    if kind not in VALIDATORS:
        raise ProtocolError(f'unknown kind {kind!r}')
    msg = dict(fields)
    msg['kind'] = kind
    msg.setdefault('v', PROTOCOL_VERSION)
    msg.setdefault('t', time.time())
    VALIDATORS[kind](msg)
    return (json.dumps(msg, default=str) + '\n').encode('utf-8')


def decode(line):
    """One line -> a validated message dict, or ProtocolError.

    Unknown extra keys are KEPT rather than rejected: a newer sender adding a
    field must not take the wire down with an older receiver. An unknown
    `kind`, a wrong `v`, or a required field of the wrong type is refused,
    because those are the shapes that would make the receiver act on nonsense.
    """
    if isinstance(line, (bytes, bytearray)):
        try:
            line = line.decode('utf-8')
        except UnicodeDecodeError as e:
            raise ProtocolError(f'not utf-8: {e}')
    line = line.strip()
    if not line:
        raise ProtocolError('empty line')
    try:
        msg = json.loads(line)
    except ValueError as e:
        raise ProtocolError(f'not JSON: {e}')
    if not isinstance(msg, dict):
        raise ProtocolError(f'not an object: {type(msg).__name__}')
    kind = msg.get('kind')
    if kind not in VALIDATORS:
        raise ProtocolError(f'unknown kind {kind!r}')
    version = msg.get('v', PROTOCOL_VERSION)
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f'protocol version {version!r} != {PROTOCOL_VERSION}')
    out = dict(msg)
    out.update(VALIDATORS[kind](msg))
    out['kind'] = kind
    out['v'] = PROTOCOL_VERSION
    out['t'] = _num(msg, 't', required=False, default=time.time())
    return out


# =========================================================================
# SR1: who is on the other end
# =========================================================================
def allowed_uids(names=ALLOWED_USERS):
    """{name: uid} for the users allowed to connect, resolved NOW by name.

    A name that does not exist on this box is simply absent - which is the
    correct state before stage 2's install has created couchd-input, and it
    fails CLOSED (that user cannot connect because there is no such user).
    """
    out = {}
    for name in names:
        try:
            out[name] = pwd.getpwnam(name).pw_uid
        except KeyError:
            continue
    return out


def peer_credentials(sock):
    """(pid, uid, gid) of the process on the other end, from the kernel.

    SO_PEERCRED is taken at connect() time by the kernel itself, so it cannot
    be spoofed by the peer the way anything it TELLS us could be.
    """
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                          struct.calcsize('3i'))
    pid, uid, gid = struct.unpack('3i', raw)
    return pid, uid, gid


def peer_allowed(uid, names=ALLOWED_USERS):
    """(ok, detail) for one peer uid. Anything unknown is refused."""
    permitted = allowed_uids(names)
    for name, u in permitted.items():
        if u == uid:
            return True, name
    try:
        who = pwd.getpwuid(uid).pw_name
    except KeyError:
        who = str(uid)
    named = ', '.join('%s=%s' % (n, u) for n, u in sorted(permitted.items()))
    return False, ('uid %s (%s) is not one of %s' %
                   (uid, who, named or '(no permitted user exists on this box)'))


def default_path(directory=None):
    return os.path.join(directory or SHADOW_DIR, SOCK_NAME)


# =========================================================================
# couchd's end: listen, validate, queue
# =========================================================================
class SupervisorListener:
    """The listening half. Threads in, messages out through a queue.

    Deliberately NOT asyncio even though couchd is: the daemon's loop must be
    able to ignore this wire completely for a whole pass without anything
    backing up into the input process, and a thread plus a bounded queue says
    that in less code than a protocol handler inside the event loop. The main
    loop drains the queue on its tick and never touches a socket.
    """

    def __init__(self, path=None, allow_users=ALLOWED_USERS, on_log=None,
                 maxsize=RECV_QUEUE):
        self.path = path or default_path()
        self.allow_users = tuple(allow_users)
        self.on_log = on_log
        self.q = queue.Queue(maxsize)
        self.listening = False
        self.error = None
        self.connections = 0        # accepted, ever
        self.rejected = 0           # SR1 refusals
        self.malformed = 0          # lines that did not decode
        self.dropped = 0            # inbound queue overflow (our own fault)
        self.received = 0
        self.peers = {}             # id(conn) -> {'pid','uid','user','since'}
        self._sock = None
        self._threads = []
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------
    def _log(self, msg):
        if self.on_log is not None:
            self.on_log(f'supervisor: {msg}')

    def _stale_socket(self):
        """Is the socket file at self.path dead (nobody listening on it)?

        Unlinking blind would let a second daemon steal a live wire. Ask the
        socket itself instead: a refused connect is a corpse, a successful one
        is somebody else's listener and we must not touch it.
        """
        if not os.path.exists(self.path):
            return False, None
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.5)
        try:
            probe.connect(self.path)
        except OSError as e:
            if e.errno in (errno.ECONNREFUSED, errno.ENOENT):
                return True, None
            return False, e
        finally:
            probe.close()
        return False, 'another process is already listening there'

    def start(self):
        """Bind, listen, and start accepting. Never raises: a wire that cannot
        be opened is a degraded daemon, not a dead one."""
        stale, problem = self._stale_socket()
        if problem is not None:
            self.error = str(problem)
            self._log(f'NOT listening on {self.path}: {self.error}')
            return False
        if stale:
            try:
                os.unlink(self.path)
            except OSError as e:
                self.error = f'cannot remove stale socket: {e}'
                self._log(self.error)
                return False
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            old = os.umask(SOCK_UMASK)
            try:
                s.bind(self.path)
            finally:
                os.umask(old)
            os.chmod(self.path, SOCK_MODE)
            s.listen(4)
            s.settimeout(ACCEPT_TIMEOUT)
        except OSError as e:
            s.close()
            self.error = str(e)
            self._log(f'NOT listening on {self.path}: {e}')
            return False
        self._sock = s
        self.listening = True
        self.error = None
        t = threading.Thread(target=self._accept_loop, name='supervisor-accept',
                             daemon=True)
        t.start()
        self._threads.append(t)
        permitted = allowed_uids(self.allow_users)
        missing = [n for n in self.allow_users if n not in permitted]
        named = ', '.join('%s=%s' % (n, u) for n, u in sorted(permitted.items()))
        self._log('listening on %s (mode %s), accepting %s%s'
                  % (self.path, oct(SOCK_MODE), named or '(nobody)',
                     '; no such user: ' + ', '.join(missing) if missing else ''))
        return True

    def close(self):
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self.listening = False
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads = []
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)
        except OSError:
            pass

    # -- accepting --------------------------------------------------------
    def _accept_loop(self):
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                return
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return                  # the listening socket was closed
            self._admit(conn)

    def _admit(self, conn):
        try:
            pid, uid, _gid = peer_credentials(conn)
        except OSError as e:
            self.rejected += 1
            self._log(f'rejecting a peer whose credentials could not be read: {e}')
            conn.close()
            return
        ok, detail = peer_allowed(uid, self.allow_users)
        if not ok:
            # Say so, loudly and by name. A refused connection that logs
            # nothing is indistinguishable from a wire that was never tried.
            self.rejected += 1
            self._log(f'REFUSED connection from pid {pid}: {detail}')
            conn.close()
            return
        self.connections += 1
        with self._lock:
            self.peers[id(conn)] = {'pid': pid, 'uid': uid, 'user': detail,
                                    'since': time.monotonic()}
        self._log(f'peer connected: pid {pid} as {detail}')
        self._put({'kind': '_connected', 'pid': pid, 'user': detail,
                   't': time.time()})
        t = threading.Thread(target=self._read_loop, args=(conn,),
                             name='supervisor-read', daemon=True)
        t.start()
        self._threads.append(t)

    # -- reading ----------------------------------------------------------
    def _put(self, msg):
        try:
            self.q.put_nowait(msg)
        except queue.Full:
            # Drop the NEWEST. The alternative (evicting the oldest) reorders
            # a press ahead of the release that ended it, and a supervisor
            # that invents gestures is worse than one that misses them.
            self.dropped += 1

    def _read_loop(self, conn):
        conn.settimeout(READ_TIMEOUT)
        buf = b''
        pid = (self.peers.get(id(conn)) or {}).get('pid')
        why = 'eof'
        try:
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    continue
                except OSError as e:
                    why = str(e)
                    break
                if not chunk:
                    break
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    self._line(line)
                if len(buf) > MAX_LINE:
                    # No newline in a whole MAX_LINE of bytes: this is not our
                    # protocol. Throw the buffer away and keep reading rather
                    # than growing without bound off a wedged or hostile peer.
                    self.malformed += 1
                    self._log(f'discarding {len(buf)} bytes with no newline in '
                              f'them (line limit {MAX_LINE})')
                    buf = b''
        finally:
            try:
                conn.close()
            except OSError:
                pass
            self._log(f'peer disconnected: pid {pid} ({why})')
            # Queue the record BEFORE dropping the peer, so `connected` going
            # false is never the FIRST the consumer hears of it: the drain
            # that sees the disconnected flag has the record in the same batch.
            self._put({'kind': '_disconnected', 'pid': pid, 'why': why,
                       't': time.time()})
            with self._lock:
                self.peers.pop(id(conn), None)

    def _line(self, line):
        try:
            msg = decode(line)
        except ProtocolError as e:
            # NEVER fatal. A bad line is counted, said once, and skipped: the
            # daemon on this end owns gestures on a live console and may not
            # be killable by whatever the input process managed to write.
            self.malformed += 1
            if self.malformed <= 5 or self.malformed % 100 == 0:
                self._log(f'malformed line #{self.malformed} skipped: {e}')
            return
        self.received += 1
        self._put(msg)

    # -- draining ---------------------------------------------------------
    @property
    def connected(self):
        with self._lock:
            return bool(self.peers)

    @property
    def peer(self):
        with self._lock:
            return dict(next(iter(self.peers.values()))) if self.peers else None

    def get_all(self, limit=None):
        """Everything queued since the last call, oldest first. Never blocks."""
        out = []
        while limit is None or len(out) < limit:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                break
        return out


# =========================================================================
# inputproc's end: enqueue, never block, reconnect forever
# =========================================================================
class SupervisorClient:
    """The connecting half, and the one with the hard rule.

    SR7: send() is called from the input fast path, between a kernel event and
    the virtual pad, and it MUST NOT BLOCK. So it does exactly two things -
    put on a bounded queue, or count a drop - and a background thread owns the
    socket, the connect, the backoff and every syscall that can wait.

    couchd going away is not an error here. The pad keeps working; it just
    means nobody is listening for a while, and the drop counter says how long.
    """

    def __init__(self, path=None, on_log=None, maxsize=SEND_QUEUE,
                 on_connect=None, reconnect_min=RECONNECT_MIN,
                 reconnect_max=RECONNECT_MAX):
        self.path = path or default_path()
        self.on_log = on_log
        # Messages to send on every (re)connection, as a callable so it
        # reports the state NOW rather than the state at construction: after a
        # couchd restart the daemon needs to be told the pad is attached, or
        # its `pad` region sits on whatever it last believed.
        self.on_connect = on_connect
        self.q = queue.Queue(maxsize)
        self.reconnect_min = reconnect_min
        self.reconnect_max = reconnect_max
        self.drops = 0              # SR7: observations we chose to lose
        self.sent = 0
        self.connects = 0
        self.send_failures = 0
        self.last_error = None
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._sock = None
        self._thread = None

    def _log(self, msg):
        if self.on_log is not None:
            self.on_log(f'supervisor: {msg}')

    @property
    def connected(self):
        return self._connected.is_set()

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name='supervisor-send',
                                        daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._disconnect('closed')

    def wait_connected(self, timeout):
        """Block the CALLER (never the fast path) until the wire is up.

        Used once, at startup, before the pad is grabbed: owning the pad with
        nothing listening is the failure this whole file exists to prevent.
        """
        return self._connected.wait(timeout)

    # -- the fast path ----------------------------------------------------
    def send(self, kind, **fields):
        """Queue one observation. Returns True if queued, False if dropped.

        Never blocks, never raises, never touches a socket. Called with a
        kernel event half-translated and a game waiting for it.
        """
        if not self._connected.is_set():
            # Nobody is listening. Queueing anyway would hand couchd a burst of
            # seconds-old presses the moment it came back, and a supervisor
            # replaying stale input is worse than one that missed it.
            self.drops += 1
            return False
        try:
            self.q.put_nowait((kind, fields))
            return True
        except queue.Full:
            self.drops += 1
            return False

    def stats(self):
        return {'connected': self.connected, 'drops': self.drops,
                'sent': self.sent, 'connects': self.connects,
                'send_failures': self.send_failures, 'error': self.last_error,
                'queued': self.q.qsize(), 'path': self.path}

    # -- the thread -------------------------------------------------------
    def _run(self):
        backoff = self.reconnect_min
        while not self._stop.is_set():
            if not self._connected.is_set():
                if self._connect():
                    backoff = self.reconnect_min
                else:
                    self._stop.wait(backoff)
                    backoff = min(self.reconnect_max, backoff * 2)
                    continue
            try:
                item = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            kind, fields = item
            try:
                line = encode(kind, **fields)
            except (ProtocolError, TypeError, ValueError) as e:
                # A message this end could not even build costs ONE message,
                # never the connection: dropping the wire over a bad field
                # would take the pad's whole channel down with it.
                self.send_failures += 1
                self.last_error = str(e)
                self._log(f'unsendable {kind} message dropped: {e}')
                continue
            try:
                self._sock.sendall(line)
                self.sent += 1
            except OSError as e:
                self.send_failures += 1
                self.last_error = str(e)
                self._disconnect(str(e))

    def _connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        try:
            s.connect(self.path)
        except OSError as e:
            s.close()
            self.last_error = str(e)
            return False
        # Anything queued while we were down is STALE input. Throw it away
        # before the first byte of the new connection rather than delivering a
        # press whose release was dropped an age ago.
        stale = 0
        while True:
            try:
                self.q.get_nowait()
                stale += 1
            except queue.Empty:
                break
        self.drops += stale
        self._sock = s
        try:
            for kind, fields in (self.on_connect() if self.on_connect else ()):
                s.sendall(encode(kind, **fields))
                self.sent += 1
        except (OSError, ProtocolError) as e:
            self.last_error = str(e)
            self._disconnect(str(e))
            return False
        self.connects += 1
        self.last_error = None
        self._connected.set()
        self._log(f'connected to {self.path}'
                  + (f' ({stale} stale message(s) discarded)' if stale else ''))
        return True

    def _disconnect(self, why):
        was = self._connected.is_set()
        self._connected.clear()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if was:
            self._log(f'disconnected ({why}); the pad keeps working, nobody '
                      f'is listening')

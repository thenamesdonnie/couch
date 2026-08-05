#!/usr/bin/env python3
"""Who owns what, right now - the one switch both stacks read at runtime.

couchd and the legacy scripts must agree, every second, about which
responsibility belongs to which stack: a responsibility owned by nobody is a
console with no PS button, and one owned by both is two arbiters fighting over
the same pad (C27's exactly-one-grabber rule, in the small). So the answer
lives in ONE file - ~/couch/couchd/owns.conf - parsed by ONE module here, and
by the four lines of shell in game-launch that mirror this grammar exactly.

Empty (the shipped state) means SHADOW: couchd acts on nothing, legacy acts on
everything, which is the console's behaviour before couchd existed.

The file is read fresh (stat-cached) on every couchd tick and every legacy
decision, so a flip - or a rollback to empty - takes effect within a tick with
no restart of anything.

Absent, unreadable or empty file = own nothing. Every failure mode here has
the same answer, and it is always the safe one.
"""
import os
import re
import time

HOME = os.path.expanduser('~')
DEFAULT_PATH = os.path.join(HOME, 'couch', 'couchd', 'owns.conf')

# couchd's heartbeat. A responsibility is only YIELDED by the legacy scripts
# while the daemon that took it is demonstrably alive: `systemctl --user stop
# couchd` with a non-empty owns.conf would otherwise leave the console owned by
# a corpse, with legacy politely declining to act. status.json is rewritten
# every ~3s, so 30s of silence is many missed beats, not a slow tick.
STATUS_FILE = os.path.join(HOME, 'couch', 'shadow', 'status.json')
HEARTBEAT_MAX_AGE = 30.0

# The C9 acceptance-gate list, which is also the reason-prefix taxonomy couchd
# stamps on every intent. 'input' is stage 2's (the input process reads it);
# stage-1 couchd maps no verb to it, so naming it here flips nothing on its
# own - it is listed so a stage-2 flag day is not rejected as a typo.
RESPONSIBILITIES = ('gestures', 'transitions', 'guard', 'reconcile', 'input')

# Stage-1 couchd can actually execute these three-plus-one; 'input' is not
# actionable by the supervisor and is named separately so status.json can say
# so out loud rather than implying couchd took something it cannot do.
ACTABLE = ('gestures', 'transitions', 'guard', 'reconcile')

# intent reason prefix -> responsibility. reconcile() stamps every intent with
# one of these four prefixes, so routing needs no second table to drift from.
BY_REASON_PREFIX = {
    'gesture': 'gestures',
    'transition': 'transitions',
    'guard': 'guard',
    'reconcile': 'reconcile',
}

_LINE = re.compile(r'^\s*COUCHD_OWNS\s*=\s*(.*)$')
_EXPORT = re.compile(r'^\s*export\s+COUCHD_OWNS\s*=')


class Owns:
    """One parse of the file. Immutable by convention; cheap to copy."""

    def __init__(self, names=(), warnings=(), raw='', path=DEFAULT_PATH,
                 mtime=None):
        self.names = frozenset(names)
        self.warnings = tuple(warnings)
        self.raw = raw
        self.path = path
        self.mtime = mtime

    def __contains__(self, name):
        return name in self.names

    def __bool__(self):
        return bool(self.names)

    def __iter__(self):
        return iter(self.sorted)

    def __eq__(self, other):
        return isinstance(other, Owns) and self.names == other.names \
            and self.warnings == other.warnings

    @property
    def sorted(self):
        return sorted(self.names)

    @property
    def actable(self):
        """What stage-1 couchd can actually execute (see ACTABLE)."""
        return sorted(n for n in self.names if n in ACTABLE)

    def __repr__(self):
        return f'Owns({",".join(self.sorted) or "-"})'


def unquote(raw):
    """The value grammar, in one function, mirrored EXACTLY by game-launch's
    four lines of shell. Any divergence here is a responsibility owned by both
    stacks or by neither, so the rule is deliberately dumb:

      1. cut at the first '#'          (trailing comment)
      2. drop every '\\r'               (a CRLF file must not own differently)
      3. trim surrounding whitespace
      4. if it now begins AND ends with the same quote character, drop exactly
         those two - never every quote in the string, or
         `COUCHD_OWNS="gestures" "transitions"` would own two things on one
         side and nothing on the other
      5. trim again

    A parity test runs this against the shell version over a corpus of hostile
    files; keep them changing together.
    """
    value = (raw or '').split('#', 1)[0].replace('\r', '').strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    return value


def parse(text, path=DEFAULT_PATH, mtime=None):
    """Text -> Owns. The LAST COUCHD_OWNS= line wins; unknown names are
    dropped with a warning rather than silently accepted (an accepted typo
    would leave a responsibility owned by nobody on one side of the flip)."""
    raw, warnings, exported = None, [], False
    text = text or ''
    # Split the way sed does - on newlines only, CRLF folded to LF - NOT with
    # splitlines(), which also splits on a bare \r and would find a
    # COUCHD_OWNS= line in the middle of a \r-terminated line that sed reads
    # as one. Same file, same lines, both stacks.
    for line in text.replace('\r\n', '\n').split('\n'):
        if _EXPORT.match(line):
            exported = True
            continue
        m = _LINE.match(line)
        if m:
            raw = m.group(1)
    if exported:
        warnings.append('`export COUCHD_OWNS=` is not read by both stacks; '
                        'use a plain COUCHD_OWNS= line')
    if '\r\n' in text or '\r' in text:
        # Both parsers now strip it, so this changes no decision - it is said
        # out loud because a config file with Windows line endings on this box
        # means something upstream is editing it in a way nobody intended.
        warnings.append(f'{path} has CRLF line endings (tolerated, but check '
                        f'what wrote it)')
    if raw is None:
        return Owns((), warnings, '', path, mtime)
    value = unquote(raw)
    names, seen = [], set()
    for token in value.replace(',', ' ').split():
        if token not in RESPONSIBILITIES:
            warnings.append(f'unknown responsibility {token!r} in {path} - '
                            f'ignored (known: {", ".join(RESPONSIBILITIES)})')
            continue
        if token in seen:
            continue
        seen.add(token)
        names.append(token)
    return Owns(names, warnings, value, path, mtime)


_cache = {}     # path -> (stat_key, Owns)


def load(path=None, force=False):
    """The current ownership, stat-cached: re-parsed only when the file
    changed, so this is safe to call from a select loop or every tick."""
    path = path or os.environ.get('COUCHD_OWNS_FILE') or DEFAULT_PATH
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        key = None
    hit = _cache.get(path)
    if hit and hit[0] == key and not force:
        return hit[1]
    if key is None:
        # No file at all is the shipped, safe state: own nothing, say nothing.
        result = Owns((), (), '', path, None)
    else:
        try:
            # errors='replace' on purpose: a file that is not valid UTF-8 (an
            # editor writing latin-1, a half-flushed write) must degrade to
            # "own nothing" with a warning. Raising here would crash-loop the
            # daemon, and a crash-loop is the one failure mode a config file is
            # never allowed to cause.
            # newline='' so the parser sees the file's real bytes, exactly as
            # sed does, instead of letting universal-newline translation hide
            # a CRLF file from the CRLF check below.
            with open(path, encoding='utf-8', errors='replace',
                      newline='') as f:
                result = parse(f.read(), path, st.st_mtime)
        except Exception as e:
            result = Owns((), (f'{path} unreadable ({type(e).__name__}: {e}); '
                               f'owning nothing',), '', path, None)
    _cache[path] = (key, result)
    return result


def heartbeat_age(path=None, now=None):
    """Seconds since couchd last rewrote status.json, or None if it never
    has. Cheap (one stat) because every legacy decision pays for it."""
    path = path or os.environ.get('COUCHD_STATUS_FILE') or STATUS_FILE
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return None
    return max(0.0, (time.time() if now is None else now) - mtime)


def couchd_alive(path=None, max_age=HEARTBEAT_MAX_AGE, now=None):
    """Is the daemon that took these responsibilities actually running?

    `systemctl --user stop couchd` is the charter's one-command rollback, and
    an operator reaching for it in the dark will not edit a config file first.
    Without this check a stopped couchd with a non-empty owns.conf would leave
    every yielded responsibility owned by nobody: the PS button dead, drift
    unrepaired, and no error anywhere. So the legacy scripts treat ownership
    as a LEASE - taken by the file, kept alive by the heartbeat."""
    age = heartbeat_age(path, now)
    return age is not None and age < max_age


def owns(name, path=None, status_path=None):
    """True if couchd owns `name` AND is alive to act on it. The one call the
    legacy scripts make; anything that goes wrong answers False, which leaves
    legacy acting.

    NOT used by couchd itself (it calls load()): the daemon must not make its
    own ownership conditional on the file it is about to write."""
    try:
        return name in load(path).names and couchd_alive(status_path)
    except Exception:
        return False


def responsibility_for_reason(reason):
    """'gesture:ps-hold' -> 'gestures'. None for a reason with no owner
    taxonomy, which is never acted on (recorded only)."""
    prefix = (reason or '').split(':', 1)[0]
    return BY_REASON_PREFIX.get(prefix)


def describe(o=None):
    """One human line, the shape say() wants."""
    o = load() if o is None else o
    return 'owns: ' + (', '.join(o.sorted) if o.names else '(nothing - shadow)')


if __name__ == '__main__':      # a two-second check from any shell
    cur = load()
    print(describe(cur), f'[{cur.path}]', f'mtime={cur.mtime}')
    for w in cur.warnings:
        print('warning:', w)
    age = heartbeat_age()
    print('couchd heartbeat:',
          'never' if age is None else f'{age:.1f}s ago',
          '- legacy yields' if couchd_alive() else '- legacy ACTS (stale/absent)')
    print('as of', time.strftime('%H:%M:%S'))

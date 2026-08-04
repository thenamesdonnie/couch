#!/usr/bin/env python3
"""The PS-button KEY BINDINGS, read from Kodi's own settings file.

`script.couch.switcher` grows a settings page (Kodi > Add-ons > Program
add-ons > Couch Switcher > Configure). Kodi writes the chosen values to

    ~/.kodi/userdata/addon_data/script.couch.switcher/settings.xml

and this module is the ONE reader of that file. Both stacks import it - the
live watcher (~/.local/bin/pad-home-watcher) and couchd's shadow model - so a
rebind moves both at once and the shadow diff stays clean. That is the whole
point of the module: the same rule gesture.py applies to the timing arithmetic
(one home for the numbers) applied to the bindings.

Contract, in order of importance:

  * it NEVER raises. A missing file, a truncated file, a file Kodi is halfway
    through rewriting, an unknown action name, a nonsense number - every one
    of them degrades to the documented default for that field alone and
    records a warning. The console must not lose its PS button because an XML
    parse failed.
  * the SAFETY RAIL: at least one gesture must map to `suspend_to_kodi`. That
    is the only way back out of a game, so a config that binds it away is
    rejected as a whole and `hold` is forced back to it. A user cannot lock
    themselves inside a running game from this settings page.
  * reads are cheap. load() stats the file and returns the cached parse
    unless (mtime_ns, size, inode) changed, so a 5Hz loop can call it every
    iteration.

Two precedence rules, both of the same shape - a gesture that would be
shadowed by a stronger one is dropped rather than double-firing:

  * `long_hold` only fires if `hold` is bound to `none`. A press cannot be
    both a 0.9s hold and a 3.0s long hold; the hold fires first and at that
    point the gesture is spent. Binding both is a mistake, not a chord, so the
    long hold is ignored and a warning is recorded.
  * `tap` only fires if `double_tap` is bound to `none`, for the mirror
    reason: with both bound, every double-tap would fire the tap action on its
    way through. (Deferring the tap by DOUBLE_TAP_S to disambiguate was the
    alternative and was rejected: it would put 350ms of latency on the most
    common press in the room.)

Defaults reproduce today's console EXACTLY:

    tap          none              (see the note on tap-resume below)
    double_tap   switcher
    hold         suspend_to_kodi
    hold_release none
    long_hold    none
    hold_seconds 0.9   double_tap_seconds 0.35   long_hold_seconds 3.0

`tap = none` is not "the tap does nothing": a tap while a game is PAUSED
resumes it, and that is deliberately NOT a binding. It is the recovery path -
the only way back into a suspended game from the couch - and a user who bound
the tap away would strand the paused game with no route back. It stays state
logic in the watcher, above the binding dispatch.
"""
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace

# -- vocabulary ------------------------------------------------------------
#: the gestures that can be bound, in the order the settings page shows them
GESTURES = ('tap', 'double_tap', 'hold', 'hold_release', 'long_hold')

#: what a gesture can be bound TO. Every one of these is implemented by both
#: the watcher (as an effect) and couchd (as an intent); adding one here
#: without adding it to both is a bug the tests catch.
ACTIONS = ('none', 'suspend_to_kodi', 'switcher', 'steam_menu', 'power_menu',
           'quit_game', 'tv_toggle', 'desktop')

#: the action that must always be reachable (the safety rail)
ESCAPE_ACTION = 'suspend_to_kodi'

DEFAULT_BINDINGS = {
    'tap': 'none',
    'double_tap': 'switcher',
    'hold': ESCAPE_ACTION,
    'hold_release': 'none',
    'long_hold': 'none',
}

DEFAULT_TIMINGS = {
    'hold_seconds': 0.9,
    'double_tap_seconds': 0.35,
    'long_hold_seconds': 3.0,
}

#: (minimum, maximum) per timing, matching resources/settings.xml's slider
#: constraints. A value outside these is not clamped silently - it is a sign
#: the file is not the one Kodi wrote - so it falls back to the default and
#: says so.
TIMING_LIMITS = {
    'hold_seconds': (0.3, 3.0),
    'double_tap_seconds': (0.15, 1.0),
    'long_hold_seconds': (1.0, 10.0),
}

ADDON_ID = 'script.couch.switcher'
SETTINGS_PATH = os.path.expanduser(
    f'~/.kodi/userdata/addon_data/{ADDON_ID}/settings.xml')

#: setting ids in resources/settings.xml -> our field names
BINDING_SETTING = {f'gesture.{g}': g for g in GESTURES}
TIMING_SETTING = {f'timing.{t}': t for t in DEFAULT_TIMINGS}


# =========================================================================
# the value
# =========================================================================
@dataclass(frozen=True)
class GestureConfig:
    """What the two stacks act on.

    `bindings` is EFFECTIVE - precedence rules and the safety rail already
    applied, so a caller can dispatch on it without knowing about either.
    `requested` is what the file actually asked for, kept so the warnings can
    be explained and so a test can tell "suppressed" from "never set".
    """
    bindings: dict = field(default_factory=lambda: dict(DEFAULT_BINDINGS))
    requested: dict = field(default_factory=lambda: dict(DEFAULT_BINDINGS))
    hold_seconds: float = DEFAULT_TIMINGS['hold_seconds']
    double_tap_seconds: float = DEFAULT_TIMINGS['double_tap_seconds']
    long_hold_seconds: float = DEFAULT_TIMINGS['long_hold_seconds']
    warnings: tuple = ()
    source: str = None          # the file it came from, or None for defaults
    stamp: tuple = None         # (mtime_ns, size, inode) of that file

    @property
    def is_default(self):
        return (self.bindings == DEFAULT_BINDINGS
                and self.timings == DEFAULT_TIMINGS)

    @property
    def timings(self):
        return {'hold_seconds': self.hold_seconds,
                'double_tap_seconds': self.double_tap_seconds,
                'long_hold_seconds': self.long_hold_seconds}

    def action_for(self, gesture):
        """The effective action for one gesture; 'none' for anything we do
        not recognise, so a caller can dispatch without a KeyError."""
        return self.bindings.get(gesture, DEFAULT_BINDINGS.get(gesture, 'none'))

    def bound_to(self, action):
        """Which gestures fire `action` (the safety rail's question)."""
        return tuple(g for g in GESTURES if self.bindings.get(g) == action)


DEFAULTS = GestureConfig()


# =========================================================================
# parsing - every step degrades, none of them raise
# =========================================================================
def _text(node):
    """The value of one <setting> node, in either shape Kodi has written.

    Kodi 20 writes the new form (`<setting id="x">value</setting>`); the old
    form (`<setting id="x" value="v"/>`) is still read because an addon_data
    file written by an older Kodi survives an upgrade untouched.
    """
    if node.get('value') is not None:
        return node.get('value')
    return (node.text or '').strip()


def parse(text):
    """settings.xml text -> (requested_bindings, timings, warnings).

    Unknown ids are ignored (Kodi keeps settings we removed), a bad value is
    replaced by that field's default, and a document that will not parse at
    all yields the defaults plus one warning.
    """
    bindings = dict(DEFAULT_BINDINGS)
    timings = dict(DEFAULT_TIMINGS)
    warnings = []
    if not (text or '').strip():
        return bindings, timings, ('settings file is empty; using defaults',)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        # Kodi rewrites this file in place; a read that lands mid-write gets a
        # truncated document. Defaults for one tick beats a dead PS button.
        return bindings, timings, (f'settings file is not valid XML ({e}); '
                                   'using defaults',)
    for node in root.iter('setting'):
        sid = node.get('id') or ''
        raw = _text(node)
        if sid in BINDING_SETTING:
            name = BINDING_SETTING[sid]
            if raw in ACTIONS:
                bindings[name] = raw
            else:
                warnings.append(
                    f'{sid}={raw!r} is not a known action; '
                    f'{name} falls back to {DEFAULT_BINDINGS[name]}')
        elif sid in TIMING_SETTING:
            name = TIMING_SETTING[sid]
            lo, hi = TIMING_LIMITS[name]
            try:
                val = float(raw)
            except (TypeError, ValueError):
                warnings.append(f'{sid}={raw!r} is not a number; '
                                f'{name} falls back to {DEFAULT_TIMINGS[name]}')
                continue
            if not (lo <= val <= hi) or val != val:      # NaN fails both
                warnings.append(f'{sid}={raw} is outside {lo}..{hi}; '
                                f'{name} falls back to {DEFAULT_TIMINGS[name]}')
                continue
            timings[name] = val
    if timings['long_hold_seconds'] <= timings['hold_seconds']:
        warnings.append(
            f"long_hold_seconds ({timings['long_hold_seconds']}) must be "
            f"longer than hold_seconds ({timings['hold_seconds']}); "
            f"using {DEFAULT_TIMINGS['long_hold_seconds']}")
        timings['long_hold_seconds'] = DEFAULT_TIMINGS['long_hold_seconds']
        if timings['long_hold_seconds'] <= timings['hold_seconds']:
            # a hold threshold above 3.0s: push the long hold out of its way
            timings['long_hold_seconds'] = timings['hold_seconds'] + 1.0
    return bindings, timings, tuple(warnings)


# =========================================================================
# precedence + the safety rail
# =========================================================================
def suppress(bindings):
    """Drop the gestures a stronger one would shadow. Pure; see the module
    docstring for why each rule exists."""
    out = dict(bindings)
    warnings = []
    if out.get('hold', 'none') != 'none' and out.get('long_hold', 'none') != 'none':
        warnings.append(
            f"long_hold={out['long_hold']} is ignored while hold is bound "
            f"({out['hold']}): the hold fires first and spends the press")
        out['long_hold'] = 'none'
    if out.get('double_tap', 'none') != 'none' and out.get('tap', 'none') != 'none':
        warnings.append(
            f"tap={out['tap']} is ignored while double_tap is bound "
            f"({out['double_tap']}): every double-tap would fire it on the way")
        out['tap'] = 'none'
    return out, tuple(warnings)


def validate(bindings, previous=None):
    """THE SAFETY RAIL.

    Suspending the game and landing on Kodi is the only way out of a running
    game from the couch. If no gesture is bound to it the config as a whole is
    rejected - not patched field by field - and `hold` is forced back to the
    previous working binding, or to the default if there is none.

    Returns (effective_bindings, warnings). Suppression runs on both sides of
    the rail: it decides what is really reachable (so a `long_hold` shadowed
    by a bound `hold` does not count as an escape), and it has to run again
    after the rail forces `hold`, because forcing it may now shadow something.
    """
    effective, warnings = suppress(bindings)
    if ESCAPE_ACTION in effective.values():
        return effective, warnings
    forced = DEFAULT_BINDINGS['hold']
    if previous is not None and previous.bindings.get('hold') == ESCAPE_ACTION:
        forced = previous.bindings['hold']
    warnings = warnings + (
        f'REJECTED: no gesture reaches {ESCAPE_ACTION}, which is the only way '
        f'out of a running game; hold forced back to {forced}',)
    effective = dict(effective)
    effective['hold'] = forced
    effective, more = suppress(effective)
    return effective, warnings + more


def build(text, source=None, stamp=None, previous=None):
    """Whole pipeline, text in -> GestureConfig out. Never raises."""
    try:
        requested, timings, warnings = parse(text)
        effective, more = validate(requested, previous)
    except Exception as e:      # pragma: no cover - belt and braces (C3)
        return replace(DEFAULTS, warnings=(f'unreadable settings ({e!r}); '
                                           'using defaults',),
                       source=source, stamp=stamp)
    return GestureConfig(bindings=effective, requested=requested,
                         warnings=warnings + more, source=source, stamp=stamp,
                         **timings)


# =========================================================================
# the cached reader
# =========================================================================
_CACHE = {}


def _stamp(path):
    """(mtime_ns, size, inode), or None if the file is not there. Kodi
    rewrites this file with a rename, so the inode is part of the identity."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def load(path=None, force=False, previous=None):
    """The config, re-parsed only when the file changed.

    Cheap enough to call from a 5Hz loop: one stat() in the common case. A
    file that has never been written (the user has not opened the settings
    page yet) is not an error - it is the default console.
    """
    path = path or SETTINGS_PATH
    stamp = _stamp(path)
    cached = _CACHE.get(path)
    if not force and cached is not None and cached.stamp == stamp:
        return cached
    if stamp is None:
        conf = replace(DEFAULTS, source=path, stamp=None)
    else:
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read()
        except OSError as e:
            conf = replace(DEFAULTS, source=path, stamp=stamp,
                           warnings=(f'settings file unreadable ({e}); '
                                     'using defaults',))
        else:
            conf = build(text, source=path, stamp=stamp,
                         previous=previous if previous is not None else cached)
    _CACHE[path] = conf
    return conf


def forget(path=None):
    """Drop the cache (tests, and the daemon on SIGHUP)."""
    if path is None:
        _CACHE.clear()
    else:
        _CACHE.pop(path, None)


if __name__ == '__main__':      # pragma: no cover - a human's `what is bound?`
    c = load()
    print(f'source: {c.source}{"" if c.stamp else " (not written yet)"}')
    for g in GESTURES:
        req = c.requested.get(g)
        eff = c.bindings.get(g)
        print(f'  {g:<13} {eff}' + (f'   (asked for {req})' if req != eff else ''))
    for k, v in c.timings.items():
        print(f'  {k:<13} {v}')
    for w in c.warnings:
        print(f'  ! {w}')

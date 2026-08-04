#!/usr/bin/env python3
"""Theory-3 test: human-chaotic PS press trains fired DURING transitions.

Each burst fires taps/holds with no settle waits (both channels, like a real
thumb). After each burst we poll once a second for a CONSISTENT state:

  suspended : flag set, every game pid frozen, Kodi on top+focused, joystick on
  running   : no flag, no frozen pids, game/BP on top+focused, joystick off
  idle      : no session, Kodi on top, joystick on

Either suspended or running is a legal landing zone for chaos; what matters is
that the system converges, and how fast. Fail = inconsistent for > 20s.
"""
import fcntl
import json
import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from couchenv import kodi_auth, kodi_url

EVENT_FORMAT = 'llHHi'
EV_KEY, EV_SYN = 0x01, 0x00
BTN_MODE, SYN_REPORT = 0x13c, 0
UI_SET_EVBIT, UI_SET_KEYBIT = 0x40045564, 0x40045565
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
LOG = '/tmp/pad-home.log'

os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('XAUTHORITY', os.path.expanduser('~/.Xauthority'))


def ds_create():
    fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_MODE)
    setup = struct.pack('80sHHHHI', b'DualSense Wireless Controller',
                        0x05, 0x0000, 0x0000, 1, 0)
    os.write(fd, setup + b'\x00' * (4 * 64 * 4))
    fcntl.ioctl(fd, UI_DEV_CREATE)
    return fd


def ds_wait_adopted(already):
    for _ in range(90):
        time.sleep(0.5)
        try:
            lines = open(LOG).read().splitlines()
        except OSError:
            lines = []
        if any('watching' in l for l in lines[already:]):
            return
    sys.exit('watcher never adopted fake DualSense')


def ds_emit(fd, value):
    os.write(fd, struct.pack(EVENT_FORMAT, 0, 0, EV_KEY, BTN_MODE, value))
    os.write(fd, struct.pack(EVENT_FORMAT, 0, 0, EV_SYN, SYN_REPORT, 0))


def press(ds_fd, seconds):
    ds_emit(ds_fd, 1)
    p = subprocess.Popen(['/home/ds2000/.local/bin/vpad', 'hold', 'guide',
                          str(seconds)])
    time.sleep(seconds)
    ds_emit(ds_fd, 0)
    p.wait()


# ---------- state reading
def flag(path):
    try:
        return open(path).read().strip()
    except OSError:
        return None


def game_states():
    r = subprocess.run(['/home/ds2000/.local/bin/game-pids'],
                       capture_output=True, text=True)
    st = {}
    for pid in r.stdout.split():
        try:
            stat = open(f'/proc/{pid}/stat').read()
            st[pid] = stat.rsplit(') ', 1)[1].split()[0]
        except (OSError, IndexError):
            pass
    return st


def jrpc(method, params=None):
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method,
                       'params': params or {}})
    r = subprocess.run(['curl', '-s', '-m', '3', '-u', kodi_auth(),
                        '-H', 'content-type: application/json', '-d', body,
                        kodi_url()],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get('result')
    except Exception:
        return None


def top_and_focus():
    from Xlib import display
    d = display.Display()
    root = d.screen().root
    NET_NAME = d.intern_atom('_NET_WM_NAME')

    def info(w, depth=0):
        try:
            p = w.get_full_property(NET_NAME, 0)
            nm = p.value.decode() if p else ''
            nm = nm or (w.get_wm_name() or '')
            cls = (w.get_wm_class() or ('', ''))[0]
            if nm or cls:
                return nm, cls
            if depth < 3:
                for c in w.query_tree().children:
                    r = info(c, depth + 1)
                    if r:
                        return r
        except Exception:
            pass
        return None

    top = ('', '')
    try:
        for c in root.query_tree().children:
            a = c.get_attributes()
            if a.map_state != 2 or a.win_class == 2:
                continue
            g = c.get_geometry()
            if g.width < 600 or g.height < 400:
                continue
            top = info(c) or top
    except Exception:
        pass
    try:
        f = d.get_input_focus().focus
        focus = (f.get_wm_name() or '') if hasattr(f, 'get_wm_name') else ''
    except Exception:
        focus = ''
    d.close()
    return top, focus


def classify():
    """Return (state_name, problems). problems empty = consistent."""
    susp = flag('/tmp/game-suspended')
    sess = flag('/tmp/game-session')
    states = game_states()
    joy = (jrpc('Settings.GetSettingValue',
                {'setting': 'input.enablejoystick'}) or {}).get('value')
    (top_name, top_cls), focus = top_and_focus()
    problems = []
    if susp is not None:
        name = 'suspended'
        if not states:
            problems.append('flag but no game pids')
        elif any(s != 'T' for s in states.values()):
            problems.append(f'not all frozen: {set(states.values())}')
        if top_name != 'Kodi':
            problems.append(f'top={top_name or top_cls}')
        if focus != 'Kodi':
            problems.append(f'focus={focus}')
        if joy is not True:
            problems.append(f'joystick={joy}')
    elif sess is not None:
        name = 'running'
        if any(s == 'T' for s in states.values()):
            problems.append(f'frozen pids present: {set(states.values())}')
        if states and not (top_cls.startswith('steam_app')
                           or 'Big Picture' in top_name):
            problems.append(f'top={top_name or top_cls}')
        if joy is not False:
            problems.append(f'joystick={joy}')
    else:
        name = 'idle'
        if top_name != 'Kodi':
            problems.append(f'top={top_name or top_cls}')
        if joy is not True:
            problems.append(f'joystick={joy}')
    return name, problems


def converge(deadline=20):
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < deadline:
        name, problems = classify()
        last = (name, problems)
        if not problems:
            return name, round(time.monotonic() - t0, 1), True
        time.sleep(1)
    return f'{last[0]} STUCK {last[1]}', deadline, False


BURSTS = [
    ('triple tap in-game, 0.2s apart',
     [(0.15, 0.2), (0.15, 0.2), (0.15, 0)]),
    ('tap then hold 0.3s later (hold lands mid menu animation)',
     [(0.15, 0.3), (1.2, 0)]),
    ('tap 0.5s after the hold handoff (resume mid kodi-guard)',
     [(1.2, 0.5), (0.15, 0)]),
    ('hold 1s after a resume tap (suspend mid resume transition)',
     [(0.15, 1.0), (1.2, 0)]),
    ('five taps 150ms apart',
     [(0.15, 0.15)] * 4 + [(0.15, 0)]),
    ('hold then hold again immediately',
     [(1.2, 0.4), (1.2, 0)]),
    ('boundary presses: 0.7s and 0.95s',
     [(0.7, 0.5), (0.95, 0)]),
]


def main():
    already = len(open(LOG).read().splitlines()) if os.path.exists(LOG) else 0
    subprocess.run(['/home/ds2000/.local/bin/vpad', 'up'], check=False)
    ds_fd = ds_create()
    ds_wait_adopted(already)
    print('channels up')

    subprocess.Popen(['setsid', '/home/ds2000/.local/bin/game-launch',
                      'bigpicture'], start_new_session=True)
    for _ in range(40):
        time.sleep(2)
        if flag('/tmp/game-session'):
            break
    time.sleep(8)
    subprocess.run('steam steam://rungameid/367520 >/dev/null 2>&1',
                   shell=True)
    for _ in range(60):
        time.sleep(2)
        if game_states():
            break
    time.sleep(12)
    name, t, ok = converge()
    print(f'baseline: {name} ({t}s) ok={ok}')

    results = []
    for label, seq in BURSTS:
        print(f'--- burst: {label}')
        for hold_s, gap in seq:
            press(ds_fd, hold_s)
            if gap:
                time.sleep(gap)
        name, t, ok = converge()
        results.append((label, name, t, ok))
        print(f'    -> {name} in {t}s ok={ok}')

    print('cleanup')
    subprocess.run(['/home/ds2000/.local/bin/game-launch', 'quit'],
                   check=False)
    time.sleep(8)
    name, t, ok = converge()
    results.append(('after quit', name, t, ok))
    print(f'    -> {name} in {t}s ok={ok}')

    ds_emit(ds_fd, 0)
    try:
        fcntl.ioctl(ds_fd, UI_DEV_DESTROY)
    except OSError:
        pass
    os.close(ds_fd)
    subprocess.run(['/home/ds2000/.local/bin/vpad', 'quit'], check=False)

    print('\n=== RESULTS')
    for label, name, t, ok in results:
        print(f'{"PASS" if ok else "FAIL":4} {t:>5}s  {name:12}  {label}')
    sys.exit(0 if all(r[3] for r in results) else 1)


if __name__ == '__main__':
    main()

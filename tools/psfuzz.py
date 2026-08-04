#!/usr/bin/env python3
"""PS-button fuzz harness: replay tap/hold sequences through BOTH consumers
(watcher via a fake DualSense, Steam via vpad's guide) and capture the full
screen/window/process state after each step.

Results land in psfuzz/ as stepNN-* files plus a state.jsonl log.
"""
import fcntl
import json
import os
import re
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from couchenv import kodi_auth, kodi_url

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'psfuzz')
EVENT_FORMAT = 'llHHi'
EV_KEY, EV_SYN = 0x01, 0x00
BTN_MODE, SYN_REPORT = 0x13c, 0
UI_SET_EVBIT, UI_SET_KEYBIT = 0x40045564, 0x40045565
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
NAME = 'DualSense Wireless Controller'
LOG = '/tmp/pad-home.log'

os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('XAUTHORITY', os.path.expanduser('~/.Xauthority'))


# ---------- fake DualSense (watcher channel; neutral ids so Steam ignores it)
def ds_create():
    fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_MODE)
    setup = struct.pack('80sHHHHI', NAME.encode(), 0x05, 0x0000, 0x0000, 1, 0)
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


# ---------- both-channel presses (what a physical thumb does)
def vpad(*args):
    subprocess.run(['/home/ds2000/.local/bin/vpad', *args], check=False)


def press(ds_fd, seconds):
    ds_emit(ds_fd, 1)
    # vpad hold blocks in its daemon for the duration; run it async so the
    # two channels overlap like a real press.
    p = subprocess.Popen(['/home/ds2000/.local/bin/vpad', 'hold', 'guide',
                          str(seconds)])
    time.sleep(seconds)
    ds_emit(ds_fd, 0)
    p.wait()


# ---------- state capture
def window_stack():
    from Xlib import display, X
    d = display.Display()
    root = d.screen().root
    NET_NAME = d.intern_atom('_NET_WM_NAME')
    NET_PID = d.intern_atom('_NET_WM_PID')

    def client_info(w, depth=0):
        # The WM wraps clients in anonymous frames; descend to the named one.
        try:
            p = w.get_full_property(NET_NAME, 0)
            nm = p.value.decode() if p else ''
            nm = nm or (w.get_wm_name() or '')
            cls = (w.get_wm_class() or ('', ''))[0]
            pp = w.get_full_property(NET_PID, 0)
            pid = int(pp.value[0]) if pp else 0
            if nm or cls or pid:
                return nm, cls, pid
            if depth < 3:
                for c in w.query_tree().children:
                    r = client_info(c, depth + 1)
                    if r:
                        return r
        except Exception:
            pass
        return None

    out = []
    for c in root.query_tree().children:  # bottom -> top
        try:
            a = c.get_attributes()
            if a.map_state != 2:
                continue
            g = c.get_geometry()
            if g.width < 600 or g.height < 400:
                continue
            nm, cls, pid = client_info(c) or ('', '', 0)
            out.append({'id': hex(c.id), 'name': nm, 'class': cls, 'pid': pid,
                        'w': g.width, 'h': g.height,
                        'input_only': a.win_class == X.InputOnly})
        except Exception:
            continue
    try:
        f = d.get_input_focus().focus
        focus = (f.get_wm_name() or '') if hasattr(f, 'get_wm_name') else str(f)
    except Exception:
        focus = '?'
    d.close()
    return out, focus


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


def game_states():
    r = subprocess.run(['pgrep', '-f', 'steamapps/[c]ommon'],
                       capture_output=True, text=True)
    states = {}
    for pid in r.stdout.split():
        try:
            stat = open(f'/proc/{pid}/stat').read()
            states[pid] = stat.rsplit(') ', 1)[1].split()[0]
        except OSError:
            pass
    return states


def flag(path):
    try:
        return open(path).read().strip()
    except OSError:
        return None


def steam_route():
    try:
        last = ''
        p = os.path.expanduser(
            '~/.steam/debian-installation/logs/controller_ui.txt')
        for l in open(p, encoding='utf-8', errors='replace'):
            if 'OnFocusWindowChanged' in l:
                last = l.strip()
        return last[-80:]
    except OSError:
        return ''


def capture(step, label):
    time.sleep(8)  # settle: watcher + game-launch + Steam + the input guard
    stack, focus = window_stack()
    state = {
        'step': step, 'label': label, 't': time.strftime('%H:%M:%S'),
        'stack_bottom_to_top': stack, 'focus': focus,
        'joystick': (jrpc('Settings.GetSettingValue',
                          {'setting': 'input.enablejoystick'}) or {}).get('value'),
        'session': flag('/tmp/game-session'),
        'suspended': flag('/tmp/game-suspended'),
        'game_states': game_states(),
        'steam_route': steam_route(),
        'kodi_window': (jrpc('GUI.GetProperties',
                             {'properties': ['currentwindow']})
                        or {}).get('currentwindow', {}).get('label'),
    }
    with open(os.path.join(OUT, 'state.jsonl'), 'a') as f:
        f.write(json.dumps(state) + '\n')
    # screenshot every big VISIBLE window (InputOnly can't be imaged)
    visible = [w for w in stack if not w['input_only']]
    for rank, win in enumerate(reversed(visible)):
        tag = (win['class'] or win['name'] or 'none').replace(' ', '_')[:24]
        fn = os.path.join(OUT, f'step{step:02d}-{rank}-{tag}.png')
        subprocess.run(['import', '-silent', '-window', win['id'], fn],
                       timeout=15, check=False)
    top = visible[-1] if visible else {'name': '?', 'class': ''}
    print(f'[{state["t"]}] step {step} ({label}) captured: '
          f'top={top["name"] or top["class"]} focus={focus} '
          f'joy={state["joystick"]} susp={state["suspended"]} '
          f'games={set(state["game_states"].values())}')
    return state


# ---------- the run
def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def main():
    os.makedirs(OUT, exist_ok=True)
    already = len(open(LOG).read().splitlines()) if os.path.exists(LOG) else 0

    print('bringing up channels...')
    vpad('up')
    ds_fd = ds_create()
    ds_wait_adopted(already)
    print('watcher adopted fake pad; vpad up')

    print('launching big picture session...')
    subprocess.Popen(['setsid', '/home/ds2000/.local/bin/game-launch',
                      'bigpicture'], start_new_session=True)
    for _ in range(40):
        time.sleep(2)
        if flag('/tmp/game-session'):
            break
    else:
        sys.exit('big picture session never started')
    time.sleep(8)
    capture(0, 'baseline: big picture up')

    print('launching hollow knight inside big picture...')
    sh('steam steam://rungameid/367520 >/dev/null 2>&1')
    for _ in range(60):
        time.sleep(2)
        if game_states():
            break
    else:
        sys.exit('game never started')
    time.sleep(12)  # window map + first render
    capture(1, 'baseline: game running')

    seq = [
        ('tap', 0.15, 'in-game tap -> expect Steam menu opens over game'),
        ('tap', 0.15, 'tap again -> expect menu closes, game visible'),
        ('hold', 1.2, 'hold -> expect freeze + Kodi on top (RISK: Steam raises menu over Kodi)'),
        ('tap', 0.15, 'tap on Kodi -> expect resume, game focused (RISK: Steam menu toggles over game)'),
        ('hold', 1.2, 'hold -> expect freeze + Kodi again'),
        ('hold', 1.2, 'hold while frozen -> expect stay on Kodi (leave-bp branch)'),
        ('tap', 0.15, 'tap -> expect resume again'),
    ]
    for i, (kind, secs, label) in enumerate(seq, start=2):
        print(f'--- step {i}: {kind} ({label})')
        press(ds_fd, secs)
        capture(i, f'{kind}: {label}')

    print('cleanup: game-launch quit')
    sh('/home/ds2000/.local/bin/game-launch quit')
    time.sleep(6)
    capture(9, 'after quit')

    ds_emit(ds_fd, 0)
    try:
        fcntl.ioctl(ds_fd, UI_DEV_DESTROY)
    except OSError:
        pass
    os.close(ds_fd)
    vpad('quit')
    print('done')


if __name__ == '__main__':
    main()

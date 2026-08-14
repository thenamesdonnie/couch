#!/usr/bin/env python3
"""XTEST input injection for the couch screen view: click at a fractional
position, type text, or press a named key. Same python-xlib approach the
Steam sign-in used; user-level, no sudo, works on whatever owns :0.

Usage:
  xinput.py click <xfrac> <yfrac> [button]
  xinput.py type <text...>
  xinput.py key <name>        (Return, BackSpace, Tab, Escape, Up, ...)
  xinput.py geometry

click prints JSON including "text": whether the spot looks like a text field,
judged by the cursor the app shows once the pointer is hovered there - an
I-beam is much taller than it is wide. The phone uses that to raise its
keyboard only when typing makes sense.
"""
import json
import sys
import time

from Xlib import protocol

from Xlib import X, XK, display
from Xlib.ext import xtest

# Characters that need shift on a GB/US layout, keyed to their base keysym name.
SHIFTED = {
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7',
    '*': '8', '(': '9', ')': '0', '_': 'minus', '+': 'equal', '{': 'bracketleft',
    '}': 'bracketright', '|': 'backslash', ':': 'semicolon', '"': 'apostrophe',
    '<': 'comma', '>': 'period', '?': 'slash', '~': 'grave',
}
NAMED = {
    ' ': 'space', '-': 'minus', '=': 'equal', '[': 'bracketleft',
    ']': 'bracketright', '\\': 'backslash', ';': 'semicolon', "'": 'apostrophe',
    ',': 'comma', '.': 'period', '/': 'slash', '`': 'grave', '\n': 'Return',
    '\t': 'Tab',
}


def keycode_for(d, char):
    if char in SHIFTED:
        name, shift = SHIFTED[char], True
    elif char in NAMED:
        name, shift = NAMED[char], False
    elif char.isalpha():
        name, shift = char.lower(), char.isupper()
    else:
        name, shift = char, False
    keysym = XK.string_to_keysym(name)
    if keysym == 0:
        return None, False
    code = d.keysym_to_keycode(keysym)
    return (code or None), shift


def press_key(d, code, shift=False):
    shift_code = d.keysym_to_keycode(XK.string_to_keysym('Shift_L'))
    if shift:
        xtest.fake_input(d, X.KeyPress, shift_code)
    xtest.fake_input(d, X.KeyPress, code)
    xtest.fake_input(d, X.KeyRelease, code)
    if shift:
        xtest.fake_input(d, X.KeyRelease, shift_code)
    d.sync()


def main():
    cmd = sys.argv[1]
    d = display.Display()
    root = d.screen().root

    if cmd == 'geometry':
        g = root.get_geometry()
        print(f'{g.width} {g.height}')
        return

    if cmd == 'kodiwin':
        # Kodi's fullscreen GL window. Grabbing it directly is silent, unlike
        # Kodi's own screenshot action which pops a shutter every frame.
        sw = d.screen().width_in_pixels
        sh = d.screen().height_in_pixels

        def find(w):
            try:
                for c in w.query_tree().children:
                    try:
                        if (c.get_wm_name() or '') == 'Kodi':
                            a = c.get_attributes()
                            g = c.get_geometry()
                            if a.map_state == X.IsViewable and g.width >= sw * 0.8:
                                return c.id
                    except Exception:
                        pass
                    r = find(c)
                    if r:
                        return r
            except Exception:
                pass
            return None

        wid = find(root)
        if wid:
            print(hex(wid))
        else:
            sys.exit('kodi window not found')
        return

    if cmd == 'gamewin':
        # The game's OWN window, by the same rule game-launch's focus_game
        # uses to decide what to raise: a window whose _NET_WM_PID is one of
        # the game's processes, or whose class is the steam_app_<appid> Proton
        # stamps on it (which survives even when the window's pid belongs to a
        # wine helper nobody pgrepped). Biggest match wins - games open splash
        # and helper windows too. Falls back to the biggest non-furniture
        # window for native games with unhelpful window pids.
        #
        #   xinput.py gamewin [--any-state] [pid ...]
        #
        # --any-state drops the viewable requirement: a suspended game's window
        # gets iconified (see `iconify` below) to release the pointer grab it
        # was holding, and the resume path still has to find it to map it back.
        # Matching is otherwise identical - geometry stays readable while a
        # window is unmapped, so the biggest-match rule is unchanged.
        #
        # Callers: pause-snap, which grabs this window while the game is
        # frozen; game-launch and pad-home-watcher, either side of a suspend.
        # Printing an id costs nothing and touches nothing.
        wanted = set()
        any_state = False
        for a in sys.argv[2:]:
            if a == '--any-state':
                any_state = True
                continue
            try:
                wanted.add(int(a))
            except ValueError:
                pass
        NET_PID = d.intern_atom('_NET_WM_PID')
        NOT_GAMES = {'Kodi', 'xfdesktop', 'xfce4-panel', 'steamwebhelper'}
        best = [None]       # (area, id) of a positive match
        fallback = [None]   # ...of the biggest thing that is not furniture

        def scan(w):
            try:
                children = w.query_tree().children
            except Exception:
                return
            for c in children:
                try:
                    if any_state or c.get_attributes().map_state == X.IsViewable:
                        g = c.get_geometry()
                        area = g.width * g.height
                        try:
                            p = c.get_full_property(NET_PID, 0)
                            pid = int(p.value[0]) if p else 0
                        except Exception:
                            pid = 0
                        try:
                            cls = (c.get_wm_class() or ('', ''))[0] or ''
                        except Exception:
                            cls = ''
                        # 'gamescope' counts as a positive match for the same
                        # reason steam_app does: under the stage-3 wrap the
                        # game's visible window is gamescope's SDL window, and
                        # its _NET_WM_PID is gamescope's own pid - the PARENT
                        # of the game tree, which game-pids (descendants of
                        # the game's processes) never contains. Only game
                        # wraps run gamescope on this box.
                        if ((pid and pid in wanted) or cls.startswith('steam_app')
                                or cls == 'gamescope'):
                            if best[0] is None or area > best[0][0]:
                                best[0] = (area, c.id)
                        elif (cls and cls not in NOT_GAMES
                              and g.width >= 600 and g.height >= 400):
                            if fallback[0] is None or area > fallback[0][0]:
                                fallback[0] = (area, c.id)
                except Exception:
                    pass
                scan(c)

        scan(root)
        hit = best[0] or fallback[0]
        if not hit:
            sys.exit('game window not found')
        print(hex(hit[1]))
        return

    if cmd == 'windows':
        # The managed top-level windows (EWMH _NET_CLIENT_LIST), minus furniture
        # (the desktop, panels), each with its title - so the phone can offer a
        # switcher.
        NET_CLIENT_LIST = d.intern_atom('_NET_CLIENT_LIST')
        NET_WM_NAME = d.intern_atom('_NET_WM_NAME')
        NET_WM_TYPE = d.intern_atom('_NET_WM_WINDOW_TYPE')
        TYPE_DESKTOP = d.intern_atom('_NET_WM_WINDOW_TYPE_DESKTOP')
        TYPE_DOCK = d.intern_atom('_NET_WM_WINDOW_TYPE_DOCK')
        prop = root.get_full_property(NET_CLIENT_LIST, 0)
        out = []
        for wid in (prop.value if prop else []):
            try:
                w = d.create_resource_object('window', wid)
                types = w.get_full_property(NET_WM_TYPE, 0)
                if types and (TYPE_DESKTOP in types.value or TYPE_DOCK in types.value):
                    continue
                nm = ''
                p = w.get_full_property(NET_WM_NAME, 0)
                if p and p.value:
                    nm = p.value.decode('utf-8', 'replace') if isinstance(p.value, bytes) else str(p.value)
                if not nm:
                    nm = (w.get_wm_name() or '')
                if not nm:
                    continue
                try:
                    cls = (w.get_wm_class() or ('', ''))[0]
                except Exception:
                    cls = ''
                # map_state 2 = IsViewable: the compositor holds real pixels
                # for it (even obscured), so a live thumbnail capture works.
                # Iconified/unmapped windows would capture black.
                try:
                    viewable = w.get_attributes().map_state == 2
                except Exception:
                    viewable = False
                out.append({'id': hex(wid), 'title': nm, 'kodi': nm == 'Kodi',
                            'cls': cls, 'mapped': viewable})
            except Exception:
                pass
        print(json.dumps(out))
        return

    def send_root(win, atom_name, data):
        atom = d.intern_atom(atom_name)
        ev = protocol.event.ClientMessage(window=win, client_type=atom, data=(32, data))
        root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.sync()

    if cmd == 'activate':
        wid = int(sys.argv[2], 16)
        w = d.create_resource_object('window', wid)
        # Ask the window manager (xfwm4) to raise + focus it properly. Source 2
        # is "pager", which is also what makes xfwm4 DEICONIFY the window - so
        # this is the exact undo of the `iconify` below, and on a window that
        # was never iconified it is just a raise.
        send_root(w, '_NET_ACTIVE_WINDOW', [2, 0, 0, 0, 0])
        print('activated')
        return

    if cmd == 'iconify':
        # ICCCM WM_CHANGE_STATE -> IconicState (3).
        #
        # Why a suspend needs this: a SIGSTOPped game cannot answer the X
        # server, so an active pointer grab it held at the moment it froze
        # stays held. Its cursor sprite sits on top of Kodi and the phone's
        # XTEST clicks are swallowed by the frozen client. X releases a grab
        # when the grab window stops being viewable, so unmapping the window is
        # what actually frees the pointer - raising Kodi over it does not.
        # `activate` maps it back on resume.
        wid = int(sys.argv[2], 16)
        w = d.create_resource_object('window', wid)
        send_root(w, 'WM_CHANGE_STATE', [3, 0, 0, 0, 0])
        print('iconified')
        return

    if cmd == 'showdesktop':
        on = 1 if (len(sys.argv) < 3 or sys.argv[2] != 'off') else 0
        send_root(root, '_NET_SHOWING_DESKTOP', [on, 0, 0, 0, 0])
        print('showdesktop', on)
        return

    if cmd == 'click':
        xf, yf = float(sys.argv[2]), float(sys.argv[3])
        button = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        g = root.get_geometry()
        x, y = int(xf * g.width), int(yf * g.height)
        xtest.fake_input(d, X.MotionNotify, x=x, y=y)
        d.sync()
        # Let the app react to the hover, then read what cursor it chose.
        time.sleep(0.15)
        is_text = False
        try:
            d.xfixes_query_version()
            img = d.xfixes_get_cursor_image(root)
            opaque = [(i % img.width, i // img.width)
                      for i, p in enumerate(img.cursor_image)
                      if (p >> 24) & 0xFF > 128]
            if opaque:
                xs = [p[0] for p in opaque]
                ys = [p[1] for p in opaque]
                w = max(xs) - min(xs) + 1
                h = max(ys) - min(ys) + 1
                is_text = h >= 12 and w <= max(8, h * 0.45)
        except Exception:
            pass
        xtest.fake_input(d, X.ButtonPress, button)
        d.sync()
        time.sleep(0.05)
        xtest.fake_input(d, X.ButtonRelease, button)
        d.sync()
        print(json.dumps({'x': x, 'y': y, 'text': is_text}))
        return

    if cmd == 'type':
        text = ' '.join(sys.argv[2:])
        for ch in text:
            code, shift = keycode_for(d, ch)
            if code:
                press_key(d, code, shift)
                time.sleep(0.02)
        print(f'typed {len(text)} chars')
        return

    if cmd == 'key':
        keysym = XK.string_to_keysym(sys.argv[2])
        code = d.keysym_to_keycode(keysym)
        if not code:
            sys.exit(f'unknown key {sys.argv[2]}')
        press_key(d, code)
        print(f'pressed {sys.argv[2]}')
        return

    sys.exit('unknown command')


if __name__ == '__main__':
    main()

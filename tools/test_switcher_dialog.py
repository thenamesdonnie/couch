#!/usr/bin/env python3
"""Unit tests for the switcher dialog's input contract (default.py + the XML).

Born from the 6 Aug live bug: the list was control id 3, which WindowXML (the
C++ class behind every WindowXMLDialog) claims as its internal "sort by"
button - it eats GUI_MSG_CLICKED from ids 2/3/4 (and 12, and containers
50-59) before python's onClick runs, so every select press vanished with
"WindowXML: Internal sort button not implemented" in kodi.log and the dialog
could only ever answer "cancelled". These tests pin the id contract so a
renumber can never wander back into a reserved range, and drive onInit /
onClick / onAction against a stub xbmcgui so the focus and answer paths are
proven without Kodi.

No Kodi, no live paths: xbmc/xbmcgui/xbmcaddon are stubbed before default.py
loads, the stub Window says the re-entry latch is already held so main() (and
its localhost HTTP calls) never runs, and the one file this writes (the
py_compile check) goes to pytest's tmp_path.

Run:  couchd/.venv/bin/pytest tools/test_switcher_dialog.py -q
"""
import importlib.machinery
import importlib.util
import os
import py_compile
import sys
import types
import xml.dom.minidom

ADDON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                         'kodi-addons', 'script.couch.switcher')
DEFAULT_PY = os.path.join(ADDON_DIR, 'default.py')
DIALOG_XML = os.path.join(ADDON_DIR, 'resources', 'skins', 'Default',
                          '1080i', 'script-couch-switcher.xml')

# Ids WindowXML::OnMessage handles itself (and so never reach onClick):
# 2/3/4 the old view/sort buttons, 12 the files label, 50-59 the
# CGUIMediaWindow container pool. From xbmc/interfaces/legacy/WindowXML.cpp -
# "Handle Sort/View internally. Scripters shouldn't use ID 2, 3 or 4."
WINDOWXML_RESERVED = {2, 3, 4, 12} | set(range(50, 60))


# -- stub Kodi, load default.py ----------------------------------------------

class StubList:
    """The one control default.py fetches, remembering what was done to it."""

    def __init__(self):
        self.items = []
        self.resets = 0
        self.selected = None

    def reset(self):
        self.resets += 1
        self.items = []

    def addItems(self, items):
        self.items.extend(items)

    def selectItem(self, pos):
        self.selected = pos

    def getSelectedPosition(self):
        return self.selected


class StubWindowXMLDialog:
    def __init__(self, *_a, **_k):
        self.list = StubList()
        self.bar = StubList()          # the power bar, control 9010
        self.fetched_ids = []
        self.focus_calls = []
        self.props = {}
        self.closed = 0

    def getControl(self, control_id):
        self.fetched_ids.append(control_id)
        return self.bar if control_id == dflt.POWER_ID else self.list

    def setFocusId(self, control_id):
        self.focus_calls.append(control_id)

    def setProperty(self, key, value):
        self.props[key] = value

    def doModal(self):
        pass

    def close(self):
        self.closed += 1


class StubListItem:
    def __init__(self, label=''):
        self.label = label
        self.art = {}

    def setArt(self, art):
        self.art.update(art)


class StubHomeWindow:
    # getProperty says the re-entry latch is held, so default.py's module-level
    # tail logs "already open" and returns instead of running main().
    def __init__(self, _win_id=None):
        pass

    def getProperty(self, _key):
        return '1'

    def setProperty(self, _key, _value):
        pass

    def clearProperty(self, _key):
        pass


class StubAddon:
    def getAddonInfo(self, _key):
        return ADDON_DIR

    def getSettingBool(self, _key):
        return True


def _install_stubs():
    xbmc = types.ModuleType('xbmc')
    xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 3
    xbmc.log = lambda _msg, _level=1: None
    # What main() asked Kodi to do. The power row goes over JSON-RPC, not
    # executebuiltin: the builtin is dispatched against a GUI still tearing
    # down the dialog and is lost (observed live - the log line printed and
    # the window never opened).
    xbmc.builtins = []
    xbmc.executebuiltin = lambda cmd: xbmc.builtins.append(cmd)
    xbmc.rpc = []
    xbmc.executeJSONRPC = lambda payload: (xbmc.rpc.append(payload) or
                                           '{"result":"OK"}')

    xbmcgui = types.ModuleType('xbmcgui')
    xbmcgui.WindowXMLDialog = StubWindowXMLDialog
    xbmcgui.ListItem = StubListItem
    xbmcgui.Window = StubHomeWindow
    xbmcgui.Dialog = None          # only reached by main(), which never runs

    xbmcaddon = types.ModuleType('xbmcaddon')
    xbmcaddon.Addon = StubAddon

    sys.modules['xbmc'] = xbmc
    sys.modules['xbmcgui'] = xbmcgui
    sys.modules['xbmcaddon'] = xbmcaddon


_install_stubs()
_spec = importlib.util.spec_from_loader(
    'couch_switcher_default',
    importlib.machinery.SourceFileLoader('couch_switcher_default', DEFAULT_PY))
dflt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dflt)


def make_dialog(rows=({'title': 'Hollow Knight · paused'},
                      {'title': 'Big Picture'})):
    dlg = dflt.SwitcherDialog('script-couch-switcher.xml', ADDON_DIR,
                              'Default', '1080i')
    dlg.rows = rows
    dlg.appid = ''      # no live session: the frame watch stays inert
    return dlg


class Action:
    def __init__(self, action_id):
        self._id = action_id

    def getId(self):
        return self._id


# -- the id contract, statically ----------------------------------------------

def _dom():
    return xml.dom.minidom.parse(DIALOG_XML)


def _control_ids(dom):
    return [int(c.getAttribute('id')) for c in dom.getElementsByTagName(
        'control') if c.getAttribute('id')]


def _lists(dom):
    return [c for c in dom.getElementsByTagName('control')
            if c.getAttribute('type') == 'list']


def _list_control(dom, want=None):
    """The switch row by default; the power bar when asked for."""
    want = dflt.LIST_ID if want is None else want
    for c in _lists(dom):
        if int(c.getAttribute('id')) == want:
            return c
    raise AssertionError('no list with id %d' % want)


def test_xml_is_well_formed_and_has_exactly_the_two_lists():
    # Two since 8 Aug: the switch row, and the power bar above it. Anything
    # else appearing here is a control the python does not know about.
    ids = sorted(int(c.getAttribute('id')) for c in _lists(_dom()))
    assert ids == sorted([dflt.LIST_ID, dflt.POWER_ID])


def test_no_control_id_is_reserved_by_windowxml():
    # Id 3 was the live "cannot select a row" bug; 50-59 would be worse.
    for control_id in _control_ids(_dom()):
        assert control_id not in WINDOWXML_RESERVED, \
            'control id %d is claimed by WindowXML itself' % control_id


def test_python_xml_and_defaultcontrol_agree_on_the_list_id():
    dom = _dom()
    assert int(_list_control(dom).getAttribute('id')) == dflt.LIST_ID
    default = dom.getElementsByTagName('defaultcontrol')
    assert len(default) == 1
    assert int(default[0].firstChild.data) == dflt.LIST_ID
    assert default[0].getAttribute('always') == 'true'


def test_navigation_only_ever_lands_on_a_real_list():
    # The stick must never walk focus onto a non-focusable control and go
    # dead. Every direction on both lists names one of the two lists - and
    # the only crossing between them is the switch row's UP and the power
    # bar's DOWN, so the bar is never reachable sideways.
    dom = _dom()
    valid = {dflt.LIST_ID, dflt.POWER_ID}
    expect = {(dflt.LIST_ID, 'onup'): dflt.POWER_ID,
              (dflt.POWER_ID, 'ondown'): dflt.LIST_ID}
    for which in (dflt.LIST_ID, dflt.POWER_ID):
        lst = _list_control(dom, which)
        for tag in ('onup', 'ondown', 'onleft', 'onright'):
            nodes = lst.getElementsByTagName(tag)
            assert nodes, 'list %d has no <%s>' % (which, tag)
            target = int(nodes[0].firstChild.data)
            assert target in valid, (which, tag, target)
            assert target == expect.get((which, tag), which), (which, tag, target)


def test_default_py_compiles(tmp_path):
    py_compile.compile(DEFAULT_PY, cfile=str(tmp_path / 'default.pyc'),
                       doraise=True)


# -- onInit: fill once, focus always ------------------------------------------

def test_oninit_fills_the_list_and_focuses_it():
    dlg = make_dialog()
    dlg.onInit()
    assert [li.label for li in dlg.list.items] == \
        ['Hollow Knight · paused', 'Big Picture', 'Cancel']
    assert dlg.list.selected == 0
    assert dlg.fetched_ids == [dflt.LIST_ID, dflt.POWER_ID]
    assert dlg.closed == 0


def test_oninit_fills_the_power_bar_from_the_action_table():
    """The labels live beside the actions they fire, so the bar cannot drift
    out of step with what selecting it does."""
    dlg = make_dialog()
    dlg.onInit()
    assert [li.label for li in dlg.bar.items] == \
        ['Quit game', 'Controller off', 'Controller + TV off']
    assert [a for _, a in dflt.POWER_ACTIONS] == ['quit', 'pad_off', 'all_off']


def test_focus_starts_on_the_switch_row_never_the_power_bar():
    """The stick must not open sitting on something that turns the TV off."""
    dlg = make_dialog()
    dlg.onInit()
    assert dlg.focus_calls == [dflt.LIST_ID]


def test_a_broken_power_bar_never_costs_the_switcher():
    """No bar is a switcher without power options; a switcher that failed to
    open is the room stuck in a game. Never trade the second for the first."""
    dlg = make_dialog()
    real = dlg.getControl

    def boom(control_id):
        if control_id == dflt.POWER_ID:
            raise RuntimeError('no such control')
        return real(control_id)
    dlg.getControl = boom
    dlg.onInit()
    assert [li.label for li in dlg.list.items][-1] == 'Cancel'
    assert dlg.focus_calls == [dflt.LIST_ID]
    assert dlg.closed == 0


def test_clicking_the_power_bar_answers_with_an_action_not_an_index():
    """A row index and a power action must never be confusable - "turn the TV
    off" cannot be allowed to arrive looking like "switch to row 2"."""
    dlg = make_dialog()
    dlg.onInit()
    dlg.bar.selected = 2
    dlg.onClick(dflt.POWER_ID)
    assert dlg.power == 'all_off'
    assert dlg.choice == -1          # untouched: nothing was switched to
    assert dlg.closed == 1


def test_clicking_the_switch_row_leaves_power_empty(dlg=None):
    dlg = make_dialog()
    dlg.onInit()
    dlg.list.selected = 1
    dlg.onClick(dflt.LIST_ID)
    assert dlg.choice == 1
    assert dlg.power == ''



def test_reinit_refocuses_without_duplicating_rows():
    # A re-init (skin reload, resolution change) redraws the window with
    # nothing focused; the guard must skip the rebuild but NOT the focus, or
    # the dialog reopens deaf to the pad.
    dlg = make_dialog()
    dlg.onInit()
    dlg.onInit()
    assert [li.label for li in dlg.list.items] == \
        ['Hollow Knight · paused', 'Big Picture', 'Cancel']   # built once
    assert dlg.focus_calls == [dflt.LIST_ID, dflt.LIST_ID]    # focused twice


# -- the answer contract -------------------------------------------------------

def test_click_on_the_list_answers_with_the_row_and_closes():
    dlg = make_dialog()
    dlg.onInit()
    dlg.list.selectItem(1)
    dlg.onClick(dflt.LIST_ID)
    assert dlg.choice == 1
    assert dlg.closed == 1
    assert dlg._frame_stop.is_set()     # close() must stop the frame poll


def test_click_elsewhere_changes_nothing():
    dlg = make_dialog()
    dlg.onInit()
    dlg.onClick(dflt.LIST_ID + 1)
    assert dlg.choice == -1
    assert dlg.closed == 0


def test_back_action_cancels():
    dlg = make_dialog()
    dlg.onInit()
    for action_id in (dflt.ACTION_PREVIOUS_MENU, dflt.ACTION_NAV_BACK):
        dlg = make_dialog()
        dlg.onInit()
        dlg.onAction(Action(action_id))
        assert dlg.choice == -1
        assert dlg.closed == 1
        assert dlg._frame_stop.is_set()


def test_unrelated_action_leaves_the_dialog_open():
    dlg = make_dialog()
    dlg.onInit()
    dlg.onAction(Action(7))     # ACTION_SELECT_ITEM: the base class's business
    assert dlg.closed == 0


# -- the power row (added 8 Aug 2026) -----------------------------------------
# The switcher is the only surface reachable from inside a game: at home a hold
# already opens the power screen, but in a game the hold is Steam's menu, so
# powering off meant suspending first and then holding. The row closes that
# gap - and it ROUTES rather than acting, because a second power path with its
# own copy of the quit-the-game-first save grace is how one of them ends up
# killing a game without it.

import json                                                     # noqa: E402
import xbmc as _xbmc                                            # noqa: E402


def _run_main(windows, pick):
    """main() over a fake server and a fake user, capturing both outcomes."""
    activated = []
    _xbmc.builtins.clear()
    _xbmc.rpc.clear()
    orig = (dflt.get_windows, dflt.select_window, dflt.activate, dflt.notify)
    dflt.get_windows = lambda: windows
    dflt.select_window = lambda rows: (_run_main.rows.append(rows) or
                                       pick(rows))
    dflt.activate = lambda wid: activated.append(wid)
    dflt.notify = lambda *_a, **_k: None
    _run_main.rows = []
    try:
        dflt.main()
    finally:
        (dflt.get_windows, dflt.select_window, dflt.activate,
         dflt.notify) = orig
    return {'rows': _run_main.rows[0] if _run_main.rows else [],
            'activated': activated, 'builtins': list(_xbmc.builtins),
            'rpc': list(_xbmc.rpc)}


WINS = [{'id': '0x1', 'title': 'Big Picture', 'kodi': False},
        {'id': '0x2', 'title': 'Kodi', 'kodi': True}]


def test_the_switch_row_holds_only_real_destinations():
    """Power moved OUT of this row on 8 Aug and into its own bar above it, so
    a destination list is destinations again. A power entry down here would
    now be a second way to do the same thing, one keypress from the row the
    stick opens on."""
    out = _run_main(WINS, pick=lambda rows: -1)
    assert [r['title'] for r in out['rows']] == ['Big Picture']
    assert not any(r.get('power') for r in out['rows'])


def test_a_power_action_dispatches_to_tvpoweroff_and_switches_nothing():
    """The switcher holds no power logic: it names an action and hands it to
    script.tvpoweroff, which is where "quit the game politely first" lives.
    Over JSON-RPC, not executebuiltin - a builtin issued while this dialog is
    tearing down is silently lost (observed 8 Aug)."""
    out = _run_main(WINS, pick=lambda rows: ('power', 'all_off'))
    assert len(out['rpc']) == 1
    sent = json.loads(out['rpc'][0])
    assert sent['method'] == 'Addons.ExecuteAddon'
    assert sent['params'] == {'addonid': 'script.tvpoweroff',
                              'params': ['all_off']}
    assert out['activated'] == [], 'a power action switched a window'
    assert out['builtins'] == []


def test_every_bar_action_is_one_tvpoweroff_implements():
    """The labels are ours; the actions must be its. A typo here would be a
    silent no-op on the one menu that turns the television off."""
    import os
    src = open(os.path.join(os.path.expanduser('~'), 'couch', 'kodi-addons',
                            'script.tvpoweroff', 'default.py')).read()
    for _label, action in dflt.POWER_ACTIONS:
        assert '"%s":' % action in src, action


def test_power_does_not_appear_when_there_is_nothing_to_switch_to():
    """With no destinations the sheet does not open at all, exactly as
    before - and it should not start opening just to offer power, because a
    hold at home already reaches the same screen in one gesture."""
    out = _run_main([{'id': '0x2', 'title': 'Kodi', 'kodi': True}],
                    pick=lambda rows: 0)
    assert out['rows'] == []
    assert out['builtins'] == [] and out['activated'] == []

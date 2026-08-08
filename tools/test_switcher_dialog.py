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
        self.fetched_ids = []
        self.focus_calls = []
        self.props = {}
        self.closed = 0

    def getControl(self, control_id):
        self.fetched_ids.append(control_id)
        return self.list

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


def _list_control(dom):
    lists = [c for c in dom.getElementsByTagName('control')
             if c.getAttribute('type') == 'list']
    assert len(lists) == 1
    return lists[0]


def test_xml_is_well_formed_and_has_one_list():
    _list_control(_dom())    # minidom.parse raising IS the failure


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


def test_list_navigation_stays_on_the_list():
    # onup/ondown/onleft/onright name the list itself: the stick can never
    # walk focus onto a non-focusable control and go dead.
    lst = _list_control(_dom())
    for tag in ('onup', 'ondown', 'onleft', 'onright'):
        nodes = lst.getElementsByTagName(tag)
        assert nodes, 'list has no <%s>' % tag
        assert int(nodes[0].firstChild.data) == dflt.LIST_ID


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
    assert dlg.fetched_ids == [dflt.LIST_ID]
    assert dlg.focus_calls == [dflt.LIST_ID]
    assert dlg.closed == 0


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


def test_power_is_offered_last_after_every_real_destination():
    """Index 0 is where the stick starts; power is the furthest thing from
    it, and Cancel still sits beyond it as the dismiss."""
    out = _run_main(WINS, pick=lambda rows: -1)
    assert [r['title'] for r in out['rows']] == ['Big Picture', 'Power']


def test_picking_power_opens_the_power_screen_and_switches_nothing():
    out = _run_main(WINS, pick=lambda rows: len(rows) - 1)
    assert len(out['rpc']) == 1
    sent = json.loads(out['rpc'][0])
    assert sent['method'] == 'GUI.ActivateWindow'
    assert sent['params'] == {'window': 'shutdownmenu'}
    assert out['activated'] == [], 'the switcher tried to switch to a sentinel'
    # and NOT the builtin, which was tried first and silently did nothing
    assert out['builtins'] == []


def test_the_power_row_never_reaches_the_server():
    """Every other row's id is an X window id posted straight to the couch
    server. The sentinel must never get that far - it is not a window."""
    out = _run_main(WINS, pick=lambda rows: 0)
    assert out['activated'] == ['0x1']
    assert dflt.POWER_ID not in out['activated']
    assert out['builtins'] == []


def test_power_does_not_appear_when_there_is_nothing_to_switch_to():
    """With no destinations the sheet does not open at all, exactly as
    before - and it should not start opening just to offer power, because a
    hold at home already reaches the same screen in one gesture."""
    out = _run_main([{'id': '0x2', 'title': 'Kodi', 'kodi': True}],
                    pick=lambda rows: 0)
    assert out['rows'] == []
    assert out['builtins'] == [] and out['activated'] == []


def test_the_power_row_is_not_mistaken_for_a_paused_game():
    """session_appid() walks the same rows to find the freeze-frame's appid;
    a row with no `paused` key must be invisible to it."""
    rows = [{'id': '0x1', 'title': 'Bloodborne · paused', 'paused': True,
             'cls': 'steam_app_367520'},
            {'id': dflt.POWER_ID, 'title': 'Power', 'power': True}]
    assert dflt.pausedframe.session_appid(rows, fallback='') == '367520'

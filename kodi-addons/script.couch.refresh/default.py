# Run Container.Refresh and get out. Nothing else belongs in here.
#
# Why an addon at all: Kodi's JSON-RPC exposes no "run this builtin" method
# (Input.ExecuteAction only reaches the keymap action list, which has no
# container refresh), and Addons.ExecuteAddon is the one remote door into
# Python that can. So this is the door - deliberately dumb, so that anything
# clever stays in the caller, ~/couch/tools/kodi-refresh-games, which decides
# WHEN a refresh is safe (only while the home screen is showing).
#
# Container.Refresh acts on the ACTIVE container only. On the home screen that
# is whatever widget currently has focus, so this is best-effort by nature: it
# is how a paused game's freeze-frame tile appears without the player having to
# leave the Games row and come back, and when it does not apply, nothing
# happens and the old behaviour stands.
import xbmc

xbmc.log("couch.refresh: Container.Refresh", xbmc.LOGINFO)
xbmc.executebuiltin("Container.Refresh")

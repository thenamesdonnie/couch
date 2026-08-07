# script.copacetic.helper local patches (re-apply after any addon update)

The helper addon lives only in ~/.kodi/addons and updates would revert:
1. games.py -> resources/lib/plugin/games.py (the whole file is ours):
   Games row listing + launch handoff + pause-snap art + the composed
   square tiles (~/.local/share/game-tiles/composed, hero art centre-crop
   with Steam's logo.png pasted dead centre - "smart centering", 8 Aug).
2. _get_skindir in resources/lib/service/monitor.py must accept
   'skin.couch' (one-line gate, 7 Aug).
3. <reuselanguageinvoker>true</reuselanguageinvoker> in addon.xml metadata
   (the Py3.12 teardown mitigation, 1 Aug).
Bump the addon version + kodi-send UpdateLocalAddons after re-applying.
Current local version: 1.1.6.6.

# script.embuary.helper local patches (re-apply after any addon update)

1. plugin_content.py getnextup: both episode queries exclude in-progress
   episodes ({'field': 'inprogress', 'operator': 'false'}) so a half-watched
   episode lives ONLY in the Continue row, and Next up shows the episode
   AFTER it (8 Aug 2026, Stagelight Library page).
2. <reuselanguageinvoker>true</reuselanguageinvoker> in addon.xml metadata
   (1 Aug 2026, the Py3.12 teardown mitigation).
Bump the version + kodi-send UpdateLocalAddons after re-applying.
Current local version: 2.0.8.2.

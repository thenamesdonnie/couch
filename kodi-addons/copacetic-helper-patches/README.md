# script.copacetic.helper local patches (re-apply after any addon update)

**Do not re-apply these by hand any more: `tools/deploy-addons` does the
file drops and reports the two hand-edits.** Since the Kodi 21 migration
there are TWO profiles to deploy into (`~/.kodi` and
`~/.var/app/tv.kodi.Kodi/data`), so `tools/deploy-addons --profile both`.

The helper addon lives only in the Kodi profile and updates would revert:
1. games.py -> resources/lib/plugin/games.py (the whole file is ours):
   Games row listing + launch handoff + pause-snap art + the composed
   square tiles (~/.local/share/game-tiles/composed, hero art centre-crop
   with Steam's logo.png pasted dead centre - "smart centering", 8 Aug).
2. _get_skindir in resources/lib/service/monitor.py must accept
   'skin.couch' (one-line gate, 7 Aug).
3. <reuselanguageinvoker>true</reuselanguageinvoker> in addon.xml metadata
   (the Py3.12 teardown mitigation, 1 Aug). On Kodi 21 this is the very bug
   the migration exists to fix - RE-DECIDE rather than re-applying by
   reflex (docs/kodi21-flatpak-migration.md has the retirement criterion).
4. couchhost.py -> resources/lib/plugin/couchhost.py. games.py imports it
   from beside itself; it is the sandbox crossing for game-launch and the
   /tmp session flags, and a no-op outside a Flatpak. Byte-identical to
   ../couchhost/couchhost.py - tools/test_couchhost.py fails if it drifts.
Bump the addon version + kodi-send UpdateLocalAddons after re-applying.
Current local version: 1.1.8.8 (check the deployed addon.xml, not this line - it
 has drifted before). Kodi addon updates are set to NOTIFY-ONLY precisely so
 an upstream release cannot silently overwrite these patches; see
 docs/audits/kodi21-migration-2026-08.md.

# Kodi 21 Flatpak migration: post-cutover audit (8 Aug 2026)

Scope: everything that shipped in the Kodi 20 -> 21 migration the same
evening, and the surfaces it touched — `tools/kodi21-migrate`,
`tools/deploy-addons`, `couchhost`, `couchd/kodiprofile.py` +
`server/kodiprofile.js`, `~/.local/bin/kodi-tv`, the `skin.couch` Omega
changes, and the two profiles themselves (`~/.kodi` = apt Kodi 20, the
rollback; `~/.var/app/tv.kodi.Kodi/data` = Kodi 21, live).

Production = the living-room TV, now running Kodi 21.3-Omega. It stayed green
throughout: Kodi on Home with `skin.couch`, library 88 films / 30 shows, the
phone app serving, Bloodborne still suspended, the set never left standby.

Prior art read first: `docs/audits/console-robustness-2026-08.md` (grading
convention taken from it), `docs/kodi21-flatpak-migration.md` (the plan being
audited).

**Every [A] in this report is a bug introduced by the migration itself, hours
earlier.** That is the honest headline: the risky code was the new code, and
three of the four were in the one file whose job is to be re-runnable.

## Findings

| # | Finding | Grade | Outcome |
|---|---|---|---|
| 1 | **`deploy-addons` would replace the frozen rollback skin with a symlink to the 5.17.0 repo.** `~/.kodi/addons/skin.couch` is a real, frozen `xbmc.gui 5.16.0` directory — the only reason a rollback to Kodi 20 gets a skin at all. `deploy_link()` saw "not a symlink", moved it aside to `.replaced`, and linked the repo in. Kodi does not load `.replaced`, so the parachute became Estuary. Reachable by `--profile both`, **which the patch-set README tells you to run.** | A | FIXED: a real directory is never replaced, it is reported. `tools/test_deploy_addons.py` (8 tests) |
| 2 | **A second `profile` run could write the frozen Nexus skin back into the git repo.** After `freeze-skin` the source (`~/.kodi/addons/skin.couch`) is a real directory while the target is a symlink into the checkout — so the copy follows it and writes 5.16.0 over the repo's 5.17.0, the version Kodi 21 then refuses. It was skipped on the live box only because the two `addon.xml` files happen to be the same *size* and the repo copy was newer. Luck, not a guard. | A | FIXED: `addons/skin.couch` added to `PROFILE_SKIP` (owned by `freeze-skin`). Test + verified on the live tree with a before/after checksum of the whole repo skin |
| 3 | **The copy's skip test was `target newer AND same size`, which inverts the rule for exactly the files that matter.** Anything Kodi 21 had rewritten to a *different length* failed the size half and was overwritten with the older apt copy. **This one fired for real during the audit**: `profile --force` reverted `Addons33.db`, taking the Omega repository index with it (back to the Nexus index, which is what made the first controller-profile install fail). | A | FIXED: a newer target always wins, whatever its size. Damage repaired (`UpdateAddonRepos` → index back to 3.4.0/Omega), `pragma integrity_check` = ok, no errors in the log, all 13 addons still enabled. Test pins both a settings file and a database that grew |
| 4 | **`profile` had no guard against copying the old profile forward over the LIVE one.** `--force` only ever meant "Kodi may be running", which is a much smaller claim than "it is safe to revert everything Kodi 21 has written". Finding 3 is what this absence costs. | A | FIXED: refuses when `kodi-flavour-active` is `flatpak`, with a separate `--overwrite-live` opt-out. Verified refusing on the live box |
| 5 | **Kodi addon updates were set to install automatically, with notifications off.** Five addons carry hand-applied patches (`games.py`, `achievements.py`, `nextup.py`, `main.py`, `couchhost.py`, the `monitor.py` skin gate, two YouTube `utils.py` edits). Their only protection is that our local version numbers out-rank the repo's — which still holds on Omega (helper 1.1.8.8 vs repo 1.1.6, embuary 2.0.8.2 vs 2.0.8, YouTube 7.4.4 = 7.4.4) but is one upstream release away from silently reverting the console's front door. | C | DECIDED: `general.addonupdates` = 1 (notify, don't install) and `general.addonnotifications` = true. Written durably into `guisettings.xml` **with the `default="true"` → `default="false"` flip** (the 2 Aug lesson: without it Kodi ignores the value on load), and confirmed live |
| 6 | **Two files claimed window 1196** — `Custom_1196_Couch_HaloPicker.xml` and `Custom_1196_Couch_YouTube.xml`. Kodi logged `id already in use` at every startup and loaded YouTube; `Home.xml:147` activates 1196 expecting YouTube, so the picker was unreachable. Its own comment called it "(temporary)". | C | DECIDED: deleted. It could not change behaviour (Kodi already refused it), it removes a startup error, and two files with one id is a trap for whoever reads them next. YouTube on 1196 re-verified afterwards |
| 7 | The patch-set README claimed helper version 1.1.6.6; the deployed addon is 1.1.8.8. | C | FIXED: corrected, and pointed at the deployed `addon.xml` as the source of truth rather than a line that has drifted before |
| 8 | **`kodi-tv`'s crash-relaunch through `flatpak run` — now CLOSED.** The loop keys on exit codes 131–136/139. The in-sandbox `kodi.sh` does `exit $RET`, and `flatpak run` should propagate it, but this was never observed — and it is also what `server/sys.js`'s hardened restart depends on. Untestable without deliberately crashing the live Kodi. | B → **closed** | VERIFIED the same evening, riding a restart that was needed anyway: `POST /api/system/kodi-restart` (i.e. `server/sys.js` SIGABRTing kodi.bin) and the wrapper brought Kodi back through `flatpak run` in ~6s, still supervising. The exit code propagates |
| 9 | The two profiles diverge from here: watch state, resume points and library changes recorded on Kodi 21 are invisible to Kodi 20, and vice versa. | C | ACCEPTED + documented. Inherent to copy-not-share, which is what makes the rollback trustworthy. Ends when the parachute is cut |
| 10 | The apt profile's addons freeze at their 8 Aug state; `deploy-addons` now defaults to the live flavour. | C | ACCEPTED. A rollback is meant to be the console as it was, not a second thing to maintain. `--profile both` remains available and is now safe (finding 1) |
| 11 | TV-side behaviour — picture, audio over eARC, 4K120, the pad actually driving the UI, a film, a game launch and a suspend/resume cycle, the first deliberate `ReloadSkin()`. | D | → todo.md "needs Donnie's eyes". No synthetic test substitutes for these |

## Checked and found fine

- **Rollback integrity**: apt Kodi installed, `~/.kodi` intact, its frozen skin
  real and pinned at 5.16.0, `kodi21-migrate rollback` present and
  uninstalling nothing.
- **Sandbox**: all 13 in-sandbox checks re-run green after every fix,
  including `--filesystem=/tmp` genuinely exporting the host `/tmp` and
  `couchhost`'s `flatpak-spawn` fallback reading a host file.
- **Profile resolution**: no `~/.kodi` literal left in live code
  (`test_kodiprofile.py` greps for it); both language halves agree; both
  default to `apt`.
- **Process identity**: `pgrep -x kodi.bin` still matches inside the sandbox,
  so `server/sys.js:361`'s hardened restart and both `tv-waker`s still find it.
- **Phone app end to end**: `/api/library/movies` returns 88 items through
  `jellyfin.js` on the new profile; `/api/windows` shows Bloodborne badged
  "· paused".
- **Backups**: both scripts parse and now include the Flatpak `userdata`; the
  netbook one gets its own destination so the two `userdata` dirs cannot
  collide.
- **Autostart**: `kodi.desktop` runs `kodi-tv`, which resolves `flatpak` from
  the flavour file — the next reboot comes up on Kodi 21 with no further step.
- **Jellyfin identity**: both profiles carry the same user id and no device
  id, so nothing double-registers; the `flock` prevents both running anyway.
- **Data**: `Addons33.db` integrity ok after the finding-3 incident; disk 220 G
  free, the whole Flatpak profile is 376 MB.
- **Addon compatibility**: every non-skin addon imports `xbmc.python` 3.0.0 or
  3.0.1, which Kodi 21 satisfies. Only skins were ever blocked.

## Verification evidence

- `couchd/.venv/bin/pytest couchd tools -q` → **983 passed**, 7 failed.
- The 7 are `tools/test_curtain.py` and are **pre-existing and unrelated**:
  the curtain daemon does not write its pidfile under the test's private
  Xvfb. Confirmed identical at `e222beb`, before any of this work, by
  checking that commit out into a scratch worktree. Still open, still
  deserving its own look.
- New tests from this audit: `tools/test_deploy_addons.py` (8),
  plus 3 added to `tools/test_kodi21_migrate.py`. Every [A] has one.
- Production re-checked after the last change: Kodi 21.3 on Home with
  `skin.couch`, 88 films, YouTube window resolving, TV in standby.

## What this audit could still have wrong

The "make no mistakes" pass over the audit itself.

- **An [A] fixed but not verified?** No. 1, 2 and 4 were each exercised
  against the live tree after the fix (deploy dry-run, repo checksum, the
  refusal message); 3 was verified by repairing the damage and re-reading the
  database. All four also have unit tests.
- **The report claiming more than shipped?** The one soft claim is finding 5's
  durability: the setting is live AND written to `guisettings.xml`, but Kodi
  will rewrite that file wholesale on its next clean exit. It writes its own
  in-memory value, which is the same value, so both paths agree — stated here
  rather than assumed.
- **A rubric area skipped?** Playback was not exercised at all. Deliberate:
  starting a film wakes the television, which was out of bounds. It is
  finding 11.
- **A fix that broke a neighbour?** The `deploy-addons` change makes it
  *refuse* an action it used to take; the risk is a genuinely stale symlink no
  longer being repaired. Covered — the repair path is tested and only real
  directories are exempt. The skin-file deletion was checked for referrers
  first (`Home.xml:147` wants YouTube, which is the file that survives).
- **A test that passes for the wrong reason?** Found one and fixed it: the
  `kodi21-migrate` fixture read the *real* flavour file, so once the box went
  live every copy test in it failed. Both that fixture and
  `test_kodiprofile`'s "no flavour file" case now inject their environment.
  This is the second time today an environment-dependent test misled — worth
  treating as a pattern, not two accidents.
- **Something I fixed that was not broken?** Finding 6 is the closest call.
  Deleting skin content was not asked for; it is defensible only because Kodi
  provably refused to load the file, so behaviour cannot change. Recorded as a
  judgement call rather than a repair.

## Findings

### 1. High confidence: the live PS-switcher path deliberately exposes Kodi before creating the dialog

[couchd/couchd.py:1789](/home/ds2000/couch/couchd/couchd.py:1789), [couchd/couchd.py:3483](/home/ds2000/couch/couchd/couchd.py:3483)

Precise interleaving:

1. Freeze game and set `/tmp/game-suspended`.
2. Spawn `pause-snap` asynchronously.
3. Route pad to Kodi.
4. Raise Kodi with `ConfigureWindow(Above)` and `d.sync()`.
5. Spawn the guard.
6. Only then call `Addons.ExecuteAddon` for the switcher.

There is no curtain action anywhere in this bare-X11 branch. Tonight’s evidence confirms the visible interval: couchd observed Kodi on top at `23:28:45.632`; Kodi loaded the switcher window at `23:28:45.911`. That is at least 279 ms, many frames at 120 Hz, in which Kodi Home is the intended top window.

The existing `g_tap_resume_due` fix only prevents a later resume. The guard preserves Kodi’s position, which actually reinforces this exposure. The gamescope branch would avoid it, but the live rail and enable flag are absent.

Smallest closure: keep the frozen game mapped while starting the addon behind it, poll Kodi until `currentwindow` enters `13000..13099`, then atomically raise Kodi and iconify the game. Alternatively, synchronously raise the freeze-frame curtain before Kodi and fade it only after that window-id confirmation.

Verified: ordering, live configuration, X/Kodi timestamps. Inferred: exactly which Kodi Home frame was scanned out, although the reproduced symptom matches the measured gap directly.

### 2. High confidence: an old launcher can kill the next launch’s curtain and raise Kodi over it

[legacy-mirror/game-launch:1407](/home/ds2000/couch/legacy-mirror/game-launch:1407), [legacy-mirror/game-launch:1444](/home/ds2000/couch/legacy-mirror/game-launch:1444), [tools/curtain:1130](/home/ds2000/couch/tools/curtain:1130)

Fresh launches show the loading curtain before claiming the new session at lines 1408 versus 1422. Launch verbs intentionally do not take the transition lock. Meanwhile every retiring launcher’s EXIT trap unconditionally:

1. Routes the pad to Kodi.
2. Raises Kodi.
3. Calls `curtain fade`.

Only removal of `/tmp/game-session` is launcher-owner guarded at line 1463. The visible restore and curtain fade are not.

Tonight’s exact overlap was:

- `23:28:47.063`: quit begins.
- `23:28:48.323`: new Steam launch begins.
- `23:28:48.781`: old shadPS4 session ends.
- `23:28:48.839`: old launcher routes to and raises Kodi.
- `23:28:49.696`: old restore finishes, exactly as the new launcher finally advances past curtain creation.

During a cold curtain upload the PID exists before its FIFO. A concurrent `fade` therefore enters `cmd_fade`, fails `fifo_send`, calls `cmd_clear`, and SIGTERMs the new curtain at lines 1153-1177. Failures are swallowed by the launch path. Consistently, there is no 23:28 curtain fade record, and both later fade attempts report that no curtain exists.

Smallest closure: generation-scope both restore and curtain ownership. Publish the new launcher/session generation before showing its curtain, and make an old EXIT trap skip `focus_kodi` and `curtain_fade` once that generation no longer belongs to it. A short handover lock may cover setup, but it must be released after the session claim rather than held for the game’s lifetime.

Verified: overlapping launch/exit, unconditional stale restore, missing curtain afterward. Inferred: the exact pre-FIFO SIGTERM branch, strongly supported by the 1.35-second blocked show and absence of a daemon fade record.

### 3. High confidence: couchd kills the Kodi guard it just spawned

[couchd/couchd.py:1586](/home/ds2000/couch/couchd/couchd.py:1586), [couchd/couchd.py:1719](/home/ds2000/couch/couchd/couchd.py:1719)

After the first tap pass freezes and spawns `steam-input-guard kodi`, the next sampled pass can still report the game processes as running. `_switcher_intents()` consequently calls `_supersede_guard_intent()` again. Because gestures are owned but guard is not, the new legacy guard is not marked `guard_pid_ours`, so couchd mistakes its own freshly spawned child for the old game guard and kills it.

Tonight the guard opened at `23:28:45.616` and was terminated as “superseded” at `23:28:45.633`, only 17 ms later and before the switcher drew.

`g_tap_resume_due` does not cover this. It guards gesture state, not a deferred PID observation written by the same action batch.

Smallest closure: supersede only a guard that predates the suspend. At minimum, do not call `_supersede_guard_intent()` once `suspended_present` is true. A generation/timestamp comparison against the current gesture is stronger.

Verified: code path and actual open/close records. Inferred: this guard loss causing a visible bounce on a particular press. Tonight Kodi happened to remain on top long enough.

### 4. Medium confidence: curtain “READY” confirms X request processing, not presentation

[tools/curtain:608](/home/ds2000/couch/tools/curtain:608), [tools/curtain:772](/home/ds2000/couch/tools/curtain:772)

`Overlay.show()` sets opacity, maps, raises, and calls `d.sync()`. `serve()` then reports `READY`. XSync only proves that the X server processed the requests. It does not prove xfwm4’s compositor painted the curtain or that a frame containing it reached scanout.

A caller can therefore receive success and immediately raise or unmap an underlying window while the compositor has not presented the curtain once. The status-file confirmation for a warm curtain has the same limitation because `shows` increments directly after that same XSync.

Smallest closure: delay readiness until at least one compositor/presentation cycle after map and damage, preferably via a presentation completion signal. A conservative one-refresh delay would close the immediate race but is less rigorous.

Verified: readiness is based solely on XSync. Inferred: whether this contributed an additional single-frame leak tonight.

The evidence therefore splits rather than supporting one root cause: the PS flash is a curtain-free, Kodi-first sequence; the launch flash is a stale previous-launcher action operating on the next global curtain.

The measured opacity lesson is applied to `switcher-overlay.unmap_now()`, and that rail is disabled live. The normal curtain fade also reaches opacity zero before unmapping. I found no live opacity-only regression on these reported paths.
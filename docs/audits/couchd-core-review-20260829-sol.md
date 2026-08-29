1. CRITICAL, confidence: very high. Input ownership is cached at startup, breaking live rollback and daemon failover.

Verified: `grants_input()` is called only in `main()` ([inputproc.py:1384](/home/ds2000/couch/couchd/inputproc.py:1384), [inputproc.py:1411](/home/ds2000/couch/couchd/inputproc.py:1411)); `self.own` is then fixed ([inputproc.py:549](/home/ds2000/couch/couchd/inputproc.py:549)). The loop reloads gesture settings, not `owns.conf` ([inputproc.py:1303](/home/ds2000/couch/couchd/inputproc.py:1303)). Supervisor availability is checked only before the initial grab ([inputproc.py:1218](/home/ds2000/couch/couchd/inputproc.py:1218)); after disconnection, every guide edge is merely dropped ([supervisor.py:630](/home/ds2000/couch/couchd/supervisor.py:630)). This contradicts the adjudicated requirement that inputproc release within a tick ([synthesis:137](/home/ds2000/couch/docs/audits/stage2-inputproc-review-20260809-synthesis.md:137)).

Trigger: while the pad is attached, remove `input` from `owns.conf`, or let couchd stop/crash after inputproc has connected. Inputproc keeps `self.own=True`, retains EVIOCGRAB and withholds BTN_MODE. After 30 seconds the legacy lease reclaims gestures ([owns.py:217](/home/ds2000/couch/couchd/owns.py:217)), but it still receives no guide events. Axes and ordinary buttons continue through the virtual pad, so this presents as a selectively dead PS button rather than a crashed service.

Live relevance: `input` is declared now ([owns.conf:55](/home/ds2000/couch/couchd/owns.conf:55)); the live peer reports `peer_owns_input: true` ([status.json:117](/home/ds2000/couch/shadow/status.json:117)). The pad happened to be absent during review.

Smallest safe change: make the startup interlock continuous. On removal of `input`, or supervisor loss beyond the lease grace, atomically clear pending gestures, reset the tracker, ungrab, set `self.own=False`, and enter the existing observe-and-forward path. Reacquire only after both ownership and supervisor connection are restored with a fresh button baseline.

2. HIGH, confidence: very high. Configurable gesture timings do not configure the trackers that classify gestures.

Verified: couchd constructs `PressTracker()` with hard-coded defaults ([couchd.py:3699](/home/ds2000/couch/couchd/couchd.py:3699)), while `Observed` receives live settings separately ([couchd.py:5277](/home/ds2000/couch/couchd/couchd.py:5277)). Inputproc configures its tracker once ([inputproc.py:550](/home/ds2000/couch/couchd/inputproc.py:550)), then reloads only `self.conf` ([inputproc.py:1303](/home/ds2000/couch/couchd/inputproc.py:1303)). Some guards also call `is_tap()` without the configured threshold ([couchd.py:674](/home/ds2000/couch/couchd/couchd.py:674), [couchd.py:779](/home/ds2000/couch/couchd/couchd.py:779)).

A read-only reproduction confirmed that the default tracker classifies a 1.0-second press as `hold-release`, while `is_tap(1.0, 1.2)` classifies the same press as a tap. The stale tracker’s `hold_release_pending` then bypasses the configured threshold through the coalesced-hold guard ([couchd.py:716](/home/ds2000/couch/couchd/couchd.py:716)).

Trigger: set `hold_seconds=1.2`, then press for 1.0 seconds. The model can execute the hold action even though the configured boundary says tap. With the current bindings, that means `home`, potentially suspending a game, instead of `switcher` ([settings.xml:2](/home/ds2000/.var/app/tv.kodi.Kodi/data/userdata/addon_data/script.couch.switcher/settings.xml:2)).

Current state: no timing overrides are present, so defaults mask the defect today.

Smallest safe change: update both trackers only while idle, snapshot timings for the lifetime of each press, and pass `o.hold_seconds` to every tap predicate. Add a runtime-path test with non-default timings.

3. HIGH, confidence: high. Losing one supervisor message can synthesize a hold from a tap.

Verified: both supervisor queues deliberately drop individual newest messages when full ([supervisor.py:468](/home/ds2000/couch/couchd/supervisor.py:468), [supervisor.py:624](/home/ds2000/couch/couchd/supervisor.py:624)). `wire_press()` ignores the result ([inputproc.py:609](/home/ds2000/couch/couchd/inputproc.py:609)). Health eventually exposes a cumulative drop count, but couchd only records it ([couchd.py:3989](/home/ds2000/couch/couchd/couchd.py:3989)); it neither resets the tracker nor suppresses decisions. The test explicitly verifies visibility only ([test_supervisor.py:654](/home/ds2000/couch/couchd/test_supervisor.py:654)).

Trigger: a press-down is delivered, but its release arrives while either bounded queue is full. Couchd remains at `button_down=True`; after the configured threshold, `g_hold_reached` fires ([couchd.py:589](/home/ds2000/couch/couchd/couchd.py:589)). A short tap can therefore become `home` or suspend. Inputproc saw the real release locally, but health carries no current button state with which couchd could resynchronize.

Current state: both live drop counters are zero ([status.json:129](/home/ds2000/couch/shadow/status.json:129)).

Smallest safe change: treat any increase in either drop counter as loss of stream integrity. Reset the tracker, mark gestures unknown, and suppress actions until inputproc supplies an explicit current BTN_MODE baseline or a clean reconnect.

4. HIGH, confidence: high. Persistent virtual-pad failure leaves inputproc consuming the real controller while daemon health stays green.

Verified: `emit()` catches every write error and returns false ([inputproc.py:656](/home/ds2000/couch/couchd/inputproc.py:656)), but ordinary forwarding ignores the result ([inputproc.py:988](/home/ds2000/couch/couchd/inputproc.py:988)). Virtual-side read errors likewise only print and return ([inputproc.py:1158](/home/ds2000/couch/couchd/inputproc.py:1158)). Local health counts `write_failures`, but supervisor health sends only drops, ownership, degraded state, and persistence state ([inputproc.py:1176](/home/ds2000/couch/couchd/inputproc.py:1176), [inputproc.py:1199](/home/ds2000/couch/couchd/inputproc.py:1199)). `degraded` is never set for uinput failure.

Trigger: `/dev/uinput` starts returning persistent `EIO`/`ENODEV`. Inputproc continues reading and grabbing the physical pad, drops every translated event, and remains connected with `peer_degraded: null`. Games lose the entire controller while couchd appears healthy. The failures exist only in inputproc’s separate evidence stream.

Current evidence records `write_failures: 0`, so this is not active now.

Smallest safe change: count consecutive failures, propagate `write_failures` and a degraded reason over supervisor health, then destroy/recreate the virtual pad after a small threshold. If recreation fails, stop consuming the physical device and surface a hard health failure.

5. MEDIUM, confidence: high. Gesture elapsed time is vulnerable to wall-clock steps.

Verified: evdev timestamps are anchored to `time.time()`, and gaps are extrapolated using later wall time ([gesture.py:117](/home/ds2000/couch/couchd/gesture.py:117), [gesture.py:303](/home/ds2000/couch/couchd/gesture.py:303), [inputproc.py:978](/home/ds2000/couch/couchd/inputproc.py:978)). No `EVIOCSCLOCKID` request exists. Live records confirm `kernel_t` is effectively the wall-clock epoch, not monotonic time.

Trigger inference: an NTP/manual clock step during a held press changes the computed duration by the size of the step. A forward step can immediately manufacture a hold; a backward step delays it. Release-to-press duration is also corrupted if the realtime step occurs between the two kernel events.

Smallest safe change: set every evdev descriptor to `CLOCK_MONOTONIC` with `EVIOCSCLOCKID`, anchor gaps with `time.monotonic()`, and loudly reject or degrade if the clock selection fails.

6. MEDIUM, confidence: medium-high. A live but stalled launcher creates an indefinitely active session with no useful Home action.

Verified: after 30 seconds, `starting` becomes `active` solely because time elapsed, even with no game evidence ([couchd.py:870](/home/ds2000/couch/couchd/couchd.py:870), [couchd.py:1135](/home/ds2000/couch/couchd/couchd.py:1135)). Once active, it can leave only when the flag disappears or the launcher is dead with no game ([couchd.py:1139](/home/ds2000/couch/couchd/couchd.py:1139)). A `home` gesture sees the session and enters `_suspend_intents`, which returns nothing when there are no game PIDs and no Big Picture window ([couchd.py:1886](/home/ds2000/couch/couchd/couchd.py:1886), [couchd.py:1655](/home/ds2000/couch/couchd/couchd.py:1655)).

Trigger inference: the launcher writes the session flag, then hangs alive before producing a game process/window. After 30 seconds the region reports `active` indefinitely; the current hold/Home binding becomes a no-op while status continues to describe an active session.

Smallest safe change: do not promote `starting` to `active` on elapsed time alone. Introduce a conservative stalled-launch deadline that surfaces attention and recovers the stale session only after the launcher’s documented maximum startup interval.
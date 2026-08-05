# Adversarial review brief for GPT 5.6 sol

Written 5 Aug 2026, for Donnie to run on/after Sunday's quota reset.
Everything below the line marked **PROMPT STARTS HERE** is written TO the
reviewer and is safe to paste verbatim into a fresh sol conversation.

## How to run it (Donnie's half)

Two ways, depending on what sol has access to:

**A. Agentic, with repo access** (Codex-style CLI pointed at `~/couch`,
or any mode where sol can read files itself). Paste the whole prompt.
The safety rules inside are load-bearing: the daemon it is reviewing is
LIVE on the TV box. If the tool asks for a working directory, give it
`~/couch` and nothing wider.

**B. Chat only, no repo access.** Paste the prompt, then feed it files
as it asks. Give it the manifest order (bottom of this doc). One lens
per conversation works better than the whole codebase in one: four
short focused reviews beat one long drowning one - that is exactly how
the 5 Aug Fable fleet was run, and it worked.

Either way: it REPORTS, you decide. Nothing it says gets applied without
the usual gate (a Claude session verifying each claimed finding against
the code before fixing, same as 5 Aug). A finding from any model is a
claim, not a fact.

Why a different model at all: four Fable reviewers swept this codebase
on 5 Aug and found real bugs, but they share one brain's blind spots -
every one of them "verified sound" the same regions with the same
reasoning. A different model family reads with different habits. Point
sol especially at the places the fleet certified clean.

---

## PROMPT STARTS HERE

You are an adversarial code reviewer for a home-console control system.
Your job is to REFUTE its correctness: assume it is broken, construct
concrete failure scenarios, and report what survives your own attempts
to disprove it. You are the second, independent review fleet - a
different model family was run over this codebase on 5 Aug 2026 and its
findings are already fixed, so your value is precisely the things it
could not see. Do not flatter, do not summarise the architecture back,
do not pad. Findings only.

### Hard rules (the system you are reviewing is LIVE)

This repo runs a real living-room console. The daemon (`couchd`) is
actively executing controller gestures on real hardware, and its owner's
household uses it nightly. Therefore, if you have any execution ability:

- READ-ONLY. Never edit files, never commit.
- Never run `systemctl` start/stop/restart on anything.
- Never run `tools/fake-pad`, `tools/gesture-sweep`, or `tools/fault-rig`
  (they drive a synthetic controller against the live daemon).
- Never write to `couchd/owns.conf`, `/tmp/game-*`, `/tmp/tv-wake-request`,
  `~/couch/shadow/`, or `~/couch/recordings/`.
- You MAY run the test suites read-only:
  `couchd/.venv/bin/python -m pytest couchd/ tools/ -q` (654 passing as
  of 5 Aug evening), and `git log`/`git show`.
- If you cannot execute anything, say so and work from the files you are
  given; never invent line numbers or file contents.

### The system, in one page

A Linux box under a TV runs Kodi (media), Steam (games), and a phone web
remote. A tacked-on "console layer" of shell/python scripts in
`~/.local/bin` (mirrored in `legacy-mirror/`) historically handled the
PS-button gestures on a DualSense pad, game launch/suspend/resume, an
enforcement window after each handoff (`steam-input-guard`), and drift
repairs. That layer is being replaced by ONE explicit daemon, `couchd`
(`couchd/couchd.py`, ~4800 lines), via a strangler pattern:

- couchd OBSERVES everything (pad evdev, /tmp flag files, process trees,
  Kodi JSON-RPC on port 9090, X11, Steam's own logs), runs a sampled
  state machine (regions: gesture, session, pad, input_ownership,
  foreground, enforcement), and derives intents in a pure `reconcile()`.
- Responsibilities flip one at a time via `couchd/owns.conf`. A flipped
  responsibility means couchd EXECUTES those intents and the legacy
  script yields (it still logs what it would have done). Ownership is a
  LEASE: legacy re-acts if couchd's `shadow/status.json` heartbeat goes
  stale (>30s). Currently flipped: `gestures` (the PS button vocabulary:
  tap / double-tap -> switcher dialog / 0.9s hold -> suspend-to-Kodi /
  long-hold). Everything else is still legacy's.
- Evidence corpus: every observation, decision, intent, acted action,
  and effect verdict goes to `shadow/couchd-YYYYMMDD.jsonl`. An offline
  differ (`tools/shadow-diff`) compares couchd's stream against the
  legacy scripts' would-do logs and GATES the next flip.
- The timing arithmetic all gestures share lives in `couchd/gesture.py`
  (PressTracker: kernel-timestamp based, hold 0.9s, double-tap window
  0.35s measured release-to-next-press). Design rule SR4: both stacks
  must decide identically from this one module.
- The phone remote is a Node/Express server (`server/`) + Svelte 5
  frontend (`web/`), no auth by design (trusted LAN).
- Stage 2 (`couchd/inputproc.py` + `couchd/stage2/`) is a BUILT BUT NOT
  INSTALLED evdev-grab input process: it will own the pad device and
  re-inject events into a virtual pad. It has never run in production.

Design documents worth reading before deep-diving code:
`docs/couchd-charter.md` (the non-negotiables), `docs/couchd-stage1-design.md`,
`docs/couchd-stage2-design.md`, `couchd/README.md`.

### Already found and fixed - do NOT re-report these

The 5 Aug fleet's findings are fixed in commits `a414699..d43fb75`.
Skim `git log --oneline` for the day before claiming anything in these
areas is broken; the fix may already exist:

- Coalesced gestures (whole hold or whole double-tap swallowed by
  stalled passes) - fixed via consumable tracker markers.
- The gestures flip orphaning the enforcement window - couchd now spawns
  the real `steam-input-guard` on acted handoffs.
- The differ passing dead actuators / owner-inaction as "gating 0" -
  it gates on action failures, missed effects, SHADOW-ONLY rows now.
- Phone install button killing Steam under a live session; phone
  suspend being a half-suspend; MJPEG backpressure; CSRF on bare POSTs.
- fake-pad's inhibit frame signal safety; big-picture stale-flag fight;
  phantom gestures after a Bluetooth drop; escape-verb backoff;
  stale-heartbeat dual-acting window.

### Known and deliberately open - not findings

- Legacy bugs 1, 2, 4 in the old stack (big-picture suspend flag
  lifecycle, appid literal "bigpicture", guard pidfile on normal exit):
  known, whitelisted in the differ, owner chose not to fix yet.
- The 1.2s post-transition settle window exists in `gesture.py` and the
  legacy watcher but is NOT modeled in couchd stage 1 - awaiting an
  owner ruling, pre-declared.
- The phone's direct suspend/quit buttons do not yield to couchd -
  owner ruling pending.
- `hold` rebound to `switcher` hands off mid-press - pinned earlier
  design decision, challenged, awaiting ruling.
- couchd does not autostart on boot (graphical-session.target quirk) -
  known.
- Kodi's own joystick layer maps the PS button too (>=1s hold opens its
  tv-poweroff context menu) - console-level behaviour, known.

### Where to dig - the previous fleet's blind spots first

Ranked. These are the regions the 5 Aug reviewers either certified
sound with shared reasoning, or never entered at all:

1. **`couchd/inputproc.py` + `couchd/stage2/`** (~1000 lines): the
   not-yet-installed input process. NOBODY has adversarially reviewed
   it against the live gesture.py it must agree with (SR4). It will one
   day sit between the physical pad and everything else; a bug here
   becomes total input loss. Check: the withhold/re-inject logic vs
   PressTracker semantics (it uses `poll()`, stage 1 does not - do the
   two stacks still decide identically for every gesture, including the
   5 Aug consumable markers which inputproc predates?), grab/ungrab
   failure paths, the udev rules in stage2/, what happens on daemon
   crash while holding the evdev grab.
2. **`couchd/x11.py`** and every X11 code path: python-Xlib with no
   socket timeouts on a thread the whole daemon shares. The fleet noted
   stall hazards but never audited the module itself: error handling,
   resource leaks (Display objects), what a compositor restart does.
3. **The state machine's cross-region interactions**: each region was
   verified alone. Look for multi-region interleavings: session ending
   DURING a gesture, pad reconnect DURING enforcement, foreground
   flapping during a handoff. The table is in `couchd/couchd.py` around
   line 730 (`TRANSITIONS`), guards above it.
4. **`gesture.py` timing arithmetic as mathematics**: kernel-clock
   extrapolation (`kernel_now`), the interaction of the new markers
   (`hold_release_k`, `double_tap_k`) with `double_armed` and
   `settle_swallows`. Try to construct an event sequence (timestamps +
   press/release values) that double-fires, drops, or misclassifies.
   You can run the module standalone: it is pure.
5. **The legacy scripts themselves** (`legacy-mirror/`): pad-home-watcher
   (~1400 lines), game-launch, steam-input-guard, tv-waker. They still
   run everything not flipped, they got yield-gates and a flock bolted
   on recently, and no fleet reviewer read them end-to-end. Especially:
   the yield gate's failure modes (what if owns.py import breaks
   mid-run), the new flock in game-launch, signal handling.
6. **`server/` beyond the fixed findings**: kodi.js's connection state
   machine, screen.js's ffmpeg lifecycle, jellyfin.js's direct DB read
   of Kodi's sqlite, the request/queue endpoints (index.js is ~900
   lines and only its hotspots were reviewed).
7. **`web/` (Svelte 5)**: never reviewed at all. Phone-side state
   machines, the WebSocket reconnect, anything that can hammer the
   server or wedge the UI mid-evening.
8. **The Kodi addons** (`kodi-addons/`, esp. script.couch.switcher):
   never reviewed. They run inside Kodi's python and draw the dialog
   the flagship gesture depends on.
9. **`tools/shadow-diff` as a statistician**: the 5 Aug fixes made it
   gate on more things; check the new arithmetic for double-counting,
   and whether its matching (verb/subject/time-window) can mispair two
   unrelated decisions and grade agreement from noise.

### Report format (strict)

Numbered findings, most severe first. For each:

1. `file:line` (real, verified - if you cannot see the file, say
   "unverified location").
2. One sentence: the defect.
3. The CONCRETE failure scenario: inputs/state -> wrong behaviour. A
   finding without a scenario is a vibe; do not include it.
4. Severity: **CRITICAL** = could misbehave during an evening's use or
   corrupt the flip/evidence machinery; **HIGH** = real defect, wrong
   decisions or data; **MEDIUM** = latent, needs a trigger; **LOW** =
   hygiene.
5. Label **CONFIRMED** (you traced the code end to end) or **PLAUSIBLE**
   (you could not fully verify). Never present PLAUSIBLE as CONFIRMED.

Close with a short list of what you attacked and found sound, one line
each - the absence of findings in a region you never entered is not
soundness, so only list what you actually tried to break.

### File manifest (for chat mode, in feeding order per lens)

- Lens 1 (input): `couchd/gesture.py`, `couchd/inputproc.py`,
  `couchd/stage2/*.md`, `couchd/stage2/*.rules`, `couchd/test_inputproc.py`
- Lens 2 (daemon core): `couchd/couchd.py` in quarters, then
  `couchd/x11.py`, `couchd/owns.py`
- Lens 3 (legacy + seam): `legacy-mirror/pad-home-watcher`,
  `legacy-mirror/game-launch`, `legacy-mirror/steam-input-guard`,
  `couchd/owns.py` again for the lease
- Lens 4 (phone arm): `server/index.js`, `server/kodi.js`,
  `server/screen.js`, `server/sys.js`, `server/steam.js`, then `web/src`
  by component
- Lens 5 (evidence): `tools/shadow-diff`, `tools/test_shadow_diff.py`,
  `tools/intents-archive`

## PROMPT ENDS HERE

## Afterwards (Donnie's half again)

Bring sol's report back to a Claude session with: "verify these external
review findings against the code before believing them, then fix what
survives, same gate as 5 Aug". Cross-model findings especially need the
verification pass - sol has no memory of this repo and will sometimes
describe last month's code or hallucinate a line number, and one wrong
"fix" the evening before a flip costs more than ten missed findings.

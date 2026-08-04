# couchd stage 1 — design note (shadow-mode control plane)

Status: DRAFT — research pass in flight (3 agents: prior art, shadow-migration
methodology, daemon architecture/runtime). Sections marked TBR (to be
researched) get filled from their findings. Per docs/couchd-charter.md
discipline 3: no stage-1 code before this note is complete.

## What it does for the product (plain language)

Tonight the console's brain is four scripts (pad-home-watcher, game-launch,
steam-input-guard, reconcile-inside-the-watcher) that agree with each other
through files in /tmp and by re-reading the world. It works — the 4 Aug audit
is green — but every new feature means editing four places, and the bugs we
fixed all lived in the gaps *between* the scripts.

Stage-1 couchd is one daemon that holds the whole picture: it watches
everything the scripts watch, keeps an explicit state machine (the audit's
states and invariants written down in code, not implied), and says what it
would do. In shadow mode it only *says* — the old scripts keep actually
doing. We compare couchd's would-do log against what really happened, evening
after evening, until they agree; only then does anything flip live, one
responsibility at a time, behind a switch, with one-command rollback.

## What it observes (the same world the old stack reads)

- DualSense evdev button node (read-only, never grabbed) — PS press/hold.
- /tmp/game-session, /tmp/game-suspended (the current shared truth).
- Game process states via game-pids (S/T per pid).
- X stacking/focus (same source as screen.js/xinput.py).
- Kodi `input.enablejoystick` (JSON-RPC read).
- Steam menu/routing state via controller_ui.txt `OnFocusWindowChanged`.

## Outputs (stage 1 = all passive)

- Structured event log (every observation, state change, and would-do action).
- /status on a unix socket (current state, invariant checks, uptime) — the
  couch app's debug card reads this later.
- Shadow-diff report: would-do vs what-the-old-stack-did, per evening.

## What could be wrong in ways tests won't catch (the reason /build applies)

1. **Shadow-diff methodology**: the old stack never announces decisions, only
   effects. Comparing intended actions to observed effects across two
   samplers with timing skew can produce endless false divergences (or,
   worse, tolerant-enough windows that hide real ones). TBR: parallel-run
   practice (Scientist, strangler-fig writeups).
2. **State model mismatch**: couchd's states might not carve reality where
   the old stack does (Big Picture browsing vs game running vs shadPS4 mode;
   transitions only visible mid-flight). TBR: how prior-art console daemons
   model session state.
3. **Runtime corner-painting**: stage 2 needs exclusive evdev grab + uinput
   virtual pad + (maybe) uhid DualSense emulation at low latency. Stage 1's
   language/skeleton must not make that a rewrite. TBR: library maturity +
   latency reality per candidate (Python / Rust / Node).

## Task-specific mistake list (swept item-by-item before "done")

- **M1 Coverage gap**: shadowing only the PS-gesture path and calling it
  done; all four responsibilities (gestures, transitions, guard invariants,
  reconcile repairs) must produce would-do output.
- **M2 Not actually passive**: an "observer" that grabs evdev, writes JSON-RPC
  settings, touches /tmp flags, or interferes with Steam's log rotation.
  Sweep: audit every syscall/API touchpoint for read-only-ness.
- **M3 Divergence noise**: timing skew between couchd's sampling and the old
  stack's actions drowning real divergences. Sweep: run rigs, count false
  positives, tune tolerances per the researched methodology.
- **M4 Box burden**: crash-loop + Restart=always, busy polling next to a
  running game, or unbounded logs filling disk overnight. Sweep: CPU/mem
  check while a game runs; log rotation/size bound; RestartSec.
- **M5 Missing states**: shadPS4 sessions, Big Picture browsing with no game,
  Kodi-crash-restart windows. Sweep: state machine enumerates every audit
  state; rigs stage each.
- **M6 Recorder/replay schema drift**: recordings (tools/pad-record) must
  actually replay into couchd's input layer. Sweep: replay the synthetic-tap
  recording through couchd and see the press in its event log.
- **M7 Secret-scrub regression**: env refactor breaking the live couch server
  on restart (node --check can't see runtime env misses). Sweep: restart in a
  quiet window, probe the API endpoints that use each moved secret.
- **M8 History contamination**: a missed secret entering git history at the
  first commit. Sweep: gitleaks (already in ~/.local/bin) over the tree
  before commit.
- **M9 Breaking the old stack**: couchd/pad-record's extra readers on the
  same evdev nodes, inotify watches, or controller_ui.txt tailing changing
  the watched systems' behavior. Sweep: rigs pass identically with couchd
  running vs stopped.

## Research findings → constraints (TBR)

(To be filled from the three research agents: prior-art constraints,
shadow-diff parameters — comparison granularity, tolerance windows,
acceptance criteria, diff-triage taxonomy — and the runtime decision with
trade-offs. Every number calibrated on OUR data: the audit timings, the
psfuzz/chaos runs, and real-evening recordings from tools/pad-record.)

## Sources (TBR)

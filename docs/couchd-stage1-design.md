# couchd stage 1 — design note (shadow-mode control plane)

Status: research complete; adversarial review done (2 independent Opus
reviewers, correctness + practicality lenses). Constraints C1-C31 stand AS
AMENDED by the rulings below — where a ruling contradicts a constraint's
original text, the ruling wins.

## Adversarial review rulings (binding)

**R1 (was E1/blocker) — Stage 1 launches nothing.** C23 is an *interface*
requirement only: the launch verb exists in the contract so launch can move
behind couchd in stage 2 (env injection + subreaper); stage-1 couchd never
starts Steam, games, or anything else. "Stage 1 = all passive" wins.

**R2 — Minimal viable shadow replaces the full pipeline.** The old stack
ALREADY LOGS ITS DECISIONS (game-launch "=== launch/quit/suspend/resume",
watcher "PS held, freezing N processes of X" + every reconcile repair with
reason, guard fix-lists) — the design's "legacy never announces decisions"
premise was false. Legacy intent = parse the three logs (primary), effect
observation demoted to corroboration. Build order: MVS-1 one-file shadow
daemon (gestures + reconcile as pure functions, intents to
~/couch/shadow/*.jsonl + human one-liners to /tmp/couchd.log); MVS-2
offline tools/shadow-diff (time-sorted greedy match on (verb,subject) ±5s,
three sections printed, hand-labeled T1-T6); MVS-3 replay once a real
corpus exists. Cut entirely: C6's twin observer (degenerate here — floor
defined instead as run-to-run variance of a repeated rig scenario), C8's
21-point Nagios window (eyes-on-the-morning-diff at this volume; per-class
"k=3-5 consecutive clean" instead), C1's process-mining alignment
(~100-LOC greedy matcher), five-deep fallback chains (two sources each:
best-measured + /proc-based terminal fallback; interface kept so more can
be added when one actually breaks). C20 runs Hypothesis against the pure
reconcile function in-process, NOT over a socket — no injection surface in
stage 1. C28 trimmed to flock + restart policy (no children exist yet);
C11's mid-action fallback becomes "flip COUCHD_OWNS off, legacy reconcile
converges within a tick" (proven by audit).

**R3 — Two prerequisites for the legacy logs as intent source:** say()
gains sub-second timestamps, and each script emits one machine-readable
JSONL line beside each human line; the guard additionally logs per-fix
lines (its summary is end-of-window). These are log-only edits to the old
stack (M9-safe) — the ONLY old-stack edits stage 1 is allowed.

**R4 — Model amendments (correctness blockers 1,4-7,21):**
- freeze/thaw/quit intents carry the RESOLVED PID SET + resolver name as
  diffable args (verb-level diffing would have been blind to the audit's
  Proton fix); plus a continuous freeze-set agreement metric (couchd's
  would-freeze set vs game-pids vs gameprocess ledger, every tick, no
  transition needed).
- Verbs added: launch(app,mode), quit(scope), kill(pid-set),
  iconify(window-class), request_tv_wake.
- game region → dynamic map appid → per-app lifecycle (C26 states incl.
  LAUNCHING/STOPPING), separate session region for the wrapper; two
  concurrent games (A stopping, B starting) must be representable.
- EVERY region gets `unknown`; intents for a region observed `unknown` are
  suppressed (named invariant — covers Kodi-down windows).
- New `gesture` region (idle|down|hold-fired|handoff-pending|timed-out) +
  `pad` region; "no reconcile intents while gesture != idle" is a named
  invariant; gesture arithmetic uses KERNEL event timestamps, not read
  time (fixes a latent legacy flaw too).
- New `enforcement` region (none|kodi(until t)|game(until t)) so guard
  windows and supersede are modeled, not implementation detail.
- Trigger channels ADDED to observation: couch server switcher log,
  game-launch argv log line, Kodi addon launch line (without these, three
  of four responsibilities produce unmatched legacy-only diffs forever).
- Kodi observation adds GUI.GetProperties(currentwindow) +
  Player.GetActivePlayers (power-menu dismiss + playback state).
- tv region: stage 1 observes via tv-waker's state only, or drops the
  region; values on|standby|wrong-input, not on|off.
- Owned-resources invariant each tick (uinput nodes, vpad fifo, guard
  pidfile, flags) — leak class of audit failure 10, checked in shadow.

**R5 — Comparator amendments (blockers 8-10, sf 12,20,23):**
- Happens-before assertions evaluated INDEPENDENTLY of tolerance windows
  (route_pad after release edge; freeze before suspended-flag; pad-to-kodi
  before focus): a match inside ±2s that violates ordering still gates.
  Retain matched-offset distributions per verb; gate p95 against the
  250ms perceptual bound.
- C9 split: organic coverage (gestures, transitions) vs INJECTED coverage
  (guard invariants, reconcile repairs — they fire ~never organically; the
  audit's decoy-staging technique becomes a fault-injection rig, with
  legacy repair loops briefly paused so couchd's would-do is first
  responder). The 10-15 sessions are SHARED across responsibilities;
  transition coverage is the unit.
- Gate wording: raw diff rate vs noise floor; T4 bucket empty; others
  reported not gating; T5 whitelist WRITTEN BEFORE first evening (initial
  entries: gameprocess-ledger vs game-pids on transient reaper children;
  no-launcher-pid orphan semantics; flag verbs absent from couchd's
  stream; single-arbiter replaces guard supersede).
- Comparator is versioned; every change re-runs against the archived
  corpus of all previous evenings (corpus lives OFF /tmp and off the
  retention rotation); the result delta is reviewed. C17 deadlines and C5
  windows derive from ONE per-verb measured latency table.
- Observer-health gate independent of diffing: staleness heartbeat per
  source (a source silent N minutes invalidates the evening rather than
  passing an empty comparison); tail Steam logs by (dev,ino,size) with a
  loud observer-blind event on truncation; pad-appearance-to-first-event
  latency tracked; PS presses cross-checked against controller_ui.txt
  (independent hidraw channel). Canonical Steam log path chosen once
  (resolve the ~/.steam/steam vs debian-installation symlink).

**R6 — Operational amendments (B1-B3, C-list, E4-E5):**
- Phone-readable from week one: human one-liners in /tmp/couchd.log
  (same say() shape as the other scripts) + couch server proxies
  /api/couchd/status; Screen tab shows three lines. Charter's
  day-one-observable requirement, honored in stage 1 not "later".
- Shadow unit: Restart=on-failure, RestartSec=10, StartLimitBurst=5,
  StartLimitIntervalSec=300 — a down shadow costs nothing, a looping one
  DoSes X/Kodi. No unit may ever gain Requires=/After=couchd in stage 1.
- Supervisor loops ≥1s period, always; hhd's 50ms number belongs only to
  the stage-2 input process. Kodi reads: subscribe to the 9090
  notification socket (couch server already does), settings reads
  rate-limited ≥10s; the anti-entropy tick NEVER drives Kodi read rate.
  X: cache the window tree, refresh on PropertyNotify/ConfigureNotify;
  banned in code: SubstructureRedirect, ResizeRedirect, XGrabServer.
  Attention mode: observed change drops sampling to ≤200ms for a few
  seconds (inotify on flags; X events), so faults are seen before legacy
  repairs erase them (blocker 10).
- game-pids stays a library call/in-process read, not a subprocess per
  tick. Event log lives under ~/couch/shadow/ (NOT /tmp — tmpfiles wipes
  at boot), bounded, with the corpus archived separately.
- Audit cheat-sheet gains, the day the unit lands, as line 1:
  `systemctl --user stop pad-record couchd` (return to 4 Aug-green).
  Agents holding the box token may stop couchd; its absence is never an
  error. M9 sweep extended: rigs pass with couchd running, stopped, AND
  after a stop-start cycle (no residue: fds, X connection, files).
- gitleaks re-runs at every commit that moves script logic into the repo
  (the watcher hardcodes the Kodi password; couchd reads .env from its
  first line). M7/M8 marked done for repo-init.

**R7 — Pre-declared legacy bugs (T3 from evening one; do NOT "fix" the
shadow to match them):** (a) pure Big Picture holds never write
/tmp/game-suspended (freeze_game writes inside `if pids:`), so reconcile
takes the pad off Kodi ~10s later — pad routed to nobody (log evidence
17:19:25, 17:19:59); (b) games launched from inside Big Picture record
appid as the literal string "bigpicture", so that game's own Kodi tile
CLOSES it instead of resuming (log evidence 18:34:41). Both live today;
couchd's model does it right and the diff will show legacy wrong. Fixing
legacy is a separate decision for Donnie (they're on the handoff sheet).

**R8 — Recorder fixes applied immediately** (before tonight's corpus):
flag markers at ~100ms with mtime stamps; inline gzip with periodic sync
flush; 14-day retention. A world-snapshot corpus (flags + pid states +
joystick + top window, periodic JSONL) is recorded SEPARATELY for the
reconcile responsibility — the pad recorder structurally can't cover it
(it only runs while a pad is present; reconcile runs pad or no pad).

## Decisions (summary)

- **Adopt**: reconciler pattern (k8s), statechart regions (Harel),
  parallel-run shadow-diff discipline (Scientist/Diffy lineage), Steam's own
  gameprocess_log.txt as primary game-PID source, prior-art supervision
  bundle (crash-loop detector, readiness deadlines, flock). Python 3.12
  supervisor.
- **Build** (nothing exists to adopt): the state model itself, the
  legacy-intent inference + shadow-diff tooling, the observation interface
  with fallback chains, the replay harness over tools/pad-record recordings.
- **Defer**: InputPlumber adopt-vs-build is stage 2's /build question; input
  fast path is a separate process behind the socket from day one (C22) so
  stage 2 stays open either way.
- **How we'd detect wrongness**: C6 noise floor + C9 per-responsibility
  gates + C17 predicted-effect checks + free-run drift measurement (C7);
  mistake list M1-M9 swept at stage end.

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

## Research findings → constraints

### Shadow-diff methodology (researched; adopted constraints)

Plain-language core: comparing "what couchd would do" with "what the old
scripts did" is its own engineering problem, and industry has solved most of
it. The old stack never announces decisions, so we *infer* them from effects
(a process froze, the pad moved) and compare **intents**, not mechanisms.

**C1 — Diff aligned event sequences, not sampled state.** couchd emits typed
intents `(t, subject, verb, args, reason, world-snapshot)`; a separate
inference pipeline turns observed legacy effects into the same shape. Diffs
come in exactly three classes: couchd-only, legacy-only, both-but-different
(process-mining alignment, not equality checks).

**C2 — Abstraction contract written before code.** The comparable verbs are:
`freeze(game)`, `thaw(game)`, `route_pad(kodi|game|steam)`,
`show(window-class)`, `close_steam_menu`, `clear_flag/set_flag(session|
suspended)`, `dismiss(power-menu)`. Mechanism differences (SIGSTOP vs
anything else) are out of scope by definition.

**C3 — Structural passivity (answers mistake M2).** All actions go through an
Executor interface; shadow mode wires in a RecordingExecutor that can only
log. Diffy disables side effects by default, Newman uses Spies; ours is the
same idea enforced by code structure, not a flag check per call site.

**C4 — Lineage, or refuse to diff.** Every intent carries the world snapshot
it was derived from (focused window, pid states, flags, pad presence). If
couchd's snapshot and the legacy-inference snapshot differ, the diff is
discarded as meaningless (Netflix's lineage rule). Two observers that saw
different worlds are not allowed to disagree.

**C5 — Interval-join matching with per-class tolerance windows.** Starting
points (to be recalibrated from our own measured offset histograms, per
/build rule "never import a number"): ±2s for pad routing and window
enforcement, ±5s for freeze/thaw (Proton freeze effects appear late; the
audit showed 18-process trees). Zero tolerance provably loses most true
matches to skew alone. A divergence that self-heals inside the window is a
*timing difference*, counted separately, never a cutover-blocker.

**C6 — Null channel before first real diff.** Run two independent shadow
observers off the same inputs; their disagreement rate is the noise floor.
Acceptance is always relative to that floor, never to zero (Diffy's
primary/secondary trick). Also run the legacy-inference pipeline twice
against the same evening to measure its own precision ceiling.

**C7 — Tracking mode, never free-run.** couchd re-syncs its state machine
from the observed world every tick (control engineering's bumpless
transfer). A free-running shadow's errors compound (imitation-learning
result: O(T²) vs O(T)); teacher-forced agreement understates cutover risk,
so we also periodically measure free-run drift as the true risk number.

**C8 — Debounce with hysteresis.** A divergence class opens at a high
threshold and closes at a lower one (Nagios flap detection shape: last ~21
decision points, recent weighted ~1.5x).

**C9 — Acceptance gate per responsibility** (gestures, transitions, guard
invariants, reconcile), each behind its own COUCHD_OWNS flag: zero permanent
differences across **10-15 clean real sessions** whose union covers the full
state repertoire (unit is transition coverage, not calendar time); every
state-machine transition exercised at least once in shadow; divergence rate
indistinguishable from the C6 noise floor; burn-down curve flat at the
floor, not merely touching it (GitHub's libgit2 gate was 24h/100%/zero,
translated to our once-an-evening cadence).

**C10 — Triage taxonomy from day one.** T1 harness artifact (expect the
biggest early bucket), T2 benign nondeterminism, T3 bug in OLD stack (a real
population; argument *for* cutover, logged separately), T4 bug in couchd
(the only gating bucket), T5 pre-declared deliberate improvement
(whitelisted BEFORE observation or it's indistinguishable from T4), T6 same
decision wrong latency (perceptual threshold 150-250ms for routing/raise).

**C11 — Fallback, not just rollback.** Post-cutover couchd must be able to
abandon a responsibility mid-action back to the old path (Shopify's
per-request fallback caught what their verifier missed). Old stack stays
installed until the stage after next (charter).

**C12 — Timebox.** Each responsibility's shadow has an expiry; if its gate
isn't met, fix the comparator or the design rather than collecting more
evenings.

Sources (primary): github.com/github/scientist README;
github.blog "Move Fast and Fix Things" (libgit2 parallel run: 1%→4-day
ramp→24h zero-mismatch gate); github.com/twitter-archive/diffy (noise-floor
secondary); shopify.engineering storefront-rewrite verifier (normalise
clocks/randomness, per-request-class cutover, fallback); netflixtechblog
"Migrating Critical Traffic" (lineage discard); engineering.zalando.com
"Parallel Run Pattern" (per-endpoint thresholds, non-idempotency);
stripe.com/blog/online-migrations; sre.google/workbook/alerting-on-slos
(two-window); Nagios flap-detection docs; Ross & Bagnell 2010 (compounding
error); bumpless-transfer control literature (jckantor CBE30338, MathWorks).
Noted and rejected: unattributed consultancy numbers ("Uber 72h shadow,
0.3% divergence") that don't trace to any primary source.

### Prior-art constraints (researched; adopted)

Plain-language core: nobody documents this domain — no literature, no Valve
docs. Everything is reverse-engineered by four hobby projects
(gamescope-session/steamos-manager, ChimeraOS's supervisor, ShadowBlip's
InputPlumber/OpenGamepadUI, hhd), so their source code IS the industry
practice, and their magic numbers are other people's calibrations to
re-measure, not constants to adopt. Notably, Valve and ChimeraOS both use
/tmp flag files for deferred intent (reboot-after-Steam-exits), which
validates our pattern for *deferred intent* while confirming live state
belongs in the daemon.

**C24 — Better Steam observation channels than we use today** (measured on
THIS box, X11, no gamescope):
- `~/.steam/steam/logs/gameprocess_log.txt` is Steam's own tracked-process
  ledger: per-appid PID add/remove lines with timestamps, exit codes, launch
  argv, and an authoritative "Remove <appid> from running list". Prefer it
  over pstree guessing for the freeze set (game-pids stays as fallback).
- Same file: `SSGL: UI mode (a->b)` marks Big Picture transitions (4=BPM,
  7=desktop — inferred from 25 local samples, must re-verify, treat mapping
  as config not code).
- Root X atoms Steam writes even without gamescope:
  `GAMESCOPECTRL_BASELAYER_APPID` = `413091, 769` observed live;
  `STEAM_GAMES_RUNNING` (per gamescope source, read from root) absent while
  idle — TEST with a game running; likely the cleanest "game running" bit.
- Subscribe via PropertyChangeMask + select() on the X fd (hhd's approach);
  poll only as backstop.
- Every signal has broken for someone; keep all observation behind one
  interface with a fallback chain (atom → Steam logs → appmanifest → window
  title → /proc), so a Steam update is a config change, not a rewrite.
- CEF remote debugging is the most powerful channel and the only one that
  has bricked Steam UIs; do not enable it.

**C25 — Continuous reassertion, single reconcile function.** Steam re-takes
its own atoms; hhd re-asserts on a 50ms tick and logs "Steam opened, hiding
it". Never paired enter/exit handlers: OGUI has a live bug where the
"disable overlay" branch writes 1 (the log says one thing, the write does
another). Desired-state → observe → diff → apply, and read back what you
wrote. (Matches C13/C16; our steam-input-guard's 6s enforcement loop was
independently the same idea.)

**C26 — Per-app lifecycle state machine with hysteresis.** STARTED / RUNNING
/ MISSING_WINDOW / STOPPING / STOPPED, with the Steam wrapper's lifecycle
tracked separately from the game's; "gone" needs 3+ consecutive missed
checks plus a ~4s missing-window grace (OGUI's calibration; re-measure
ours). Ignore windows under ~20x20px. Log the full state stack every
transition.

**C27 — Ownership hygiene bundle** (for stage 2, but shapes stage-1
interfaces): every override gets a paired auto-release keyed to its
subject vanishing; save-and-restore any foreign state stomped (sticky
cache against transient zero reads); clear input state whenever taking
ownership (stuck-button fix); release in `finally` on every teardown path;
ecosystem-wide exactly ONE grabber may exist (HandyGCCS vs hhd vs
steam-patch all broke on this — the industry converged on a single arbiter
daemon, which is what couchd becomes). Chord timing to Steam: ~80ms between
events, reversed release order, ~350ms XTEST holds, first synthetic send
after connect may drop.

**C28 — Supervision bundle**: child readiness is a message with a deadline
(5s), never a sleep; crash-loop detector with hysteresis (ChimeraOS: 5
failures under 60s → explicit recover() then rearm) where recover() falls
back to the mode that can't fail the same way (Kodi-only, pad released,
nothing frozen); rate-limit restarts (≥5s); teardown deadline + audit (kill,
wait 5s, kill -9 survivors, log ps for each unexpected one); single
instance via flock on a held fd, not a pidfile; systemd user unit with
BindsTo=graphical-session.target, KillMode=mixed.

**C29 — Tag at spawn, discover by tag** (stage-2 upgrade path for
game-pids): inject a COUCHD_ID env var into everything couchd launches and
find trees by scanning /proc/*/environ, plus PR_SET_CHILD_SUBREAPER on the
launcher so Proton orphans reparent to us — the documented fix for exactly
our Proton-suspend class of bug. Freeze leaves-inward (reversed pstree),
signalling both process group and pid.

**C30 — The control socket is a privilege-escalation primitive.**
InputPlumber shipped a root D-Bus API with no authorization at all
(CVE-2025-66005), then with the Polkit check compiled out by default plus a
TOCTOU race (CVE-2025-14338). couchd's socket can inject input and
STOP/KILL processes: unix socket with 0700 dir + SO_PEERCRED uid check from
the first commit, no path-taking methods (fd-passing or fixed paths only),
systemd hardening directives on the unit. Split read-only /status from
mutating calls (steamos-manager's public/private split), and a
feature-discovery call so clients probe rather than assume.

**C31 — Strangler seams**: a small fixed set of no-op-by-default hooks
(recover/post_start/post_shutdown) is how the four scripts become couchd's
actuators; /tmp flags stay only as deferred-intent tokens; couchd has an
explicit not-the-owner mode (OGUI's should_manage_overlay) — which is what
shadow mode is.

Sources: evlaV/steamos-manager; ChimeraOS gamescope-session-plus +
sessions.d/steam + os-session-select; ShadowBlip InputPlumber (D-Bus XML,
composite_device/mod.rs, SUSE CVE writeup security.opensuse.org 2026-01-09)
+ OpenGamepadUI (launch_manager.gd, reaper.gd, state_machine.gd,
overlay_mode_input_manager.gd); hhd x11.py/base.py/faq.md; gamescope
steamcompmgr.cpp atom registration; Alice Mikhaylenko libmanette/HID
writeup; Valve steam-devices udev rules; on-box atom/log measurements
(4 Aug 2026, Steam idle — STEAM_GAMES_RUNNING game-running re-test still
owed).

### Architecture + runtime decision (researched; adopted constraints)

Plain-language core: couchd is a *reconciler*, the pattern Kubernetes
controllers use — don't react to events, react to the world. An event only
means "look now"; the decision is always computed from freshly observed
state. That's what makes missed events survivable (the audit's reconcile()
loop discovered this independently; k8s wrote it down as a design principle:
"level-based, edge-triggered only as an optimization").

**C13 — `reconcile(observed) -> [intent]` takes no event argument.** Events
schedule a reconcile; they never parameterise it. Enforced by signature.

**C14 — Orthogonal state regions, not one flat enum**: input-ownership
(kodi|game|steam-menu), foreground (kodi|game|bigpicture|other), game
(none|running|frozen), tv (on|off), each its own small machine (Harel
statecharts insight; a flat product enum is exactly the state explosion the
audit's /tmp flags papered over).

**C15 — Every transition emits `(region, from, to, reason)` through one
chokepoint** with reasons a closed enum (NetworkManager's state+reason
pattern) — this is what makes the 11pm "why did the pad move" log readable.

**C16 — Anti-entropy tick**: full observe+reconcile every few seconds
regardless of events (k8s resync; the old stack's ~10s reconcile survives
as this tick).

**C17 — Intents carry an expected observable effect + deadline.** In shadow,
log the prediction, then log whether the world got there — free validation
of the model before any real action ever fires (ReplicaSet's
action-tracking-with-timeout, which also becomes the post-cutover retry
mechanism since you can't optimistic-lock X11 or Kodi).

**C18 — All effects through gateways with real/shadow/replay modes.** One
mechanism gives shadow mode, the replay suite, and the eventual cutover
(event-sourcing's gateway rule; also C3's structural passivity).

**C19 — Invariants as closure + convergence** (Dijkstra self-stabilization:
once legal stay legal; from anywhere reach legal within N seconds — bounded
liveness is finitely testable). chaos.py's "8/8 bursts converged in
0.1-1.3s" already measured exactly this; N calibrates from our data
(audit: reconcile repairs within one ~10s tick; chaos convergence ≤1.3s +
transition latencies).

**C20 — Stateful property-based testing** with Hypothesis
RuleBasedStateMachine driving couchd over its socket: random event
sequences (including impossible orderings), model vs daemon agreement
asserted after every step. chaos.py graduates into this.

**C21 — Event log = append-only JSONL we own** (observations AND decisions,
monotonic seq + monotonic clock + wall clock); journald only as a
human-facing mirror (its native protocol guarantees no delivery, so it
can't be the replay corpus).

**C22 — Topology is the expensive mistake, not language.** The stage-2 input
fast path (evdev grab → virtual pad forward) lives in its OWN process from
day one, behind the unix socket. Measured on THIS box: forwarding work in
the same Python process as a busy supervisor = 15ms median / 129ms p99
added wakeup latency (GIL, not CPU); separate process = 24µs / 58µs. Python
per-event cost ~1µs. So: supervisor and input path never share a process.

**C23 — couchd owns process launch of Steam/games** even in stage 1's
design, because stage 2's cheapest pad-hiding lever is per-process
environment (`SDL_GAMECONTROLLER_IGNORE_DEVICES=0x054c/0x0ce6` on launched
processes) plus withholding the hidraw uaccess udev tag. EVIOCGRAB alone
does NOT hide a pad (games see a phantom), and Steam reads the DualSense
over hidraw regardless — grab-only designs are known-insufficient
(sc-controller, libmanette writeups).

**Runtime decision: Python 3.12 for the supervisor.** It's I/O-bound glue
where iteration speed on the state model is everything; the existing
scripts are Python; Hypothesis is the best stateful-PBT tool of any
candidate; python-evdev (grab/UInput) is mature, and uhid-from-Python is
what the kernel's own HID test suite uses (hid-tools, by the kernel HID
maintainer). Node ruled out for input (bindings dead since 2019/2020, no
uhid, single-loop head-of-line blocking). Rust stays the default for the
stage-2 forwarder *if* measurements or DualSense haptics (HID report
packing, where InputPlumber needed git-pinned crates) demand it — with C22
honoured, that later rewrite is a few hundred lines behind a fixed
interface either way. Box facts checked: /dev/uinput ACL already grants
ds2000, no Rust toolchain installed, python-evdev not yet installed
(sdist-only, gcc present).

Sources: k8s design-proposals-archive architecture principles +
controller-runtime reconcile docs/FAQ; Harel 1987 / statecharts.dev;
NetworkManager NMDevice state+reason; sd-event docs; wpa_supplicant
state_machine.h; Dijkstra CACM 1974 + Alpern-Schneider "Defining
Liveness"; Hypothesis stateful docs; systemd Journal Native Protocol;
Fowler Event Sourcing; python-evdev docs/changelog; hid-tools;
InputPlumber Cargo.toml; SDL3 SDL_hints.h; Valve 60-steam-input.rules;
sc-controller evdev/HID wiki; on-box GIL/wakeup benchmarks (agent-run,
scripts preserved in session scratchpad).

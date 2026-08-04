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

### Prior-art constraints (TBR — agent still running)

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

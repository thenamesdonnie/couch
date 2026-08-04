# couchd build charter

How the consolidation gets built without ever breaking the living room.
This governs every couchd work session. The roadmap is in todo.md; the
requirements spec is docs/audits/console-robustness-2026-08.md.

## Prime rule

**The TV works every night.** Donnie should never come home to a broken
console because of an in-progress stage. Every change is either shadowed,
flagged, or instantly revertible. If a stage can't meet that bar, it waits.

## The five disciplines

### 1. Shadow first, cut over second
couchd's first weeks run in SHADOW MODE: it watches the same inputs the old
stack watches, runs its state machine, and logs what it WOULD do - while the
old stack keeps actually doing it. We diff couchd's decisions against
reality until they agree across real evenings (including Donnie's actual
usage, not just synthetic tests). Only then does one responsibility at a
time flip live, behind a switch:

    COUCHD_OWNS="suspend"        # old stack handles everything else

Rollback for any stage is one command (systemd unit swap), and the old
stack stays installed until the stage after next is stable - never delete
the thing you might roll back to.

### 2. The harness is the contract
tools/psfuzz.py and tools/chaos.py must pass IDENTICALLY before and after
every cutover - they encode the state machine's observable behaviour, so
they are the definition of "nothing broke". Extend, never shrink:
- every audit failure mode stays a stageable test (orphaned session, stale
  flag, lost thaw, menu capture...);
- during Donnie's physical-pad sessions, RECORD the real input stream
  (evdev capture) and add replays of real evenings to the suite;
- each new feature lands with its failure modes added as tests first.
Run the full suite before any cutover, after any rollback, and after any
Steam/Kodi update.

### 3. Adopt before build (research-rooted, per /build)
**Every stage BEGINS by invoking the /build skill** - not as a formality:
each stage of couchd is exactly the "substantial new mechanism where a
design decision could be wrong in ways tests won't catch" that /build
exists for (input routing semantics, compositor architecture, shadow-diff
methodology). The /build pass produces the stage's design note: industry
practice + prior art corroborated, concrete constraints extracted,
parameters calibrated on OUR data (the audit, the recorded input replays),
in plain language. No stage writes code before its /build note exists.
Corroborate against prior art and prefer adoption where it fits:
- Stage 2 input ownership: evaluate **InputPlumber** (ShadowBlip) seriously
  before writing our own grab/route/virtual-pad layer - it is this exact
  daemon, maintained, with uhid DualSense targets. Build only what it
  can't do (our session semantics).
- Stage 3: gamescope IS the adoption (never fork it, wrap it).
- Stage 4: smithay/wlroots; study gamescope + cage (kiosk compositor) as
  the closest prior art before writing surface one.
Each stage starts with a short written design note: what we adopt, what we
build, what could be wrong in ways tests won't catch, and how we'd detect it.

### 4. The state machine is explicit and observable
- States, transitions, and invariants are enumerated IN CODE (the audit's
  invariant list becomes assertions), not implied by process behaviour.
- Structured event log + a /status API from day one; the couch app grows a
  debug card showing couchd's live state so problems are visible from the
  sofa, not just from journalctl.
- chaos.py graduates to a property test: any random press sequence must
  converge to a legal state within N seconds. That property, not specific
  scenarios, is the real guarantee.

### 5. Human gates and safe windows
- couchd lives in git from its first commit (and couch/ gets git init at
  the same moment - standing risk finally closed).
- Every stage ends with a 5-minute couch acceptance checklist for Donnie
  (like the 4 Aug pad checklist) - a stage is not "done" until his thumb
  says so.
- Risky cutovers happen in daytime/work hours with monitoring watching;
  evenings run whatever was stable that morning.
- /code-review before each cutover; /handoff at each milestone so any
  session can resume the build cold.

### 6. Parallelise the thinking, serialise the touching
The box is one shared mutable machine - parallel agents must never both
poke the live TV/services. But everything that ISN'T touching the box
fans out to subagents well, and should:
- **Adopt-vs-build research** (each stage's design note): parallel agents
  evaluating candidates (e.g. InputPlumber vs custom grab layer; smithay
  vs wlroots; how gamescope/cage solve X) and reporting back trade-offs.
- **Design review**: independent adversarial reviewers on each stage's
  design note before code, and /code-review before each cutover.
- **Module builds in worktrees** (once git exists): state machine, API
  socket, shadow-diff tooling are independent modules - build in parallel
  isolated worktrees, integrate serially on the box.
- **Log/trace analysis**: shadow-mode divergence triage (couchd said X,
  reality did Y) is read-only and parallelises perfectly.
Exactly ONE agent (or the main session) holds the "box token" at a time
for anything that mutates services, devices, or the screen.

## Failure budget

If a cutover causes two unexplained regressions, it reverts and the stage
goes back to shadow mode - no debugging live on the TV's time. Debugging
happens in shadow, where being wrong costs nothing.

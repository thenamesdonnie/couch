# Second-opinion adversarial reviews — the howff method, for couch

Written 5 Aug 2026, for Sunday's quota reset. This mirrors the process
that worked in venue-finder (`~/venue-finder/docs/audits/`, 26 Jul + 2
Aug): **blind two-reviewer pairs** - gpt-5.6-sol via Codex CLI and a
Claude subagent, given the IDENTICAL prompt, neither seeing the other -
then Fable diffs the two reports, verifies every high-severity claim
against live code/corpus/state, and writes a synthesis. In howff every
sol CRITICAL that got spot-checked verified true, and the disagreements
were exactly where the value was.

## How to run one lens (Donnie's half)

1. Pick ONE lens from the list below. One system per review - the howff
   INDEX proves four short reviews beat one drowning one.
2. Build the prompt: SHARED PREAMBLE + that lens's MISSION block. Paste
   into Codex CLI pointed at `~/couch`, **read-only sandbox**.
3. Same combined prompt to a Claude session as a subagent review (any
   day - the Claude half doesn't need Sunday's quota).
4. Neither sees the other's report. Save them as
   `docs/audits/<lens>-review-<date>-sol.md` and `...-claude.md`.
5. Adjudication: a Fable session reads both, verifies each CONFIRMED
   claim against the code (and the shadow corpus / status.json where
   relevant), resolves splits, writes `...-synthesis.md`, and only then
   fixes what survives. When all lenses are done, an INDEX file with
   cross-cutting themes (howff's T1-T4 section paid for the whole
   exercise - the same root cause showing up in three reviews is the
   real finding).

A finding from any model is a claim, not a fact. Nothing is applied
without the adjudication pass - sol has no memory of this repo and will
occasionally review code that doesn't exist.

---

## SHARED PREAMBLE (paste first, both reviewers)

You are an adversarial second-opinion reviewer for a home-console
control system at `~/couch`. You are read-only in the repo. A different
review fleet swept this codebase on 5 Aug 2026 and its findings are
fixed - your value is what it could not see. Orient with
`docs/couchd-charter.md` and `couchd/README.md` first; skim, don't read
everything. Findings only: no architecture summaries, no praise, no
wholesale-rewrite proposals. Concrete and surgical.

**Hard rules - the system is LIVE on a real TV box:**
- Read-only. Never edit, never commit, never run `systemctl`.
- Never run `tools/fake-pad`, `tools/gesture-sweep`, `tools/fault-rig`.
- Never write `couchd/owns.conf`, `/tmp/game-*`, `/tmp/tv-wake-request`,
  anything under `shadow/` or `recordings/`.
- You MAY run the suites read-only
  (`couchd/.venv/bin/python -m pytest couchd/ tools/ -q`; today 1039
  pass, 7 fail - all 7 in `tools/test_curtain.py`, which covers a
  built-but-deliberately-unwired overlay tool; those 7 are known, do
  not spend your budget on them) and `git log`/`git show`.
  `couchd/gesture.py` is pure - you may exercise it standalone with
  synthetic timestamps. NOTE: codex's read-only sandbox exposes no
  writable temp dir, so pytest cannot actually start under it - do not
  burn turns retrying.
- READ THE LIVE STATE before grading severity:
  `couchd/owns.conf` (what couchd currently executes; today:
  `gestures`), `shadow/status.json` (mode/owns/failures), and
  the switcher addon's `settings.xml` under Kodi's profile (gesture
  bindings; absent = defaults; NOTE Kodi is a Flatpak since 8 Aug, so
  the profile is `~/.var/app/tv.kodi.Kodi/data/userdata/`, NOT `~/.kodi`
  - resolve it via the `kodiprofile` helper rather than assuming).
  Howff's reviews mis-graded severity by assuming config instead of
  reading it.

**System in one page:** a Linux TV box runs Kodi, Steam, and a phone
web remote. A legacy layer of scripts (`legacy-mirror/`, live copies in
`~/.local/bin`) handled PS-button gestures, game launch/suspend/resume,
a post-handoff enforcement window (`steam-input-guard`), and drift
repairs. It is being replaced by one daemon, `couchd`
(`couchd/couchd.py`, ~4800 lines): observes everything (pad evdev,
/tmp flags, process trees, Kodi JSON-RPC :9090, X11, Steam logs), runs
a sampled state machine (regions: gesture/session/pad/input_ownership/
foreground/enforcement), derives intents in a pure `reconcile()`.
Responsibilities flip one at a time via `couchd/owns.conf`; a flipped
one means couchd EXECUTES and legacy yields but keeps logging would-dos.
Ownership is a lease on `shadow/status.json`'s heartbeat (>30s stale =
legacy re-acts). Timing arithmetic is shared in `couchd/gesture.py`
(SR4: both stacks must decide identically; kernel timestamps only, hold
0.9s, double-tap window 0.35s release-to-press). Evidence: every
observation/decision/intent/effect-verdict lands in
`shadow/couchd-YYYYMMDD.jsonl`; the offline differ `tools/shadow-diff`
compares the stacks and its verdict gates the next flip. The phone
remote is Node/Express (`server/`) + Svelte 5 (`web/`), no auth by
design (trusted LAN). Stage 2 (`couchd/inputproc.py` + `couchd/stage2/`)
is a built-but-never-installed evdev-grab input process.

**Fixed on 5 Aug (commits `a414699..d43fb75`) - do not re-report;
`git log` that day before claiming anything here:** coalesced-gesture
drops (consumable tracker markers), the flip orphaning the enforcement
window (couchd now spawns the guard), the differ passing dead actuators
as "gating 0", phone install killing Steam / half-suspend / MJPEG
backpressure / CSRF, fake-pad signal safety, big-picture stale-flag
fight, phantom gestures after BT drops, escape-verb backoff, the
stale-heartbeat dual-acting window.

**CHANGED SINCE 5 AUG - the preamble above was written on the 5th and
the console has moved. `git log --since=2026-08-06` before assuming any
of it:**
- `gestures` was FLIPPED and accepted 6 Aug. couchd EXECUTES the whole
  PS-button vocabulary live; legacy shadows it. Anything touching
  gesture timing is therefore real, not latent.
- The resume-ordering protocol (flag-first thaws, persistence-gated
  repairs) landed 6 Aug (`7d7da3a` and follow-ups).
- The synthetic Steam guide press was DISABLED in both stacks 7 Aug
  (`1ac3ab0`) after it reached Steam's power menu and suspended the
  machine mid-game. Do not propose reviving it.
- 8 Aug: tap and double-tap coexist via DEFERRED DISPATCH (`45b980b`,
  fixed by `ddab8a4`) - a change to the shared gesture mathematics that
  postdates the 5 Aug consumable markers.
- 8 Aug: Kodi 20 (distro) -> Kodi 21.3 (Flatpak), on our own forked
  skin `kodi-addons/skin.couch`. Profile paths and anything crossing
  the sandbox changed (`74ed172`, `6fa2eb5`).
- 6 Aug hardware: RX 9070 XT (AMD/Mesa, NVIDIA purged) and an LG C5
  OLED at 4K120. Stage 3 (gamescope) is open; only a wrapper is
  committed.

**Known and deliberately open - not findings:** legacy bugs 1/2/4
(big-picture flag lifecycle, "bigpicture" appid literal, guard pidfile
on normal exit; whitelisted in the differ); the 1.2s settle window
unmodeled in stage 1 (owner ruling pending); phone suspend/quit not
yielding to couchd (ruling pending); `hold=switcher` handing off
mid-press (pinned decision, challenged, ruling pending); couchd not
autostarting on boot; Kodi's own PS-hold poweroff menu (console-level,
known); the 7 failing `tools/test_curtain.py` tests (unwired tool).

**Output format (strict):** numbered findings, most severe first. Each:
real `file:line`; one-sentence defect; a CONCRETE failure scenario
(inputs/state -> wrong behaviour - no scenario, no finding); severity
CRITICAL (could misbehave during an evening's use or corrupt the
flip/evidence machinery) / HIGH (wrong decisions or data) / MEDIUM
(latent) / LOW (hygiene); and CONFIRMED (traced end to end) vs
PLAUSIBLE (could not fully verify) - never dress the second as the
first. Cap ~25, deduped; an empty severity is a fine answer. Close with
one line per region you actually attacked and found sound, then a
**§Meta**: what you couldn't verify and why.

---

## RUN LOG

| lens | sol | claude | synthesis |
|---|---|---|---|
| 1 stage 2 input process | ✅ 9 Aug, `...-sol.md` (10 findings, 2 CRITICAL) | ✅ 9 Aug, `...-claude.md` (21 findings, 4 CRITICAL) | ✅ `...-synthesis.md` — 14 code fixes + tests shipped, 5 open for a ruling |
| 2 daemon core | ❌ | ❌ | ❌ |
| 3 legacy + seam | ❌ | ❌ | ❌ |
| 4 phone arm | ❌ | ❌ | ❌ |
| 5 evidence machinery | ❌ | ❌ | ❌ |

**What lens 1 taught us about running these.** Blindness has to be
STRUCTURAL, not honour-based: sol's report was committed before the claude
half ran, so the second reviewer was given a detached worktree pinned to the
commit before it, where the file simply does not exist. Do that from the
start next time - run both halves before committing either. The pair earned
its cost: they agreed on both CRITICALs by different routes (sol via the pad
NAME filter, claude via the udev PERMISSIONS - both true, and they compound),
and every split was a severity disagreement rather than a contradiction, with
claude's grade winning twice. Neither reviewer could run the suite in its
sandbox, so both reasoned statically; budget for the adjudicator verifying
every claim against the code, which is where the real time went.

---

## LENS MISSIONS (pick one per review)

### Lens 1 — stage 2 input process (RUN 9 Aug, sol half only)

MISSION: `couchd/inputproc.py`, `couchd/stage2/` (INSTALL.md, runbooks,
udev rules), `couchd/test_inputproc.py`. This process will one day sit
between the physical pad and everything else; a bug becomes total input
loss in the living room. Hunt: SR4 agreement - inputproc uses
`PressTracker.poll()` where stage 1 does not, and it PREDATES the 5 Aug
consumable markers (`hold_release_k`/`double_tap_k`) - construct any
event sequence the two stacks classify differently. The
withhold/re-inject logic (a press withheld from the virtual pad that
turns out to be a tap must be re-injected with the chord spacing): what
does a crash between withhold and re-inject do? Grab/ungrab failure
paths, the evdev grab held across daemon death, the udev rules'
match breadth, the E-runbook's claimed invariants vs the code.

### Lens 2 — daemon core cross-region behaviour

MISSION: `couchd/couchd.py` (the `TRANSITIONS` table ~line 730, guards
above it, `reconcile()`, the observers), `couchd/x11.py`,
`couchd/owns.py`. The 5 Aug fleet verified each region ALONE. Hunt
multi-region interleavings: session ending mid-gesture, pad reconnect
during an enforcement window, foreground flapping during a handoff,
Kodi restarting mid-suspend. `x11.py` end to end: python-Xlib with no
socket timeout on the shared thread - error paths, Display lifecycle,
compositor restart. `gesture.py` as mathematics: kernel-clock
extrapolation, marker/`double_armed`/`settle_swallows` interactions -
find a timestamp sequence that double-fires or drops.

### Lens 3 — the legacy stack and the seam

MISSION: `legacy-mirror/pad-home-watcher` (~1400 lines), `game-launch`,
`steam-input-guard`, `tv-waker`, plus `couchd/owns.py` as the lease both
sides read. Nobody has read these end to end since the yield gates and
the game-launch flock were bolted on. Hunt: yield-gate failure modes
(owns.py unimportable mid-run, stat-cache staleness, the 30s lease at
its boundaries), the new flock's interaction with every verb arm and
with the backgrounded guard spawns, signal handling, what each script
does when its /tmp flags are half-written, and any place the two stacks
can still both act or both abstain on one responsibility.

### Lens 4 — the phone arm beyond the hotspots

MISSION: `server/index.js` (~900 lines - only its hotspots were
reviewed), `server/kodi.js` connection state machine, `server/screen.js`
ffmpeg lifecycle, `server/jellyfin.js` (direct sqlite reads of Kodi's
DB), the request/queue endpoints, then `web/src` by component (never
reviewed at all: WebSocket reconnect, polling, anything that can hammer
the server or wedge the phone mid-evening). Also `kodi-addons/`,
especially `script.couch.switcher` - it runs inside Kodi's python and
draws the dialog the flagship gesture depends on.

### Lens 5 — the evidence machinery as a statistician

MISSION: `tools/shadow-diff` (post-5-Aug: it now gates on action
failures, missed effects, SHADOW-ONLY rows, pid-set repeats - check the
new arithmetic for double-counting and for pairs the matcher
(verb/subject/time-window) can mispair, grading agreement from noise),
`tools/test_shadow_diff.py` for tests that enshrine bugs as expected
output, `tools/intents-archive`, and the ShadowLog writer in
`couchd/couchd.py`. The differ's verdict gates responsibility flips: a
false green here is the most expensive bug the repo can host.

---

## Adjudication template (the Fable session's half)

For the synthesis doc, follow howff's shape
(`~/venue-finder/docs/audits/*-synthesis.md`):
per finding - AGREE/DISAGREE between reviewers, VERIFIED/REFUTED against
code (quote the line), severity re-grade with reasoning, fix applied or
queued or declined-with-reason. Splits get resolved by reading the live
state, not by trusting either reviewer. End with cross-cutting themes
once multiple lenses exist. File name:
`docs/audits/<lens>-review-<date>-synthesis.md`, and add the row to a
dated INDEX when the set completes.

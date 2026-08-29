# Lens: couchd core correctness (29 Aug 2026)

## SHARED PREAMBLE

You are an adversarial second-opinion reviewer for a home-console control
system at `~/couch`. You are read-only in the repo. Earlier review fleets swept
this codebase and their findings are fixed. Your value is what they could not
see. Orient with `docs/couchd-charter.md` and `couchd/README.md` first; skim,
don't read everything. Findings only: no architecture summaries, no praise, no
wholesale-rewrite proposals. Concrete and surgical, with file:line.

**Hard rules - the system is LIVE on a real TV box, someone is using it now:**
- Read-only. Never edit, never commit, never run `systemctl`.
- Never run `tools/fake-pad`, `tools/gesture-sweep`, `tools/fault-rig`.
- Never write `couchd/owns.conf`, `/tmp/game-*`, `/tmp/tv-wake-request`,
  anything under `shadow/` or `recordings/`.
- You may read `git log`/`git show`. Codex's read-only sandbox exposes no
  writable temp dir, so pytest cannot start under it. Do not retry it.
- READ THE LIVE STATE before grading severity: `couchd/owns.conf` (what couchd
  actually executes today), `shadow/status.json`, and the switcher addon's
  `settings.xml` under Kodi's profile. Kodi is a Flatpak, so the profile is
  `~/.var/app/tv.kodi.Kodi/data/userdata/`, NOT `~/.kodi` - resolve it via the
  `kodiprofile` helper rather than assuming. Past reviews mis-graded severity by
  assuming config instead of reading it.

**System in one page:** a Linux TV box runs Kodi (Flatpak), Steam, the shadPS4
emulator, and a phone web remote. `couchd` (`couchd/couchd.py`) observes pad
evdev, /tmp flags, process trees, Kodi JSON-RPC and X11, runs a sampled state
machine (regions: gesture/session/pad/input_ownership/foreground/enforcement),
and derives intents in a pure `reconcile()`. Responsibilities flip one at a time
via `couchd/owns.conf`; a flipped one means couchd EXECUTES and the legacy
scripts yield but keep logging what they would have done. Stage 2 is live:
couchd owns gestures and input, `inputproc.py` grabs the pad so Steam never sees
the guide press. Reconcile, transitions and guard are still legacy.

## MISSION

**Lens: core correctness of the daemon itself.** Not the transition/curtain
path (a separate review covers that), not the web app, not the support scripts.

Focus on `couchd/couchd.py`, `couchd/inputproc.py`, `couchd/gesture.py`,
`couchd/supervisor.py`, `couchd/owns.py`, `couchd/x11.py`.

This daemon runs unattended for days on a machine that is someone's television.
The failure that matters is not a crash, it is **silently doing the wrong thing
and staying up**, or **wedging while appearing healthy**. Hunt for:

- **State machine soundness.** Regions that can disagree with each other.
  States reachable that no transition can leave. Sampling assumptions that break
  when a sample is missed, late, or duplicated. Anything that treats a sampled
  observation as an edge.
- **Purity violations in `reconcile()`.** It is documented as pure. Verify that.
  Hidden I/O, time reads, mutation of inputs, or dependence on module state
  would each undermine every test written against it.
- **Ownership flips.** `owns.conf` decides whether couchd executes or only
  logs. Look for paths that act regardless of ownership, or that read ownership
  once and cache it, or where legacy and couchd could both act.
- **Process and resource lifecycle.** Leaked file descriptors, evdev grabs not
  released on error paths, child processes not reaped, threads that die
  silently leaving the daemon apparently alive. There is a documented history of
  zombie pids on this box.
- **Error handling that swallows.** Bare excepts, retry loops with no ceiling,
  and anywhere a failure downgrades to a no-op without surfacing. On this
  system a silent no-op means the TV stops responding to the pad and nobody
  knows why.
- **Time and clock assumptions.** Monotonic vs wall clock, timeouts that assume
  a sample rate, anything that would misbehave across a suspend/resume or an
  NTP step.
- **Concurrency.** Shared mutable state between the sampler, the evdev reader
  and any timer, without clear ownership.

Prefer findings that explain a symptom the user would actually notice. For each:
file:line, the precise sequence that triggers it, why existing guards miss it,
and the smallest safe change. Rank by confidence, and explicitly separate what
you verified in code from what you are inferring.

Do not change any code. Review only.

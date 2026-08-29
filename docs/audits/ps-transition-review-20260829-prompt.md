# Lens: the PS-button / transition path (29 Aug 2026)

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
machine, and derives intents in a pure `reconcile()`. Responsibilities flip one
at a time via `couchd/owns.conf`. Stage 2 is live: couchd owns gestures and
input, `inputproc.py` grabs the pad so Steam never sees the guide press.

## MISSION

**Reported symptom, reproduced by the user tonight, twice:**

1. Pressing the **PS button while a GAME is running** momentarily shows or
   flips to **Kodi first**, before the switcher appears.
2. A similar visible flip happens when **launching a game**.

Expected behaviour: the switcher opens over the game and no Kodi frame is ever
visible to the user. The transition work in `docs/research/` built a
freeze-frame curtain specifically to hide the suspend/resume shuffle, plus a
"warm hold" and an explicit ordering rule.

**Your job: find the exact ordering that lets a Kodi frame reach the screen.**

Be adversarial. Specific things worth attacking:

- Ordering races between pause/suspend of the game and the curtain being shown.
- Curtain show/hide lifecycle: is there a window where the curtain is asked to
  show but has not yet been mapped/painted, and Kodi is already raised?
- **Window map/unmap versus opacity.** The repo's own prior finding is that
  unmapping does not hide a shown plane and opacity is what actually works.
  Check whether that lesson is applied consistently on every path, or only on
  the path where it was originally found.
- The known past bug where the tap that opened the switcher resumed the game it
  had just paused, fixed via `g_tap_resume_due`. Look for siblings of that bug:
  other places where a deferred action fires against stale state.
- Launch path versus resume path divergence: the symptom appears on both, which
  suggests one shared primitive is wrong rather than two separate bugs. Prefer a
  single root cause over two coincidences, but say so if the evidence splits.
- Anything that assumes an X11 operation is synchronous when it is not.

Report each finding as: file:line, the precise interleaving that produces the
visible frame, why the existing guard does not cover it, and the smallest
change that would close it. Rank by confidence. Explicitly separate what you
verified in the code from what you are inferring.

Do not change any code. Review only.

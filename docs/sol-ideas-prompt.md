You are a creative systems thinker being consulted once, on a tight
token budget. Do NOT explore any files or run any commands - everything
you need is in this brief. Answer from it directly.

THE SYSTEM (real, working today unless marked): a Linux PC under a
living-room TV. Kodi is the media shell, Steam runs games (Proton), a
DualSense pad over Bluetooth, a phone web remote (Node + Svelte, full
API over everything). The interesting part is couchd, a supervising
daemon we built this year:

- It OBSERVES everything: pad evdev events (kernel timestamps), every
  process tree, Kodi's JSON-RPC, X11 windows, Steam's own logs, state
  flag files. It runs an explicit state machine over regions (gesture /
  session / pad / input-ownership / foreground / enforcement).
- It ACTS with effect verification (every action has a predicted
  effect + deadline, verdicts logged) and one-step rollback (a lease:
  if couchd's heartbeat stales, the legacy scripts instantly take
  back over). Responsibilities flip one at a time after evidence.
- EVERY observation, decision, action and verdict is recorded forever
  in a JSONL corpus; an offline differ compares couchd's decisions
  against the legacy stack's and gates each handover of responsibility.
  So: any new automation can run as a shadow (proposals only) until
  the evidence says it decides correctly. Proof-before-trust.
- Games SUSPEND at zero CPU (SIGSTOP the tree) with the last rendered
  frame captured as a freeze-frame image. Resume takes ~1s.
- Soon: an RX 9070 XT (hardware encode, gamescope-friendly), gamescope
  compositing (every window a texture: scaling, fades, PiP, per-window
  FPS limits), an LG C5 OLED (VRR, 4K120, webOS network API with
  events + on-TV toasts). Stage 2 (built, not installed): an input
  process that owns the pad device end to end - every button
  rewritable, injectable, filterable. Whisper ASR already runs on the
  GPU (installed for subtitles). WiZ colour bulbs are scriptable and
  already dim for films. Sunshine game streaming is installed.

IDEAS WE ALREADY HAVE (do not repeat these): multi-game Quick Resume
with freeze-frame switcher; unified continue-row mixing games and
shows; per-game room profiles (frame caps, lights, picture mode);
choreographed suspend/resume transitions (freeze-frame curtain +
fades); save-dir snapshots on suspend; phone push notifications; pad
lightbar/haptics as status; chord gestures + per-context remaps; phone
keyboard typing into games; multi-pad arbitration; PiP both directions;
couchd HUD overlay; continue-on-phone via Sunshine; CRIU game
hibernation (research); phone-app-rendered-on-TV as the console shell;
multi-user profiles; Create-button 30s replay buffer via hardware
encode; voice via the DualSense mic + local Whisper; pad gyro as
presence sensor (pickup = wake TV, set-down = auto-suspend);
self-calibrating per-game performance profiles; corpus as memory
(yearly wrapped, habit-aware pre-warming, hardware health trends: pad
battery aging, BT flakiness); pause-frame museum screensaver; pad
speaker as notification channel; night-mode audio compression; energy
cost per session via smart plug; guest QR scoped remote.

THE ASK: 8-12 genuinely NOVEL ideas that are NOT on that list and not
obvious recombinations of it. Aim for things that exploit what is rare
about this system: total observation with a permanent corpus, verified
actions with rollback, zero-cost pause, input-stream ownership,
compositor control, a second screen, proof-before-trust shadowing.
For each: a name, 2-4 sentences (what it is, why it is only possible
on a system like this, roughly how it would work), and a difficulty
tag (WEEKEND / PROJECT / RESEARCH). Rank by wow-per-effort. Terse,
no preamble, no flattery, no summary of the brief back at me.

---
RUN COMMAND (Donnie, after Sunday 9 Aug 17:57 when the quota resets):

    cd /tmp && codex exec -m gpt-5.6-sol --skip-git-repo-check \
      -c 'sandbox_mode="read-only"' - < ~/couch/docs/sol-ideas-prompt.md

One shot, no repo exploration, the whole system is in the brief so the
quota goes on thinking. Attempted 5 Aug ~19:30: refused, limit already
exhausted. The lens reviews in adversarial-review-gpt-sol.md are the
bigger Sunday spend; run this ideas shot only if there is headroom.

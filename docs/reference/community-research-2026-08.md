# Community research: couch/console Linux projects worth stealing from

Researched 5 Aug 2026 (32 web searches, links verified by the researcher).
Companion to docs/realm-of-possibility.md - this is what OTHER people
have built. The top-10 ranking at the bottom is calibrated to OUR stack.

## The two findings that change our own plans

1. **CRIU game hibernation is a confirmed dead end.** The GPU
   checkpointing work (CRIU 4.0 CRIUgpu, the amdgpu plugin, NVIDIA
   cuda-checkpoint) is COMPUTE-ONLY (ROCm/KFD, CUDA). Nothing can
   checkpoint a live Vulkan swapchain, a DRM/X11/Wayland connection, or
   Proton's wineserver. Nobody has ever gotten a Proton game through
   CRIU. Consequence: our SIGSTOP + freeze-frame architecture is the
   CORRECT design, not a compromise, and the tier-4 hibernation spike
   in realm-of-possibility.md should be re-scoped or dropped.
   https://www.criu.org/GPU_Checkpointing
   https://github.com/checkpoint-restore/criu/blob/criu-dev/plugins/amdgpu/README.md

2. **The missing piece of real Quick Resume exists and nobody has built
   it: process_madvise(MADV_PAGEOUT).** One process can force another's
   anonymous pages out to swap/zram while preserving them (Linux 5.4+,
   private pages only). ChromeOS uses exactly this on backgrounded tabs
   (25% faster switches). Applied to games SIGSTOPped for N minutes:
   multiple parked games on 32GB without OOM - actual Xbox Quick Resume,
   which no Linux project appears to have shipped. ~50 lines + a timer
   in couchd.
   https://man7.org/linux/man-pages/man2/process_madvise.2.html
   https://lwn.net/Articles/790123/

## Distros and daemons (what the couch-Linux world ships)

- **Bazzite**: boots to Big Picture, HDR in game mode, CEC; the
  stealable idea is the `ujust` menu - named, idempotent system chores
  (setup-htpc, rollback) as discoverable one-liners. A "Chores" list in
  our phone app mapping to recipe scripts is the same idea with better
  UX. https://github.com/ublue-os/bazzite
  https://docs.bazzite.gg/Installing_and_Managing_Software/ujust/
- **ChimeraOS `chimera` web app**: phone-browser console admin -
  install Epic/GOG/Flathub games, upload ROMs, TDP, power. Proves the
  phone-as-admin pattern; features ours lacks: content install from
  the phone, artwork management. https://github.com/chimeraOS/chimera
- **gamescope-session-plus**: generalized session wrapper - CLIENTCMD
  can be KODI, not just Steam. The clean path to Kodi inheriting the
  HDR/VRR/scaling pipeline on the C5, with couchd as session switcher.
  https://github.com/ChimeraOS/gamescope-session
- **Handheld Daemon (hhd)**: the closest existing thing to couchd's
  shape. Steal: double-tap-a-system-button opens the daemon's OWN
  gamescope overlay; everything exposed as one declarative settings
  tree rendered by overlay + CLI alike. https://github.com/hhd-dev/hhd
- **InputPlumber**: DBus input router with Intercept Mode (steal input
  off a device, receive over DBus) and N-devices-into-one-virtual-pad.
  NOTE: we declined InputPlumber for stage 2 with receipts (root-only,
  crash-leaves-pad-chmod-000, no kernel timestamps over DBus) - the
  intercept-mode CONCEPT validates our stage-2 withhold design; the
  compositing trick is worth stealing for multi-pad/guest.
  https://github.com/ShadowBlip/InputPlumber

## gamescope tricks

- `--reshade-effect <path>`: apply ReShade shaders to ANYTHING on
  screen without touching the game - warm/dim night shader, CRT filter
  for retro, desaturate-on-pause. Highest delight per line of code.
  https://wiki.archlinux.org/title/Gamescope
- `gamescopectl`: retune a LIVE gamescope (FPS cap, sharpness, VRR
  quirks) - couchd can adjust the compositor per session state.
- gamescope exposes its COMPOSITED OUTPUT as a PipeWire video node:
  one free zero-overhead capture of exactly what the TV shows - for
  freeze-frames, a live phone preview, and dominant-color ambient
  lighting. https://github.com/ValveSoftware/gamescope/issues/213
- The external-overlay slot is SINGULAR and mangoapp squats it on
  SteamOS-alikes - own that slot or render via MangoHud's
  custom_text_center. https://github.com/flightlessmango/MangoHud/issues/775
- ScopeBuddy: per-game gamescope flag profiles (we'd key ours off
  couchd's appid knowledge). https://docs.bazzite.gg/Advanced/scopebuddy/
- C5 planning warnings: gamescope 3.16.17 shipped an HDR regression
  (pin versions); HDR+VRR together unstable for some; OLED VRR
  near-black gamma flicker is panel-physics - consider a per-title
  "VRR off, refresh-locked" policy for dark slow games.
  https://github.com/ValveSoftware/gamescope/issues/2018
  https://tftcentral.co.uk/articles/exploring-and-testing-oled-vrr-flicker

## Suspend/resume prior art

- wl-freeze (hyprfreeze): SIGSTOP the focused window's tree; documents
  two hazards to TEST OURS AGAINST: native-Linux games' audio can die
  under PipeWire on suspend, and a paused XWayland game can trap the
  pointer for other XWayland apps. https://github.com/Zerodya/hyprfreeze
- SDH-PauseGames (Decky): auto-pause on focus loss, and PAUSE-ALL
  BEFORE SYSTEM SUSPEND (fixes crackling audio + emulator freezes
  across S3) - couchd should SIGSTOP everything before systemctl
  suspend and SIGCONT after. https://github.com/popsUlfr/SDH-PauseGames

## DualSense on Linux

- dualsensectl: lightbar, player LEDs, MIC, SPEAKER, volume, trigger
  effects from the CLI. https://github.com/nowrep/dualsensectl
- The pad is a real ALSA device (mono speaker + jack + headset mic;
  Linux 6.18 adds proper jack detection). Haptics = ultrasonic PCM to
  channels 2/3 of the 4-channel interface; needs one WirePlumber rule;
  a working helper exists.
  https://github.com/HotspringDev/DualSense-haptic-helper
- trigger-control: adaptive triggers over BT on Linux.
  https://github.com/Etaash-mathamsetty/trigger-control
- Gyro: JoyShockMapper reads DualSense motion directly (gyro as a
  point-at-screen cursor for Kodi bypasses Steam Input entirely).
  Nobody has published controller-as-presence-sensor - unoccupied.
  https://github.com/JibbSmart/JoyShockMapper

## Clips, voice, lighting, saves, identity

- **gpu-screen-recorder**: the ShadowPlay replacement; AMD VAAPI; RAM
  replay buffer; `-ipc` + `gsr-cli save-replay 30` + `-sc` completion
  hook = a clean two-way contract with couchd for Create-button clips.
  https://git.dec05eba.com/gpu-screen-recorder/about/
- Sunshine prep-cmd do/undo has rollback semantics (undo unwinds on
  failure) - same philosophy as ours; caveat: undo on session quit,
  not client disconnect. Apollo fork ships a built-in virtual display.
- **Speech-to-Phrase** (Home Assistant): closed-vocabulary STT built
  from your actual entity names - faster and far more accurate than
  Whisper for command grammar; Whisper stays the open-ended fallback.
  Nobody found combining the DualSense's OWN mic with a local voice
  pipeline: unoccupied niche.
  https://www.home-assistant.io/blog/2025/02/13/voice-chapter-9-speech-to-phrase/
- **HyperHDR** (over hyperion.ng) for ambient light: PipeWire/Portal
  accelerated capture, HDR tonemapping. For WiZ (no strips): a slow
  1-2Hz dominant-color loop with heavy smoothing off the gamescope
  PipeWire node respects WiZ's UDP limits.
  https://www.linuxlinks.com/hyperhdr-ambient-lighting-implementation/
- **Ludusavi**: save backup driven by PCGamingWiki's location database
  (covers non-Steam/emulator saves) - better than hand-rolling our
  save-path map; hook it on couchd's suspend/exit events.
  https://github.com/mtkennerly/ludusavi
- **Identity/guest is UNSOLVED everywhere** (Steam: a decade of asks,
  no guest mode; Deck parental controls are a PIN and not much else).
  The opening is identity-by-controller: pad connect events -> whose
  pad -> Kodi filter, Steam account, light scene, hours, save
  namespace. Genuinely new territory for us.
- CEC as a network service: script.json-cec / pyCEC's TCP bridge /
  cec-dpms (relevant only if a CEC adapter ever arrives; the 4070 and
  the 9070 XT pass no CEC).
- Delight shelf: Decky Animation Changer (boot animations), an e-ink
  now-playing panel (~£25 Pi Zero + Waveshare), MangoHud
  custom_text_center as a text channel into the overlay + frametime
  CSVs into the corpus, graftorio2 (game telemetry -> Grafana).

## The researcher's top 10 for our stack (wow-per-effort)

1. Pad-mic push-to-talk -> Speech-to-Phrase grammar -> couchd verbs
   (Whisper fallback) - nobody has published this.
2. process_madvise pageout of cold frozen games -> real multi-game
   Quick Resume - unbuilt anywhere.
3. gpu-screen-recorder -ipc as couchd's replay buffer (Create-button
   clips into the phone app).
4. Pad as output device: lightbar state colours, speaker chirps,
   ultrasonic haptics.
5. Consume gamescope's PipeWire node: freeze-frames, phone live
   preview, WiZ ambient colour.
6. --reshade-effect room moods (night shader, CRT, pause desaturate).
7. Ludusavi on suspend/exit lifecycle events.
8. Kodi inside gamescope via gamescope-session-plus CLIENTCMD (pin the
   gamescope version).
9. Identity-by-controller guest/profile system.
10. ujust-style chores menu + a double-tap on-TV couchd overlay (own
    the single overlay slot).

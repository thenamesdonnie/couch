# Couch

The software that runs a living-room PC as an appliance: a phone is the remote, a game pad is the
only thing you need on the sofa, and nothing ever asks you to find a keyboard.

It drives Kodi, Steam, a TV over HDMI-CEC, Jellyfin and the lights, from a Svelte web app on your
phone and from a daemon that watches the pad. Python and Node, systemd units, no cloud service in
the middle.

## The parts

| directory | what it is |
| --- | --- |
| `server/` | Node server: static front end, JSON API, a WebSocket for live state. **The only process holding credentials** — the phone never talks to Kodi, Steam, the TV or the bulbs directly. |
| `web/` | the phone app, Svelte and Vite |
| `couchd/` | Python daemon: owns the game pad, reads gestures, decides what the box should be doing, and reconciles reality against that decision |
| `kodi-addons/` | a Kodi skin and service add-ons |
| `tools/` | 123 single-purpose scripts: capture, diagnostics, patching, a fake pad for testing without hardware |
| `docs/` | design documents, audits, adversarial reviews, acceptance runs |
| `systemd/` | the units that keep it all up |

## Design ideas worth stealing

**The daemon shipped in shadow mode first.** `couchd` replaced four separate watcher scripts. Rather
than cutting over, it ran beside the old stack for weeks saying only what it *would* have done, and
its log was compared against what actually happened, evening after evening, until they agreed.
Passivity was structural rather than a flag: with `owns.conf` empty, no acting executor is ever
constructed, so there is no switch anyone can forget. `docs/couchd-stage1-design.md` has the whole
argument.

**The pad is owned, not polled.** udev rules fence the controller to the daemon so a game cannot
steal it mid-gesture, with the real device scoped by its own MAC and a model-scoped fallback.
`couchd/stage2/` documents the flag-day procedure.

**Credentials live in exactly one process.** Everything the phone can do is an API call to the
server. Nothing else on the network needs a token.

**The test suite runs without the hardware.** `tools/fake-pad` synthesises controller input, so the
gesture engine, the reconciler and the input processor are all testable on any machine. 581 tests.

## Run it

```sh
cp .env.example .env    # ports, LAN address, Kodi and Jellyfin credentials
npm install && npm --prefix web install && npm --prefix web run build
node server/index.js    # phone app on COUCH_PORT, default 8790
```

The daemon is separate and optional:

```sh
python3 -m venv couchd/.venv && couchd/.venv/bin/pip install -r couchd/requirements.txt
couchd/.venv/bin/python -m pytest couchd/ -q
```

Install the systemd units from `systemd/` and `couchd/*.service` to have it survive a reboot.

## Not included

The Bloodborne tooling in `tools/` (`bb-*`) patches and inspects a specific game's files and is
useless without your own copy. It is left in because the crash-watching and event-tailing patterns
generalise.

## Licence

MIT.

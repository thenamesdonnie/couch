# legacy-mirror

(`kodi-tv` joined 8 Aug when it grew the Kodi-21 flavour switch;
`pause-snap` the same evening, when it started stamping the Games row's
content revision - the fix for a paused card that never cleared.
`tv-waker-webos` joined 9 Aug when it grew `headphone_watch` - note that it
is the LG/webOS twin `tv-waker` execs into, so the two must be mirrored
together or the pair on disk disagrees about which TV exists.)

Versioned snapshots of the console scripts that live (and execute) at
`~/.local/bin/` - nine of them now, not the original three. They are OUTSIDE this repo at runtime; this
mirror exists so the couchd yield edits are in git history and a broken
edit can be restored.

Deploy = `cp legacy-mirror/<name> ~/.local/bin/<name>` (keep the exec bit).
The mirror is refreshed by hand whenever the live scripts change; if the
two disagree, the live file in `~/.local/bin` is the truth.

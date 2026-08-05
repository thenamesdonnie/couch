# legacy-mirror

Versioned snapshots of the three legacy console scripts that live (and
execute) at `~/.local/bin/`. They are OUTSIDE this repo at runtime; this
mirror exists so the couchd yield edits are in git history and a broken
edit can be restored.

Deploy = `cp legacy-mirror/<name> ~/.local/bin/<name>` (keep the exec bit).
The mirror is refreshed by hand whenever the live scripts change; if the
two disagree, the live file in `~/.local/bin` is the truth.

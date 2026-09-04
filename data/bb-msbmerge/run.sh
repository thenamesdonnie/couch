#!/bin/sh
# Rebuild the merge from scratch.  Run from anywhere.
S=/tmp/claude-1000/-home-ds2000-couch/bb334b67-8a0b-4c04-8c9b-e05214c498f5/scratchpad
PY=$S/ss313/bin/python
V=/home/ds2000/couch/data/bb-mod-backups-copy/BloodborneEnhanced-0.11.2-fix9/files/map/mapstudio
E=/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/map/mapstudio
R=$S/rmap/BBReborne_map/map/mapstudio
O=$S/merged-map/map/mapstudio
mkdir -p "$O"
$PY $S/msbmerge/rt.py "$V"          # acceptance: byte-identical round trip
$PY $S/msbmerge/mergemsb.py "$V" "$E" "$R" "$O" $S/msbmerge/REPORT.txt
$PY $S/msbmerge/verify.py "$R" "$O"     # independent re-check of the written files
$PY $S/msbmerge/entities.py "$R" "$O"   # every entity ID from both mods survives
$PY $S/msbmerge/analyse.py "$R"         # overlap + field usage census

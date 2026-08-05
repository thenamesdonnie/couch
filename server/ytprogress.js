// Resume positions and watched flags for in-app YouTube playback. Kodi's
// YouTube plugin only wires resume points inside its own menus, and once a
// video resolves Kodi reports the raw googlevideo url, so the server remembers
// which id it launched and records the player clock against it. Persisted to
// data/yt-progress.json, written at most every few seconds and trimmed so it
// can't grow without bound.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const FILE = path.join(os.homedir(), 'couch/data/yt-progress.json');
const WATCHED_AT = 0.9; // fraction of the runtime that counts as watched
const MIN_TRACK = 20;   // seconds watched before a resume point is worth keeping
const KEEP = 200;       // most-recent entries kept on save

let db = {};
try { db = JSON.parse(fs.readFileSync(FILE, 'utf8')); } catch { /* fresh start */ }

let dirty = false;
setInterval(() => {
  if (!dirty) return;
  dirty = false;
  const entries = Object.entries(db).sort((a, b) => b[1].at - a[1].at).slice(0, KEEP);
  db = Object.fromEntries(entries);
  fs.writeFile(FILE, JSON.stringify(db), () => {});
}, 5000).unref();

// Record where a video is up to. Anything under two minutes long isn't worth
// resuming; near the end it flips to watched and the resume point is dropped.
export function track(id, position, duration) {
  if (!id || !duration || duration < 120 || position < MIN_TRACK) return;
  db[id] = position / duration >= WATCHED_AT
    ? { watched: true, at: Date.now() }
    : { pos: Math.floor(position), dur: Math.floor(duration), at: Date.now() };
  dirty = true;
}

export function resumePoint(id) {
  const e = db[id];
  return e && !e.watched ? e.pos : 0;
}

// Progress decorations for a result list: fraction watched and watched flag.
export function decorate(results) {
  return results.map((r) => {
    const e = db[r.id];
    if (!e) return r;
    if (e.watched) return { ...r, watched: true };
    return { ...r, resumeSecs: e.pos, progress: e.pos / e.dur };
  });
}

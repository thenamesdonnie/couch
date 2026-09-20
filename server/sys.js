// Everything outside Kodi: game sessions via game-launch, the DualSense,
// the TV, the lights. All user-level, nothing here may want sudo.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, execFile } from 'node:child_process';

import { COUCHD_STATUS, ROOT } from './config.js';

const HOME = os.homedir();
const BIN = path.join(HOME, '.local/bin');
const LAUNCHER = path.join(BIN, 'game-launch');
const SESSION = '/tmp/game-session';
const SUSPENDED = '/tmp/game-suspended';
const PAD_MAC = process.env.COUCH_PAD_MAC || 'AA:BB:CC:DD:EE:FF'; // your pad's Bluetooth MAC

function readIf(file) {
  try { return fs.readFileSync(file, 'utf8').trim(); } catch { return null; }
}

// --- game session ---

export function gameSession() {
  const session = readIf(SESSION);
  const suspended = readIf(SUSPENDED);
  const parts = session ? session.split(/\s+/) : [];
  return {
    active: !!session,
    mode: parts[1] || null,
    appid: parts[2] || parts[1] || null,
    suspended: suspended || null,
  };
}

// game-launch owns the whole handoff; it must outlive us and never inherit
// our stdio, exactly as the Kodi plugin spawns it.
function launcher(args) {
  const child = spawn(LAUNCHER, args, { detached: true, stdio: 'ignore' });
  // A missing/unexecutable game-launch raises on the child, which is an
  // unhandled 'error' event: it would take the whole server down.
  child.on('error', (err) => console.error(`game-launch ${args[0]} failed:`, err.message));
  child.unref();
}

export function launchGame(id) {
  if (id === 'bigpicture') launcher(['bigpicture']);
  else if (id === 'shadps4') launcher(['shadps4']);
  else if (id.startsWith('ps4:')) launcher(['shadps4', id.slice(4)]);
  else if (/^\d+$/.test(id)) launcher(['steam', id]);
  else throw new Error('unrecognised game id');
}

export function resumeGame() { launcher(['resume']); }
export function quitGame() { launcher(['quit']); }

// game-pids, not pgrep -f: a cmdline pattern can match a bystander whose
// arguments merely mention steamapps (an editor with a game file open, a
// shell sitting in the directory) and SIGSTOP it, and it also MISSES the
// real game under Proton, whose cmdline is an S:\ path with no "steamapps"
// in it. game-pids walks Steam's reaper/pv-adverb process tree instead -
// the same identification couchd and screen.js already use. Exit 1 means
// "no game session", and any error means we freeze nothing.
function gamePids() {
  return new Promise((resolve) => {
    execFile(path.join(BIN, 'game-pids'), (err, out) => {
      resolve(err ? [] : out.trim().split('\n').filter(Boolean).map(Number));
    });
  });
}

// The FULL console suspend, the same one the PS-hold and the screen switcher
// use: `game-launch suspend`. Doing the SIGSTOP here instead was a half
// suspend - it froze the game and set the flag but left Kodi behind the game's
// window, left the frozen client holding its pointer grab (a SIGSTOPped client
// never answers X, so its grab swallows the phone's clicks), took no pause
// frame, and spawned no steam-input-guard.
//
// Run to completion (it is synchronous, ~1-2s) rather than detached, so the
// route's answer reflects a finished suspend. The exit code says nothing about
// whether anything was frozen - it exits 0 with no game at all - so the answer
// comes from the pids seen going in, or the flag it left behind.
export async function suspendGame() {
  const pids = await gamePids();
  await new Promise((resolve) => {
    // Generous: a SIGTERM landing mid-suspend (timeout) would leave the game
    // frozen with the pad still pointed at it, so the timeout is only a
    // last-resort guard against a launcher that never returns at all.
    execFile(LAUNCHER, ['suspend'], { timeout: 45000 }, (err) => {
      if (err) console.error('game-launch suspend:', err.message);
      resolve();
    });
  });
  return pids.length > 0 || fs.existsSync(SUSPENDED);
}

// --- DualSense ---

// A joystick node under /sys/devices/virtual/ was created through /dev/uinput
// by something on this box, not plugged in by a person: `vpad` (the guard's
// synthetic Xbox pad), the fake-pad and ps-button test rigs, and the mouse
// passthrough Kodi's peripheral layer puts up. Counting those as "a
// controller is connected" is what made the phone app claim a pad while the
// DualSense was off - and the fake-pad rig deliberately calls itself
// "DualSense Wireless Controller", so a name match alone would not have
// caught it either. Where the device lives is the honest test: uinput cannot
// forge a real bus path.
const VIRTUAL_INPUT = `${path.sep}devices${path.sep}virtual${path.sep}`;

export function realJoysticks() {
  let nodes = [];
  try {
    nodes = fs.readdirSync('/dev/input').filter((f) => /^js\d+$/.test(f));
  } catch { return []; }
  const found = [];
  for (const node of nodes) {
    let where;
    try { where = fs.realpathSync(`/sys/class/input/${node}`); } catch { continue; }
    if (where.includes(VIRTUAL_INPUT)) continue;
    found.push({ node, name: readIf(`/sys/class/input/${node}/device/name`) || node });
  }
  return found;
}

export function padState() {
  // The DualSense presents two nodes (the 13-button pad and its motion
  // sensors); either is proof the pad is here, so the answer stays a boolean
  // and `name` reports the first real one for the app to show and for anyone
  // debugging this again.
  const real = realJoysticks();
  const connected = real.length > 0;
  const name = real.length ? real[0].name : null;
  let battery = null;
  let charging = false;
  const globs = fs.existsSync('/sys/class/power_supply') ? fs.readdirSync('/sys/class/power_supply') : [];
  for (const d of globs) {
    if (!/controller.*battery|^sony_controller/.test(d)) continue;
    const base = path.join('/sys/class/power_supply', d);
    const cap = readIf(path.join(base, 'capacity'));
    if (cap !== null) {
      battery = parseInt(cap, 10);
      charging = readIf(path.join(base, 'status')) === 'Charging';
      break;
    }
  }
  return { connected, battery, charging, name };
}

function bluetooth(cmd) {
  return new Promise((resolve, reject) => {
    execFile('bluetoothctl', [cmd, PAD_MAC], { timeout: 20000 }, (err, out, errOut) => {
      if (err) reject(new Error((out + errOut).trim() || err.message));
      else resolve(out.trim());
    });
  });
}

// Attribution breadcrumb: couchd logs 'pad: present -> absent
// (pad-disconnected)' identically whether Bluetooth dropped on its own or
// Donnie pressed the button in this app - and on 23 Aug the morning's
// forensics blamed the hardware for a disconnect he asked for. One file,
// newest action wins; couchd watches it, quit-trace tapes it, and anyone
// reading a pad transition correlates by the timestamp inside.
const PAD_EVENT_FILE = '/tmp/pad-user-action';
function padBreadcrumb(action) {
  try {
    fs.writeFileSync(PAD_EVENT_FILE,
      `${new Date().toISOString()} ${action} via couch-app\n`);
  } catch { /* attribution is best-effort, never blocks the action */ }
}

export const padConnect = () => { padBreadcrumb('connect'); return bluetooth('connect'); };
export const padDisconnect = () => { padBreadcrumb('disconnect'); return bluetooth('disconnect'); };

// --- TV and lights: shell out to the CLIs that already know the quirks. ---
// Both are slow (the tv connect settles, lights rediscover every call), so
// callers fire them async and the UI shows the last known state meanwhile.

function cli(bin, args, timeout = 30000) {
  return new Promise((resolve, reject) => {
    execFile(path.join(BIN, bin), args, { timeout }, (err, out, errOut) => {
      if (err) reject(new Error((errOut + out).trim() || err.message));
      else resolve(out.trim());
    });
  });
}

const TV_CMDS = new Set(['status', 'on', 'off', 'toggle', 'hdmi1', 'hdmi2', 'hdmi3', 'hdmi4']);
export function tv(cmd) {
  if (!TV_CMDS.has(cmd)) throw new Error('unrecognised tv command');
  return cli('tv', [cmd]);
}

// The TV's native Jellyfin app, launched over SSAP. Deliberately NOT in
// TV_CMDS: the /api/tv/:cmd route must never become an arbitrary app
// launcher, and SSAP only answers while the TV is awake anyway - tvcast.js
// owns the wake-first sequencing.
export const tvJellyfinApp = () => cli('tv', ['app', 'org.jellyfin.webos']);

// Whether the tv CLI has a TV to talk to at all. Its absence is a normal
// state on a fresh checkout; callers answer 503 with words, not a stack.
export const tvConfigured = () => fs.existsSync(path.join(HOME, '.config/tv-remote/tv.json'));

// --- TV / soundbar volume ---
//
// Deliberately NOT the `tv` CLI: every verb that one has is allowed to wake
// the set, and the phone reads the volume the instant the Remote tab opens.
// tools/tv-volume is the no-wake path - it only ever dials the TV, and a set
// that does not answer comes back as {off:true}, which is a state and not a
// fault. So this never rejects on a sleeping TV either; the route hands the
// shape straight to the phone.
//
// It lives in the repo (tools/), not ~/.local/bin, because it exists for this
// app. The wall-clock cost of a standby TV is ~3s (two refused socket opens),
// hence a timeout comfortably above it rather than the 30s the CLIs get.
const TV_VOLUME = path.join(ROOT, 'tools', 'tv-volume');

export function tvVolume(args) {
  return new Promise((resolve, reject) => {
    execFile(TV_VOLUME, args, { timeout: 12000 }, (err, out, errOut) => {
      let parsed = null;
      try { parsed = JSON.parse((out || '').trim()); } catch { /* not json */ }
      // A non-zero exit still prints {"error": ...}; prefer its words to
      // execFile's "Command failed".
      if (parsed && typeof parsed === 'object' && !parsed.error) { resolve(parsed); return; }
      if (err || parsed?.error) {
        reject(new Error(parsed?.error || (errOut || out || '').trim() || err.message));
        return;
      }
      reject(new Error('tv-volume printed nothing usable'));
    });
  });
}

// The one place that decides what the phone is allowed to ask for, so the
// route below stays a thin translation of the request body.
export function tvVolumeArgs({ level, action }) {
  if (level !== undefined && level !== null) {
    const n = Number(level);
    if (!Number.isFinite(n)) throw new Error('level must be a number 0-100');
    return ['set', String(Math.max(0, Math.min(100, Math.round(n))))];
  }
  if (action === 'up' || action === 'down') return [action];
  if (action === 'mute') return ['mute', 'on'];
  if (action === 'unmute') return ['mute', 'off'];
  throw new Error('level, or action up/down/mute/unmute, required');
}

export function lights(cmd, dim) {
  const args = [];
  if (cmd === 'status' || cmd === 'off' || cmd === 'warm' || cmd === 'cool') args.push(cmd);
  else if (cmd === 'on') { args.push('on'); if (dim) args.push('dim', String(dim)); }
  else if (cmd === 'dim') args.push('dim', String(Math.max(10, Math.min(100, dim | 0))));
  else throw new Error('unrecognised lights command');
  return cli('lights', args, 15000);
}

// --- couchd (the shadow daemon) ---

// couchd rewrites status.json atomically every ~3s; we re-read it on every
// request and never cache, so the phone sees the daemon's own clock. A file
// that is missing, unreadable or older than STALE means couchd is not running:
// a NORMAL state (it may be stopped at any time, stage-1 design R6/B1), so it
// answers ok:false with a reason rather than throwing.
const COUCHD_STALE_S = 60;
const ago = (s) => (s < 120 ? `${s}s` : s < 7200 ? `${Math.round(s / 60)}m` : `${Math.round(s / 3600)}h`);

export function couchdStatus() {
  const raw = readIf(COUCHD_STATUS);
  if (!raw) return { ok: false, reason: 'couchd not running' };
  let s;
  // A half-written read shouldn't happen (the writer renames into place), but
  // a truncated file must read as "not running", never as a 502.
  try { s = JSON.parse(raw); } catch { return { ok: false, reason: 'couchd not running' }; }
  const age = Math.round(Date.now() / 1000 - Number(s.t || 0));
  if (!Number.isFinite(age) || age > COUCHD_STALE_S) {
    if (!Number.isFinite(age)) return { ok: false, reason: 'couchd not running' };
    return { ok: false, reason: `couchd stale (no update for ${ago(age)})`, age };
  }
  return {
    ok: true,
    age,
    mode: s.mode ?? null,
    // Which responsibilities couchd is EXECUTING right now (owns.conf, read
    // by both stacks every tick). Empty = shadow mode: it decides and logs,
    // the old scripts act. The card shows this so the room can see, from the
    // sofa, which stack is driving before anyone starts debugging.
    owns: s.owns ?? [],
    ownsWarnings: s.owns_warnings ?? [],
    actionFailures: s.action_failures ?? 0,
    attention: !!s.attention,
    uptime: s.uptime_s ?? null,
    regions: s.regions ?? {},
    observers: s.observers ?? {},
    // last_would_do is newest-first, in the same words as /tmp/couchd.log.
    wouldDo: s.last_would_do ?? [],
    counts: s.counts ?? {},
  };
}

// --- health panel ---

function exec(bin, args, timeout = 8000) {
  // systemctl is-active exits non-zero when a unit is inactive but still
  // prints the states; keep stdout whenever there is any.
  return new Promise((resolve) => {
    execFile(bin, args, { timeout }, (err, out) => {
      const text = (out || '').trim();
      resolve(text || (err ? null : text));
    });
  });
}

function cpuTemp() {
  try {
    for (const d of fs.readdirSync('/sys/class/hwmon')) {
      const base = path.join('/sys/class/hwmon', d);
      const name = readIf(path.join(base, 'name'));
      if (name === 'k10temp' || name === 'coretemp') {
        const raw = readIf(path.join(base, 'temp1_input'));
        if (raw) return Math.round(Number(raw) / 1000);
      }
    }
  } catch {}
  return null;
}

function disk(mount) {
  try {
    const s = fs.statfsSync(mount);
    const total = s.blocks * s.bsize;
    const free = s.bavail * s.bsize;
    return { mount, total, free, usedPct: Math.round(((total - free) / total) * 100) };
  } catch { return null; }
}

const USER_SERVICES = ['couch', 'rota', 'light-watch', 'cinema-watch', 'tv-waker', 'whisper-asr', 'pad-home'];
// watchnow is a system unit, not a user one; is-active needs no sudo.
const SYSTEM_SERVICES = ['watchnow'];

// GPU telemetry regardless of vendor: nvidia-smi while the 4070 is in, the
// amdgpu sysfs files after the 9070 XT swap. Same shape either way.
function amdGpuHealth() {
  try {
    for (const card of fs.readdirSync('/sys/class/drm').filter((c) => /^card\d+$/.test(c))) {
      const dev = `/sys/class/drm/${card}/device`;
      let hw;
      try { hw = fs.readdirSync(`${dev}/hwmon`)[0]; } catch { continue; }
      if (!hw) continue;
      const rd = (p) => { try { return Number(fs.readFileSync(p, 'utf8').trim()); } catch { return null; } };
      const temp = rd(`${dev}/hwmon/${hw}/temp1_input`);
      if (temp === null) continue;
      const memUsed = rd(`${dev}/mem_info_vram_used`);
      const memTotal = rd(`${dev}/mem_info_vram_total`);
      return {
        temp: Math.round(temp / 1000),
        util: rd(`${dev}/gpu_busy_percent`) ?? 0,
        memUsed: memUsed !== null ? Math.round(memUsed / 1048576) : 0,
        memTotal: memTotal !== null ? Math.round(memTotal / 1048576) : 0,
      };
    }
  } catch { /* no amd gpu either */ }
  return null;
}

export async function health() {
  const [gpuRaw, userStates, systemStates, dockerRaw, kodiPid, steamPid] = await Promise.all([
    exec('nvidia-smi', ['--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits']),
    exec('systemctl', ['--user', 'is-active', ...USER_SERVICES]),
    exec('systemctl', ['is-active', ...SYSTEM_SERVICES]),
    exec('docker', ['ps', '--format', '{{.Names}}']),
    exec('pgrep', ['-x', 'kodi.bin']),
    exec('pgrep', ['-f', 'steam -silent|steamwebhelper']),
  ]);
  let gpu = null;
  if (gpuRaw) {
    const [temp, util, memUsed, memTotal] = gpuRaw.split(',').map((v) => Number(v.trim()));
    gpu = { temp, util, memUsed, memTotal };
  } else {
    gpu = amdGpuHealth();
  }
  const services = {};
  (userStates || '').split('\n').forEach((state, i) => { services[USER_SERVICES[i]] = state; });
  (systemStates || '').split('\n').forEach((state, i) => { services[SYSTEM_SERVICES[i]] = state; });
  services.kodi = kodiPid ? 'active' : 'down';
  services.steam = steamPid ? 'active' : 'down';
  const docker = (dockerRaw || '').split('\n').filter(Boolean);
  // Container names differ per house; COUCH_DOCKER_SERVICES overrides the defaults.
  const want_ = (process.env.COUCH_DOCKER_SERVICES || 'jellyseerr,qbittorrent,cloudflared').split(',').map((x) => x.trim()).filter(Boolean);
  for (const want of want_) {
    services[want] = docker.includes(want) ? 'active' : 'down';
  }
  return {
    cpuTemp: cpuTemp(),
    gpu,
    load: Math.round(os.loadavg()[0] * 100) / 100,
    cores: os.cpus().length,
    memUsedPct: Math.round(((os.totalmem() - os.freemem()) / os.totalmem()) * 100),
    uptime: Math.round(os.uptime()),
    disks: [disk('/'), disk('/mnt/media')].filter(Boolean),
    services,
  };
}

// The hardened restart: abort kodi.bin so the kodi-tv watchdog relaunches it
// (a clean TERM exit would NOT be restarted). Never touch kodi-tv itself,
// manual relaunches breed duplicate watchdogs.
export async function kodiRestart() {
  const pid = await exec('pgrep', ['-x', 'kodi.bin']);
  if (!pid) throw new Error('kodi.bin is not running');
  process.kill(Number(pid.split('\n')[0]), 'SIGABRT');
  return 'restarting, the watchdog brings it back in a few seconds';
}

export function parseLightsStatus(out) {
  // "<bulb-ip>  on  100%  2700K  (rssi -55)" per line, or "no bulbs answered"
  const bulbs = [];
  for (const line of out.split('\n')) {
    const m = line.match(/^([\d.]+)\s+(on|off)\s+(\d+)%\s+(.+?)\s+\(rssi/);
    if (m) bulbs.push({ ip: m[1], on: m[2] === 'on', dimming: parseInt(m[3], 10), mode: m[4] });
  }
  return bulbs;
}

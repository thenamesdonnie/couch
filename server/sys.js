// Everything outside Kodi: game sessions via game-launch, the DualSense,
// the TV, the lights. All user-level, nothing here may want sudo.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, execFile } from 'node:child_process';

const HOME = os.homedir();
const BIN = path.join(HOME, '.local/bin');
const LAUNCHER = path.join(BIN, 'game-launch');
const SESSION = '/tmp/game-session';
const SUSPENDED = '/tmp/game-suspended';
const PAD_MAC = 'AA:BB:CC:DD:EE:FF';

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

// Mirror of pad-home-watcher's suspend_game: freeze the live game processes,
// record what was frozen, then the caller hands the pad back to Kodi via
// JSON-RPC. Console-style suspend, zero CPU while frozen.
function gamePids() {
  return new Promise((resolve) => {
    execFile('pgrep', ['-f', 'steamapps/common|Shadps4-sdl|mount_Shadps'], (err, out) => {
      resolve(err ? [] : out.trim().split('\n').filter(Boolean).map(Number));
    });
  });
}

export async function suspendGame() {
  const pids = await gamePids();
  if (!pids.length) return false;
  const parts = (readIf(SESSION) || '').split(/\s+/);
  const appid = parts[2] || parts[1] || 'game';
  for (const pid of pids) {
    try { process.kill(pid, 'SIGSTOP'); } catch { /* already gone */ }
  }
  fs.writeFileSync(SUSPENDED, appid);
  return true;
}

// --- DualSense ---

export function padState() {
  let connected = false;
  try { connected = fs.readdirSync('/dev/input').some((f) => f.startsWith('js')); } catch {}
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
  return { connected, battery, charging };
}

function bluetooth(cmd) {
  return new Promise((resolve, reject) => {
    execFile('bluetoothctl', [cmd, PAD_MAC], { timeout: 20000 }, (err, out, errOut) => {
      if (err) reject(new Error((out + errOut).trim() || err.message));
      else resolve(out.trim());
    });
  });
}

export const padConnect = () => bluetooth('connect');
export const padDisconnect = () => bluetooth('disconnect');

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

export function lights(cmd, dim) {
  const args = [];
  if (cmd === 'status' || cmd === 'off' || cmd === 'warm' || cmd === 'cool') args.push(cmd);
  else if (cmd === 'on') { args.push('on'); if (dim) args.push('dim', String(dim)); }
  else if (cmd === 'dim') args.push('dim', String(Math.max(10, Math.min(100, dim | 0))));
  else throw new Error('unrecognised lights command');
  return cli('lights', args, 15000);
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
  }
  const services = {};
  (userStates || '').split('\n').forEach((state, i) => { services[USER_SERVICES[i]] = state; });
  (systemStates || '').split('\n').forEach((state, i) => { services[SYSTEM_SERVICES[i]] = state; });
  services.kodi = kodiPid ? 'active' : 'down';
  services.steam = steamPid ? 'active' : 'down';
  const docker = (dockerRaw || '').split('\n').filter(Boolean);
  for (const want of ['jellyseerr', 'qbittorrent', 'cloudflared-donflix']) {
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

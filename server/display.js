// The display's account of itself. This is deliberately read-only: changing a
// mode while a game owns the screen can leave the TV black, but seeing the
// negotiated mode is useful when a hotplug has dropped 4K120.
import { execFile } from 'node:child_process';
import express from 'express';

function xrandr() {
  return new Promise((resolve, reject) => {
    execFile('xrandr', ['--verbose'], {
      env: { ...process.env, DISPLAY: ':0' }, timeout: 8000, maxBuffer: 1024 * 1024,
    }, (err, out, errOut) => {
      if (err) reject(new Error(String(errOut || err.message).trim()));
      else resolve(out);
    });
  });
}

let seams = { run: xrandr };
export function _setDisplaySeams({ run } = {}) {
  seams = { run: run ?? xrandr };
}

function monitorName(lines) {
  const named = lines.find((line) => line.match(/^\s*MonitorName:\s*/i));
  if (named) return named.replace(/^\s*MonitorName:\s*["']?/, '').replace(/["']?\s*$/, '') || null;
  const start = lines.findIndex((line) => /^\s*EDID:\s*$/i.test(line));
  if (start === -1) return null;
  const hex = [];
  for (let i = start + 1; i < lines.length && /^\s*[0-9a-f]{32}\s*$/i.test(lines[i]); i += 1) {
    hex.push(lines[i].trim());
  }
  const edid = Buffer.from(hex.join(''), 'hex');
  // The four descriptor slots live at fixed offsets. Walking the whole blob
  // in 18-byte steps happens to cross them, but it also reads the 54 bytes of
  // header and timing data before them as if they were descriptors, where a
  // 00 00 00 fc run means something else entirely.
  for (const i of [54, 72, 90, 108]) {
    if (i + 18 > edid.length) break;
    if (edid[i] === 0 && edid[i + 1] === 0 && edid[i + 2] === 0 && edid[i + 3] === 0xfc) {
      return edid.subarray(i + 5, i + 18).toString('ascii').replace(/[\n\0]/g, '').trim() || null;
    }
  }
  return null;
}

function outputBlocks(text) {
  const starts = [...text.matchAll(/^(\S+)\s+(connected|disconnected)\b.*$/gm)];
  return starts.map((m, i) => ({
    name: m[1], connected: m[2] === 'connected',
    text: text.slice(m.index, starts[i + 1]?.index),
  }));
}

function sizeFromHeader(header) {
  const m = header.match(/\s(\d+)mm\s+x\s+(\d+)mm(?:\s|$)/);
  return m ? { width: Number(m[1]), height: Number(m[2]) } : null;
}

function geometryFromHeader(header) {
  const m = header.match(/\s(\d+)x(\d+)\+[-\d]+\+[-\d]+/);
  return m ? { width: Number(m[1]), height: Number(m[2]) } : null;
}

function rate(token) {
  const value = Number(token.replace(/[+*]/g, ''));
  return Number.isFinite(value) ? value : null;
}

function modeDimensions(name) {
  const m = name.match(/^(\d+)x(\d+)/);
  return m ? { width: Number(m[1]), height: Number(m[2]) } : {};
}

// Parse the entire connector block. In particular, do not stop at the EDID
// mode table: user modelines can appear later in this same block after a
// hotplug, and that is often where the active 4K120 mode is named.
export function parseXrandr(text) {
  if (typeof text !== 'string' || !text.trim()) throw new Error('xrandr returned no display data');
  const blocks = outputBlocks(text);
  const block = blocks.find((item) => item.connected) ?? blocks[0];
  if (!block) throw new Error('xrandr returned no outputs');
  const lines = block.text.split('\n');
  const modes = new Map();
  let current = null;

  for (let i = 1; i < lines.length; i += 1) {
    const line = lines[i];
    // Normal xrandr mode rows, including custom rows appended after the EDID
    // rows. A refresh token is the discriminator from verbose timing details.
    const row = line.match(/^\s+(\S+)\s+((?:\d+(?:\.\d+)?[+*]?\s*)+)$/);
    if (row) {
      const name = row[1];
      // --verbose prints the connector's PROPERTIES in this same block, and
      // "Timestamp:  164250451" has exactly the shape of a mode row. Two
      // discriminators, both cheap: a property name ends in a colon, and no
      // display refreshes at 164 million hertz. Without these the panel listed
      // Brightness, CRTC and vrr_capable as modes you could select.
      if (name.endsWith(':')) continue;
      const rates = row[2].trim().split(/\s+/).map(rate)
        .filter((v) => v !== null && v >= 10 && v <= 1000);
      if (!rates.length) continue;
      const found = modes.get(name) ?? {
        name, ...modeDimensions(name), refreshRates: [], custom: !/^\d+x\d+$/.test(name),
      };
      found.refreshRates = [...new Set([...found.refreshRates, ...rates])].sort((a, b) => b - a);
      modes.set(name, found);
      const active = row[2].trim().split(/\s+/).find((v) => v.includes('*'));
      if (active) current = { name, refresh: rate(active), custom: found.custom };
      continue;
    }
    // --verbose names a modeline separately from its timing. Keep looking
    // through the whole block, because custom modelines are commonly here.
    const verbose = line.match(/^\s+(\S+)\s+\(0x[0-9a-f]+\)/i);
    if (!verbose) continue;
    const name = verbose[1];
    const timing = lines.slice(i + 1, i + 8).join(' ');
    const timingRate = timing.match(/clock\s+([\d.]+)Hz/i);
    const found = modes.get(name) ?? { name, ...modeDimensions(name), refreshRates: [], custom: true };
    found.custom = true;
    const h = timing.match(/h:\s+width\s+(\d+)/i);
    const v = timing.match(/v:\s+height\s+(\d+)/i);
    if (h && v) { found.width = Number(h[1]); found.height = Number(v[1]); }
    if (timingRate) found.refreshRates = [...new Set([...found.refreshRates, Number(timingRate[1])])].sort((a, b) => b - a);
    if (/\*current\b/.test(line)) current = {
      name,
      refresh: timingRate ? Number(timingRate[1]) : null,
      custom: found.custom,
    };
    modes.set(name, found);
  }

  const header = lines[0] || '';
  const geometry = geometryFromHeader(header);
  if (current && geometry) current = { ...geometry, ...current };
  const allModes = [...modes.values()].map((mode) => ({
    ...mode,
    refreshRates: [...mode.refreshRates].sort((a, b) => b - a),
  }));
  const has4k120 = allModes.some((mode) => {
    const is4k = (mode.width === 3840 || mode.width === 4096) && mode.height === 2160 || /^4k/i.test(mode.name);
    return is4k && mode.refreshRates.some((v) => v >= 119 && v <= 121);
  });
  return {
    ok: true,
    output: block.name,
    monitor: monitorName(lines),
    connected: block.connected,
    physicalSize: sizeFromHeader(header),
    current,
    modes: allModes,
    has4k120,
  };
}

export async function status() {
  try {
    return parseXrandr(await seams.run());
  } catch (err) {
    return { ok: false, reason: String(err.message || err) || 'cannot read xrandr' };
  }
}

export const routes = express.Router();
routes.get('/', async (req, res) => {
  res.set('cache-control', 'no-store');
  res.json(await status());
});

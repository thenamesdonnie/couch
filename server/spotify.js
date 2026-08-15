// Spotify Connect transport control, for the spotifyd receiver that makes
// this box the "Couch" speaker (systemd user service; docs in the memory
// note and ~/.config/spotifyd/spotifyd.conf).
//
// HOW IT TALKS TO SPOTIFYD: MPRIS over the session DBus, via busctl, so
// there is no dbus client dependency. spotifyd only registers its MPRIS
// player name (org.mpris.MediaPlayer2.spotifyd.instance<pid>) while a phone
// has an active session with it; the name's absence therefore IS the
// "nothing to control" signal, not an error. Its rs.spotifyd.instance<pid>
// name exists from startup but only carries volume/transfer methods - no
// use here.
//
// SAFETY: this backs a bar on the on-TV switcher, the room's only route out
// of a frozen game. Every call is bounded by a short timeout and the status
// call never throws: a hung dbus daemon must cost the Spotify bar, never
// the switcher.
import { execFile } from 'node:child_process';

const MPRIS_PREFIX = 'org.mpris.MediaPlayer2.spotifyd';
const MPRIS_PATH = '/org/mpris/MediaPlayer2';
const PLAYER_IFACE = 'org.mpris.MediaPlayer2.Player';

const COMMANDS = {
  playpause: 'PlayPause',
  play: 'Play',
  pause: 'Pause',
  next: 'Next',
  previous: 'Previous',
};

function busctl(args) {
  return new Promise((resolve, reject) => {
    execFile('busctl', ['--user', '--json=short', ...args], { timeout: 3000 },
      (err, stdout) => {
        if (err) return reject(err);
        try { resolve(stdout.trim() ? JSON.parse(stdout) : null); }
        catch (e) { reject(e); }
      });
  });
}

async function playerName() {
  const res = await busctl(['call', 'org.freedesktop.DBus',
    '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'ListNames']);
  const names = res?.data?.[0] || [];
  return names.find((n) => n.startsWith(MPRIS_PREFIX)) || null;
}

function getProp(name, prop) {
  return busctl(['call', name, MPRIS_PATH,
    'org.freedesktop.DBus.Properties', 'Get', 'ss', PLAYER_IFACE, prop]);
}

// {active:false} when no phone session; otherwise playing + what's on.
export async function status() {
  let name = null;
  try { name = await playerName(); } catch { return { active: false }; }
  if (!name) return { active: false };
  try {
    const [st, md] = await Promise.all([
      getProp(name, 'PlaybackStatus'),
      getProp(name, 'Metadata'),
    ]);
    const meta = md?.data?.[0]?.data || {};
    return {
      active: true,
      playing: st?.data?.[0]?.data === 'Playing',
      track: meta['xesam:title']?.data || '',
      artist: (meta['xesam:artist']?.data || []).join(', '),
    };
  } catch {
    // The name existed a moment ago; a raced session teardown or a slow
    // property read still means "Spotify is here", just with nothing to say.
    return { active: true, playing: false, track: '', artist: '' };
  }
}

// Fires a transport command and answers with a FRESH status, so the caller
// can redraw its play/pause label without a second round trip. The pause
// before re-reading is because spotifyd applies the command asynchronously;
// 250ms measured comfortably on this box.
export async function command(cmd) {
  const method = COMMANDS[cmd];
  if (!method) throw new Error(`unknown spotify command: ${cmd}`);
  const name = await playerName();
  if (!name) throw new Error('no active Spotify session');
  await busctl(['call', name, MPRIS_PATH, PLAYER_IFACE, method]);
  await new Promise((r) => setTimeout(r, 250));
  return status();
}

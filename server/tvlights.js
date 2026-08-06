// Cinema lights for a playback running on the TV's own Jellyfin app.
//
// WHY THIS EXISTS: ~/.local/bin/light-watch already dims the WiZ bulbs when a
// film plays, but it listens to KODI. A TV-app playback never touches Kodi, so
// without this the lights would stay up for exactly the films that matter most
// (the 4K HDR ones). tvcast's session monitor calls set('dim'/'restore') as the
// TV session plays, pauses and stops.
//
// HOW IT TALKS TO THE BULBS: through the `lights` CLI (server/sys.js -> lights),
// the same binary the phone's Lights card drives. NOTE, and this cost real
// reading: light-watch does NOT use that CLI - it speaks WiZ UDP itself, so it
// can save and restore each bulb individually, ramp over 1.8s and dim to
// 2200K. The CLI can only address every bulb that answers, has no ramp and its
// warmest preset is 2700K. So the two paths look CLOSE, not identical:
//   * dim level 10 (light-watch's DIM_LEVEL) - identical.
//   * warm-and-low look - 2700K here vs 2200K there, and only applied when the
//     bulbs' current colour is one this CLI can put back (see restorableTemp).
//     If they are on a scene or an arbitrary temperature we change brightness
//     ONLY, so the restore is exact rather than approximately warm.
//   * bulbs that are OFF when a film starts are left alone by light-watch. The
//     CLI cannot address one bulb, so the rule here is coarser: if NO bulb is
//     on we do nothing at all (a dark room stays dark); if some are on, the
//     brightness command will also wake any that were off. Documented, and the
//     restore puts the room back to the brightest level it was at.
//
// SAFETY: nothing in here may ever fail a playback. Every CLI call is wrapped;
// a missing binary, a bulb that does not answer or a parse miss logs and
// returns. Commands are serialised on one promise chain so a dim and a restore
// arriving together can never interleave two `lights` processes.
import * as sys from './sys.js';

// light-watch's DIM_LEVEL. WiZ's own floor is 10, so this is as low as it goes.
export const DIM_LEVEL = 10;

// The colour presets the `lights` CLI can set, by the mode string `lights
// status` prints for them. Anything else (a scene, 4000K, rgb) is not
// reproducible, so we refuse to change colour at all in that case.
const CLI_TEMPS = { '2700K': 'warm', '5000K': 'cool' };

// Can we put this snapshot's colour back afterwards? Only if every lit bulb
// agrees on one temperature the CLI knows. null means "leave colour alone".
export function restorableTemp(bulbs) {
  const modes = new Set((bulbs || []).filter((b) => b.on).map((b) => b.mode));
  if (modes.size !== 1) return null;
  return CLI_TEMPS[[...modes][0]] || null;
}

// What brightness to come back to. Bulbs can disagree; the brightest wins,
// because coming back too bright is a shrug and coming back too dark is
// someone hunting for a light switch in the dark.
export function restoreLevel(bulbs) {
  const levels = (bulbs || []).filter((b) => b.on).map((b) => b.dimming || 0);
  return levels.length ? Math.max(...levels, DIM_LEVEL) : 100;
}

const DEFAULTS = {
  run: (cmd, dim) => sys.lights(cmd, dim),
  parse: (out) => sys.parseLightsStatus(out),
  log: (...a) => console.error('[tvlights]', ...a),
};

export function createTvLights(overrides = {}) {
  const d = { ...DEFAULTS, ...overrides };

  let dimmed = false;
  let saved = null; // the snapshot taken just before dimming
  let back = null; // the CLI colour command that restores it, or null
  let desired = 'restore';
  let chain = Promise.resolve();

  // One CLI call. Never throws: the caller decides what a failure means, and
  // no failure here may reach a playback.
  async function call(cmd, arg) {
    try {
      await d.run(cmd, arg);
      return true;
    } catch (e) {
      d.log(`lights ${cmd} failed:`, e.message);
      return false;
    }
  }

  async function dim() {
    let bulbs;
    try {
      bulbs = d.parse(await d.run('status'));
    } catch (e) {
      d.log('cannot read the bulbs, leaving them alone:', e.message);
      return;
    }
    const lit = (bulbs || []).filter((b) => b.on);
    if (!lit.length) {
      // No bulb answered, or the room is already dark. Either way: hands off.
      d.log('no bulb is lit, leaving the room as it is');
      return;
    }
    const temp = restorableTemp(lit);
    if (!temp) d.log('bulbs are on a colour this CLI cannot restore, dimming brightness only');
    let acted = false;
    if (temp) acted = (await call('warm')) || acted;
    acted = (await call('dim', DIM_LEVEL)) || acted;
    if (!acted) return; // nothing landed: we are not holding a dim, so never "restore"
    saved = lit;
    back = temp;
    dimmed = true;
  }

  async function restore() {
    const was = saved;
    const temp = back;
    // Cleared FIRST: a restore that half fails must not leave us believing we
    // still own a dim, or every later tick would fire the CLI again.
    saved = null;
    back = null;
    dimmed = false;
    const level = restoreLevel(was);
    if (temp) await call(temp);
    await call('on', level);
  }

  // Ask for a state. Returns the promise for the settled command so tests (and
  // shutdown paths) can await it; callers in the monitor deliberately do not.
  function set(target) {
    desired = target === 'dim' ? 'dim' : 'restore';
    const step = async () => {
      if (desired === 'dim' && !dimmed) await dim();
      else if (desired === 'restore' && dimmed) await restore();
    };
    chain = chain.then(step, step).catch((e) => d.log('unexpected:', e.message));
    return chain;
  }

  return {
    set,
    state: () => ({ dimmed, desired, level: dimmed ? DIM_LEVEL : null }),
    settled: () => chain,
  };
}

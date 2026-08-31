// Bloodborne cheat toggles for the Games tab.
//
// All the real work lives in ~/couch/tools/bb-cheat (see its docstring for the
// shadPS4 patch mechanism). This is a thin, well-behaved wrapper: it never
// shells out through a shell, it always uses an absolute path, and it turns a
// tool failure into a message the phone can actually show.
//
// ABSOLUTE PATH IS NOT OPTIONAL. The server runs under systemd, whose PATH has
// no ~/.local/bin and no ~/couch/tools, so a bare command name works from a
// terminal and silently fails here. That trap has cost this project days
// before now (see docs: the launch PATH trap).
import path from 'node:path';
import os from 'node:os';
import { execFile } from 'node:child_process';

const HOME = os.homedir();
const TOOL = path.join(HOME, 'couch/tools/bb-cheat');

function run(args) {
  return new Promise((resolve, reject) => {
    execFile(TOOL, args, { timeout: 10000 }, (err, stdout, stderr) => {
      if (err) {
        // bb-cheat writes its reasons to stderr and they are written for a
        // human, so pass them straight through rather than inventing one.
        const msg = (stderr || err.message || '').trim();
        reject(new Error(msg.replace(/^bb-cheat:\s*/, '') || 'bb-cheat failed'));
        return;
      }
      resolve(stdout);
    });
  });
}

export async function state() {
  return JSON.parse(await run(['json']));
}

// A toggle from the phone means both halves: change it in the running game if
// there is one, and change what the next launch will do. Doing only the live
// half would silently revert on the next launch; doing only the boot half
// would look like the switch did nothing.
export async function setCheat(name, on) {
  if (!name) throw new Error('cheat name required');
  const notes = [];

  await run([on ? 'on' : 'off', name]);
  notes.push(on ? 'armed for next launch' : 'disarmed for next launch');

  const { running } = await state();
  if (running) {
    try {
      await run(['live', on ? 'on' : 'off', name]);
      notes.push('applied to the running game');
    } catch (e) {
      // The boot half already succeeded, so this is partial success, not
      // failure. Say so precisely: the usual cause is ptrace_scope and the
      // user needs to know a relaunch would still work.
      return { ok: true, live: false, note: `${notes[0]}, but not to the running game: ${e.message}` };
    }
  }
  return { ok: true, live: running, note: notes.join(', ') };
}

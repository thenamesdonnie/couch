// Where Kodi keeps its profile - which stopped being one answer on 8 Aug 2026.
//
// Under apt-Kodi it is ~/.kodi. Under the Kodi 21 Flatpak it is
// ~/.var/app/tv.kodi.Kodi/data, because the Flathub build patches kodi.sh to
// `export KODI_DATA=${XDG_DATA_HOME}` - so it is neither ~/.kodi nor
// ~/.var/app/tv.kodi.Kodi/.kodi, which are the two guesses a reasonable person
// makes first.
//
// Both builds stay installed while apt-Kodi is the rollback, so the question
// is not which one exists - both do - but which one kodi-tv last launched.
// kodi-tv records that in data/kodi-flavour-active; data/kodi-flavour is the
// choice for the next launch. An absent record reads as 'apt', which is
// correct for a box that has been running apt-Kodi all along and is what keeps
// this module inert until the switch is thrown.
//
// This is the Node twin of couchd/kodiprofile.py. tools/test_kodiprofile.py
// reads both files and fails if they disagree.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const FLATPAK_APP_ID = 'tv.kodi.Kodi';

export const FLAVOURS = {
  apt: '.kodi',
  flatpak: path.join('.var', 'app', FLATPAK_APP_ID, 'data'),
};

export const DEFAULT_FLAVOUR = 'apt';

const FLAVOUR_FILE = path.join(os.homedir(), 'couch', 'data', 'kodi-flavour');
const ACTIVE_FILE = path.join(os.homedir(), 'couch', 'data', 'kodi-flavour-active');

function read(file) {
  try {
    return fs.readFileSync(file, 'utf8').trim();
  } catch {
    return '';
  }
}

// Read on every call rather than cached at import: the server outlives a
// flavour flip, and a stale answer here means reading the wrong Kodi's
// jellyfin credentials, which fails in a way that looks like Jellyfin being
// down. The cost is two stat()s on a path that is already in page cache.
// The CHOICE is deliberately not a fallback for the RECORD. `kodi21-migrate
// switch` writes the choice, and until Kodi is relaunched the running Kodi is
// still the old one - reading the choice as the record points this server at
// a profile that does not exist yet, which surfaces as "Jellyfin credentials
// unavailable" and reads like Jellyfin being down. An intention is not a fact.
export function flavour({ active = true } = {}) {
  const word = read(active ? ACTIVE_FILE : FLAVOUR_FILE);
  // An unrecognised word is treated as absent, never trusted: a typo must
  // not point the server at a directory that does not exist.
  return Object.prototype.hasOwnProperty.call(FLAVOURS, word)
    ? word : DEFAULT_FLAVOUR;
}

export function profileDir(name = flavour()) {
  return path.join(os.homedir(), FLAVOURS[name]);
}

export function userdata(name) {
  return path.join(profileDir(name), 'userdata');
}

export function addonData(addonId, name) {
  return path.join(userdata(name), 'addon_data', addonId);
}

export function addonsDir(name) {
  return path.join(profileDir(name), 'addons');
}

export function logPath(name) {
  return path.join(profileDir(name), 'temp', 'kodi.log');
}

// Every credential and every machine-specific address lives in the environment,
// never in source. This is the only file that reads it.
//
// systemd supplies the values with EnvironmentFile=%h/couch/.env. When the
// server is started by hand the same file is loaded here, so both paths see
// identical config; loadEnvFile never overwrites a variable that is already
// set, so systemd's copy always wins.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
try { process.loadEnvFile(path.join(ROOT, '.env')); } catch { /* systemd already supplied it */ }

const e = process.env;

// Secrets deliberately have no default: a missing one must fail loudly at the
// call site rather than fall back to something baked into the repo.
export function secret(name) {
  const v = e[name];
  if (!v) throw new Error(`${name} is not set (see .env.example)`);
  return v;
}

export const PORT = Number(e.COUCH_PORT) || 8790;

// The address the box is reachable on from the phone, used to build the links
// in the House view. Only a default so a fresh checkout starts at all.
export const LAN_HOST = e.COUCH_LAN_HOST || '127.0.0.1';

export const KODI_URL = e.KODI_URL || 'http://localhost:8090';
export const KODI_USER = e.KODI_USER || 'kodi';
export const KODI_EVENT_HOST = e.KODI_EVENT_HOST || '127.0.0.1';
export const KODI_EVENT_PORT = Number(e.KODI_EVENT_PORT) || 9090;

export const JELLYFIN_URL = e.JELLYFIN_URL || 'http://localhost:8096';

export const JELLYSEERR_URL = e.JELLYSEERR_URL || 'http://localhost:5055';
export const JELLYSEERR_SETTINGS = e.JELLYSEERR_SETTINGS || '/opt/stacks/jellyseerr/config/settings.json';

export const SONARR_URL = e.SONARR_URL || 'http://127.0.0.1:8989';
export const SONARR_CONFIG = e.SONARR_CONFIG || '/var/lib/sonarr/config.xml';

export const RADARR_URL = e.RADARR_URL || 'http://127.0.0.1:7878';
export const RADARR_CONFIG = e.RADARR_CONFIG || '/var/lib/radarr/config.xml';

// qBittorrent runs inside the gluetun container, so it is reached at the
// published LAN address rather than on localhost.
export const QBITTORRENT_URL = e.QBITTORRENT_URL || `http://${LAN_HOST}:8080`;

// The server-side kill switch for HDR auto-routing: create this file and a
// plain click plays everything in Kodi again, no restart, no Kodi UI needed
// (`touch ~/couch/data/tv-autoroute-off`). The Kodi addon has its own toggle
// as well; either one being off is enough to stop it.
export const AUTOROUTE_OFF = e.COUCH_AUTOROUTE_OFF || path.join(ROOT, 'data', 'tv-autoroute-off');

// couchd's status file, rewritten atomically every few seconds. Reading it is
// the only contact this server has with the shadow daemon; its absence is a
// normal state, never an error.
export const COUCHD_STATUS = e.COUCHD_STATUS || path.join(ROOT, 'shadow', 'status.json');

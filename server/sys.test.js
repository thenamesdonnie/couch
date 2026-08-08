// The two things the phone app kept getting wrong about the console's edges.
//
// 1. "a controller is connected" counted ANY /dev/input/js* node. This box
//    manufactures those: `vpad` (the guard's synthetic Xbox pad), the
//    fake-pad and ps-button rigs, and a "Mouse passthrough (absolute)" that
//    Kodi's peripheral layer puts up and leaves there. With the DualSense
//    switched off the app still said connected, with a null battery - which
//    is what Donnie reported on 8 Aug. Caught live: the only js node on the
//    box at the time was the mouse passthrough, and /api/pad said true.
//
//    The discriminator is WHERE the device lives, not what it calls itself:
//    uinput devices sit under /sys/devices/virtual/ and cannot forge a real
//    bus path, whereas the fake-pad rig deliberately names itself "DualSense
//    Wireless Controller" - so a name match would have been fooled by the one
//    device most likely to be up during testing.
//
// 2. the Downloads view listed seeding torrents, because it asked
//    qBittorrent for `filter=active` and active means "moving bytes" in
//    either direction. Measured on the box: active = 2 torrents, both
//    "uploading 100%"; downloading = 0.
//
// Both are pure functions over injected inputs here - no /sys, no qBittorrent.
// Run: npm test (node --test), from server/.
import test from 'node:test';
import assert from 'node:assert/strict';

// --- 1. the controller ------------------------------------------------------
// The rule under test, expressed the way sys.js implements it: a joystick
// counts when its resolved sysfs path is not under /devices/virtual/.
const VIRTUAL_INPUT = '/devices/virtual/';
const isReal = (sysfsPath) => !sysfsPath.includes(VIRTUAL_INPUT);

// Real paths taken from this box.
const DUALSENSE_BT =
  '/sys/devices/pci0000:00/0000:00:08.1/0000:0d:00.3/usb1/1-4/1-4:1.0/bluetooth/hci0/hci0:11/0005:054C:0CE6.0009/input/input42/js0';
const MOUSE_PASSTHROUGH = '/sys/devices/virtual/input/input61/js0';
const VPAD = '/sys/devices/virtual/input/input70/js1';
const FAKE_DUALSENSE = '/sys/devices/virtual/input/input71/js2';

test('a real DualSense counts', () => {
  assert.equal(isReal(DUALSENSE_BT), true);
});

test('the mouse passthrough does not - this is the reported bug', () => {
  assert.equal(isReal(MOUSE_PASSTHROUGH), false);
});

test('vpad does not, however convincing it is to Steam', () => {
  assert.equal(isReal(VPAD), false);
});

test('nor does the fake-pad rig, which shares the real pad\'s NAME', () => {
  // The case a name match would have got wrong, and the one most likely to
  // be up while somebody is testing.
  assert.equal(isReal(FAKE_DUALSENSE), false);
});

test('no pad and only virtual devices means not connected', () => {
  const nodes = [MOUSE_PASSTHROUGH, VPAD].filter(isReal);
  assert.equal(nodes.length, 0);
});

test('the real pad is still found alongside the virtual ones', () => {
  const nodes = [MOUSE_PASSTHROUGH, DUALSENSE_BT, VPAD].filter(isReal);
  assert.deepEqual(nodes, [DUALSENSE_BT]);
});

// --- 2. the downloads -------------------------------------------------------
const UPLOAD_STATE = /UP$|^uploading$/;
const isDownload = (t) => !UPLOAD_STATE.test(t.state) && t.progress < 1;

// Real states seen on this box's qBittorrent.
const SEEDING = [
  { state: 'uploading', progress: 1 },
  { state: 'stalledUP', progress: 1 },
  { state: 'stoppedUP', progress: 1 },
  { state: 'queuedUP', progress: 1 },
  { state: 'forcedUP', progress: 1 },
];

test('nothing that is uploading reaches the Downloads view', () => {
  assert.deepEqual(SEEDING.filter(isDownload), []);
});

test('a real download does', () => {
  const t = { state: 'downloading', progress: 0.42 };
  assert.equal(isDownload(t), true);
});

test('so do the stalled and queued ones - still downloads, just not moving', () => {
  assert.equal(isDownload({ state: 'stalledDL', progress: 0.1 }), true);
  assert.equal(isDownload({ state: 'queuedDL', progress: 0 }), true);
  assert.equal(isDownload({ state: 'metaDL', progress: 0 }), true);
});

test('a complete torrent is never a download, whatever its state says', () => {
  // The belt to the filter's braces: 100% means finished, and the view is
  // about things still arriving.
  assert.equal(isDownload({ state: 'downloading', progress: 1 }), false);
  assert.equal(isDownload({ state: 'checkingUP', progress: 1 }), false);
});

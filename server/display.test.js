// display.js is tested entirely from xrandr fixture text. No test starts an X
// client or asks the living-room display for a mode.
import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import { parseXrandr, status, routes, _setDisplaySeams } from './display.js';

// The EDID blob is a real 128-byte one: uniform 32-char lines the way
// xrandr --verbose actually prints them, with the 0xfc monitor-name
// descriptor at its spec offset of byte 54, 0x0a terminated and space
// padded to 13 bytes. The first version of this fixture had a ragged
// 40-char line, which the reader correctly refused - and that looked like
// a parser bug rather than a bad fixture.
const WITH_4K120 = `Screen 0: minimum 8 x 8, current 3840 x 2160, maximum 32767 x 32767
HDMI-0 connected primary 3840x2160+0+0 (normal left inverted right x axis y axis) 1210mm x 680mm
	EDID:
		00ffffffffffff0010ac123400000000
		00000000000000000000000000000000
		00000000000000000000000000000000
		000000000000000000fc0043696e656d
		612054560a2020200000000000000000
		00000000000000000000000000000000
		00000000000000000000000000000000
		00000000000000000000000000000000
	3840x2160     60.00 +
	1920x1080     60.00
	4k120         120.00*
	4k120 (0x1f2) 1188.000MHz +HSync +VSync
		h: width 3840 start 4016 end 4104 total 4400 skew 0 clock 270.00KHz
		v: height 2160 start 2168 end 2178 total 2250 clock 120.00Hz
DP-0 disconnected (normal left inverted right x axis y axis)
`;

const WITHOUT_4K120 = WITH_4K120
  .replace(/\n\t4k120[^\n]*(?:\n\t\th:[^\n]*)?(?:\n\t\tv:[^\n]*)?/g, '')
  .replace('3840x2160+0+0', '1920x1080+0+0')
  .replace('\t1920x1080     60.00', '\t1920x1080     60.00*');

test('reads a custom 4K120 modeline appended below EDID modes', () => {
  const out = parseXrandr(WITH_4K120);
  assert.equal(out.output, 'HDMI-0');
  assert.equal(out.monitor, 'Cinema TV');
  assert.equal(out.connected, true);
  assert.deepEqual(out.physicalSize, { width: 1210, height: 680 });
  assert.deepEqual(out.current, { width: 3840, height: 2160, name: '4k120', refresh: 120, custom: true });
  assert.equal(out.has4k120, true);
  assert.deepEqual(out.modes.find((m) => m.name === '4k120').refreshRates, [120]);
});

test('reports when the post-hotplug mode list has lost custom 4K120', () => {
  const out = parseXrandr(WITHOUT_4K120);
  assert.equal(out.has4k120, false);
  assert.equal(out.current.name, '1920x1080');
});

test('xrandr being absent is a calm status answer', async () => {
  _setDisplaySeams({ run: async () => { throw new Error('spawn xrandr ENOENT'); } });
  try {
    assert.deepEqual(await status(), { ok: false, reason: 'spawn xrandr ENOENT' });
  } finally { _setDisplaySeams(); }
});

test('rubbish xrandr output is a calm status answer', async () => {
  _setDisplaySeams({ run: async () => 'this is not xrandr' });
  try {
    const out = await status();
    assert.equal(out.ok, false);
    assert.match(out.reason, /no outputs/);
  } finally { _setDisplaySeams(); }
});

test('a disconnected output remains readable', () => {
  const out = parseXrandr('HDMI-0 disconnected (normal left inverted right x axis y axis)\n');
  assert.equal(out.ok, true);
  assert.equal(out.output, 'HDMI-0');
  assert.equal(out.connected, false);
  assert.equal(out.current, null);
  assert.equal(out.has4k120, false);
});

test('the route keeps display read failures at HTTP 200', async () => {
  _setDisplaySeams({ run: async () => { throw new Error('cannot open display'); } });
  const app = express();
  app.use('/api/display', routes);
  const server = app.listen(0);
  await new Promise((resolve) => server.once('listening', resolve));
  try {
    const res = await fetch(`http://127.0.0.1:${server.address().port}/api/display`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { ok: false, reason: 'cannot open display' });
  } finally {
    await new Promise((resolve) => server.close(resolve));
    _setDisplaySeams();
  }
});

// --verbose prints connector PROPERTIES in the same block as the modes, and
// they have the same shape as a mode row. Live output listed nine of them as
// selectable modes, including "Timestamp:" at 164250451 Hz.
const VERBOSE_PROPS = `Screen 0: minimum 8 x 8, current 3840 x 2160, maximum 32767 x 32767
DisplayPort-2 connected primary 3840x2160+0+0 (normal left inverted right x axis y axis) 1600mm x 900mm
	Identifier: 0x1f2
	Timestamp:  164250451
	Brightness: 1.0
	CRTC:       0
	CRTCs:      0 1 2 3
	vrr_capable: 1
	non-desktop: 0
	3840x2160     60.00 +
	4k120         120.00*
`;

test('connector properties are not offered as display modes', () => {
  const out = parseXrandr(VERBOSE_PROPS);
  const names = out.modes.map((m) => m.name);
  for (const junk of ['Timestamp:', 'Brightness:', 'CRTC:', 'CRTCs:',
                      'vrr_capable:', 'non-desktop:', 'Identifier:']) {
    assert.equal(names.includes(junk), false, `${junk} was listed as a mode`);
  }
  assert.equal(out.current.name, '4k120');
  // Deliberately NOT asserting the exact mode list here. display.js runs
  // xrandr --verbose, whose mode format differs from the compact table this
  // fixture imitates; pinning the list would be pinning the fixture rather
  // than the behaviour. The property under test is that a connector PROPERTY
  // never becomes a selectable mode, and that is asserted above.
});

test('no mode claims an impossible refresh rate', () => {
  const out = parseXrandr(VERBOSE_PROPS);
  for (const mode of out.modes) {
    for (const r of mode.refreshRates) {
      assert.ok(r >= 10 && r <= 1000, `${mode.name} claims ${r} Hz`);
    }
  }
});

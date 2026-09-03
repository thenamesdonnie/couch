/*
 * roundtrip_test.mjs <dir-of-fxrs> - what does FXR.read -> toArrayBuffer cost?
 *
 * Evidence for why tools/ds3-fog-soften patches bytes instead of re-serialising.
 * Measured 3 Sep 2026 on all 136 m32 FXRs: 0 of 136 come back byte-identical,
 * though every one comes back the same LENGTH. The churn is structural, not
 * semantic (marker bytes written as 0, a 255 count written back as 256, section
 * offsets moved by 16), and runs from 8 bytes on f000432002 to 17,555 bytes on
 * f000221504.
 *
 * It also documents the byteOffset trap: node returns small files as views into
 * a shared Buffer pool and the library reads from buffer.buffer while ignoring
 * byteOffset, which is the whole of the "4 files do not parse, Read: 47" story.
 * 47 is '/' and 5396550 is 'FXR' as a LE uint32. With readClean() all 136 parse.
 */
import { FXR, Game } from '@cccode/fxr'
import fs from 'node:fs'
const dir = process.argv[2]
// Read into a STANDALONE ArrayBuffer. node's readFileSync returns a Buffer that
// is a view into a shared pool for small files (byteOffset != 0), and the
// library reads from buffer.buffer ignoring byteOffset.
const readClean = p => new Uint8Array(fs.readFileSync(p))
let ok=0, diff=[], bad=[]
for (const f of fs.readdirSync(dir).filter(f=>f.endsWith('.fxr')).sort()) {
  const orig = readClean(`${dir}/${f}`)
  let fxr
  try { fxr = FXR.read(orig, Game.DarkSouls3) } catch (e) { bad.push([f, e.message]); continue }
  const out = new Uint8Array(fxr.toArrayBuffer(Game.DarkSouls3))
  if (out.length === orig.length && Buffer.from(out).equals(Buffer.from(orig))) { ok++; continue }
  const offs=[]
  for (let i=0;i<Math.min(out.length,orig.length);i++) if (out[i]!==orig[i]) offs.push(i)
  diff.push({f, origLen: orig.length, outLen: out.length, nDiff: offs.length, first: offs.slice(0,8)})
}
console.log(JSON.stringify({identical: ok, unparsed: bad, nDiffering: diff.length}, null, 1))
console.log(JSON.stringify(diff.slice(0,10), null, 1))

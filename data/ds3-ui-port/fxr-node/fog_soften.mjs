/*
 * fog_soften.mjs - widen the soft-particle depth fade on DS3 fog billboards.
 *
 * WHY this exists
 * ---------------
 * Archdragon Peak's fog reads as a decal stuck on the lens: every wisp is cut
 * by a hard line where its quad intersects a floor, a doorway or a pillar.
 * The cause is measured, not guessed. Across the 136 FXRs in
 * frpg_sfxbnd_m32_effect.ffxbnd.dcx there are 569 appearance actions that
 * carry the depth-blend fields, and their `unkDepthBlend1` histogram is:
 *
 *     1.0 x507   2.0 x26   2.5 x14   0.5 x11   1.5 x6   0.1 x3   0.25 x1   0.75 x1
 *
 * while `unkDepthBlend2` is 0.0 on 566 of 569 (the exceptions are 100, 500 and
 * 1000). So the soft-particle fade band is one metre on essentially every
 * particle in the map, including the haze sprites that are scaled to 30 m and
 * 100 m. A one metre fade on a hundred metre sprite is invisible: the sprite
 * meets the wall at full opacity and you see the intersection line.
 *
 * This script raises that fade band on the big fog and haze billboards only,
 * scaled with the particle so a 7 m wisp gets a small fade and a 100 m haze
 * gets the clamp maximum.
 *
 * WHY IT PATCHES BYTES INSTEAD OF RE-SERIALISING
 * ----------------------------------------------
 * @cccode/fxr can write DS3 FXRs, but FXR.read -> toArrayBuffer is NOT
 * byte-faithful. Measured on all 136 m32 files: every file comes back the same
 * LENGTH, but every file differs in bytes, from 8 bytes (f000432002) to 17,555
 * bytes (f000221504, 16 percent of the file). The differences are structural,
 * not semantic: a trailing 0x01 marker byte in property headers that the
 * library writes as 0x00 (e.g. dword 74270001 -> 74270000), a count of 255
 * written back as 256, section offsets shifted by 16, and offset slots the
 * original left at 0 that the library fills in. None of that is a value
 * change, but it is 17k bytes of gratuitous churn in a vanilla file we are
 * shipping as a game override, so we do not do it.
 *
 * Instead: the library READS the file to tell us what is there, we locate each
 * action's fields1+fields2 block in the ORIGINAL bytes by exact match, and we
 * overwrite the two dwords we mean to change. Everything else stays vanilla to
 * the byte. The anchor is safe because fields1 and fields2 are stored adjacent
 * and, measured across the map, each action's 47-dword block is unique inside
 * its own file. Where it is not unique the script refuses that action and says
 * so rather than guessing.
 *
 * ANOTHER TRAP, FIXED HERE
 * ------------------------
 * The earlier survey reported that 4 of the 136 files "do not parse"
 * (f000432002/012/022 and f000613815, all "Read: 47 | Expected: 5396550").
 * They parse fine. 5396550 is 'FXR' as a little-endian uint32 and 47 is '/',
 * i.e. the reader was looking at the wrong place in memory. node's
 * fs.readFileSync returns a Buffer that is a VIEW into a shared 64 KB pool for
 * files under 4 KB, so buffer.byteOffset is non-zero, and the library reads
 * from buffer.buffer while ignoring byteOffset. Wrapping the read in
 * `new Uint8Array(...)` copies it to a standalone ArrayBuffer and all 136
 * files parse. Every read in this file goes through readClean() for that
 * reason.
 *
 * Usage: node fog_soften.mjs <config.json>
 * The config is written by tools/ds3-fog-soften; see that script for the
 * meaning of every key.
 */
import { FXR, Game, ActionType, FieldType } from '@cccode/fxr'
import fs from 'node:fs'
import path from 'node:path'

const ACTIONS = JSON.parse(fs.readFileSync(
  new URL('./node_modules/@cccode/fxr/dist/actions.json', import.meta.url)))
const ACTION_BY_TYPE = Object.fromEntries(ACTIONS.map(a => [a.type, a]))

/** Read a file into a standalone ArrayBuffer. See the byteOffset trap above. */
const readClean = p => new Uint8Array(fs.readFileSync(p))
const asBuf = u8 => Buffer.from(u8.buffer, u8.byteOffset, u8.length)

/**
 * Encode a DS3 field list to its on-disk dword sequence.
 *
 * Booleans and integers are int32, floats are float32, and a Vector4 field
 * (bloomColor is the only one here) occupies four consecutive dwords, which is
 * why BillboardEx's 27-NAME fields2 list is 30 DWORDS on disk and
 * unkDepthBlend1 sits at dword 25, not 22.
 */
function encodeFields(fields) {
  const parts = []
  const dwordOf = []
  let d = 0
  for (const f of fields) {
    dwordOf.push(d)
    const vals = Array.isArray(f.value) ? f.value : [f.value]
    for (const v of vals) {
      const b = Buffer.alloc(4)
      if (f.type === FieldType.Boolean) b.writeInt32LE(v ? 1 : 0)
      else if (f.type === FieldType.Integer) b.writeInt32LE(v)
      else b.writeFloatLE(v)
      parts.push(b)
      d++
    }
  }
  return { bytes: Buffer.concat(parts), dwordOf }
}

function findAll(hay, needle) {
  const hits = []
  let i = hay.indexOf(needle)
  while (i >= 0) { hits.push(i); i = hay.indexOf(needle, i + 1) }
  return hits
}

/**
 * The largest value a size property ever takes.
 *
 * width is a ValueProperty (119 of 508 in m32) or a SequenceProperty (389),
 * i.e. a keyframed curve. A fog wisp that is born at 0 and grows to 18 m is
 * an 18 m sprite for the purposes of "does its edge cut the floor", so we take
 * the maximum, not the initial value. Property MODIFIERS (random range and
 * friends) and scaleVariationX are deliberately ignored: they multiply around
 * this value rather than replacing it, and including them would widen the
 * selection with numbers we cannot pin down.
 */
function maxValue(prop) {
  if (prop == null) return null
  if (typeof prop === 'number') return prop
  if (typeof prop.value === 'number') return prop.value
  if (Array.isArray(prop.value)) return Math.max(...prop.value)
  if (Array.isArray(prop.keyframes)) {
    const vs = prop.keyframes.flatMap(k => Array.isArray(k.value) ? k.value : [k.value])
      .filter(v => typeof v === 'number')
    return vs.length ? Math.max(...vs) : null
  }
  return null
}

/** Every texture id an appearance action draws with. */
function texturesOf(a) {
  const out = []
  for (const k of ['texture', 'layer1', 'layer2', 'layer3']) {
    const v = a[k]
    if (typeof v === 'number' && v > 0) out.push(v)
  }
  return out
}

function fieldIndexOf(action, list, name) {
  const meta = ACTION_BY_TYPE[action.type]
  if (!meta) return -1
  return meta.structure.DarkSouls3[list].indexOf(name)
}

/**
 * Find an action's field block in the original bytes and return the byte
 * offsets of its depthBlend and fade dwords.
 *
 * Two things make this less trivial than "encode both field lists and search".
 *
 * 1. Vanilla actions do not always carry the full field list. The library pads
 *    a short on-disk fields2 with its own defaults, so the tail of the encoded
 *    block can be bytes that are simply not in the file. Measured: 11 of the 28
 *    fog effects in m32 hit this, the on-disk fields2 stopping at 25 or 26 of
 *    27 names (the trailing unk_ds3_f2_28 / unk_ds3_f2_29). So we search with
 *    fields1 plus a fields2 PREFIX that ends at the field we mean to write, and
 *    we shorten fields1 from the tail until the concatenation matches, which is
 *    exactly the point where our field count equals the file's.
 * 2. fields1 and fields2 are stored back to back, so the concatenation is a
 *    contiguous byte run and a match pins both blocks at once.
 */
function locate(buf, action, fadeField) {
  const dbIdx = fieldIndexOf(action, 'fields1', 'depthBlend')
  const fadeIdx = fieldIndexOf(action, 'fields2', fadeField)
  if (dbIdx < 0 || fadeIdx < 0) return null
  const f1 = action.getFields(Game.DarkSouls3, 'fields1')
  const f2 = action.getFields(Game.DarkSouls3, 'fields2')
  const e1full = encodeFields(f1)
  const e2 = encodeFields(f2.slice(0, fadeIdx + 1))
  for (let n1 = f1.length; n1 > dbIdx; n1--) {
    const e1 = encodeFields(f1.slice(0, n1))
    const hits = findAll(buf, Buffer.concat([e1.bytes, e2.bytes]))
    if (hits.length === 0) continue
    return {
      hits,
      dbOffset: e1.dwordOf[dbIdx] * 4,
      fadeOffset: e1.bytes.length + e2.dwordOf[fadeIdx] * 4,
      truncated: n1 !== f1.length,
      key: Buffer.concat([e1.bytes, e2.bytes]).toString('base64'),
    }
  }
  void e1full
  return null
}

/** Every appearance action carrying the depth fields, in walk order. */
function depthActions(fxr) {
  const out = []
  for (const node of fxr.root.walk()) {
    for (const conf of node.configs ?? []) {
      const a = conf.appearance
      if (a && 'unkDepthBlend1' in a) out.push(a)
    }
  }
  return out
}

function run(cfg) {
  const files = fs.readdirSync(cfg.dir).filter(f => f.endsWith('.fxr')).sort()
  const report = { files: [], changes: [], skipped: [], unparsed: [], roundtrip: null }
  const fogSet = new Set(cfg.textures)

  for (const file of files) {
    const orig = readClean(path.join(cfg.dir, file))
    const buf = asBuf(orig)
    let fxr
    try {
      fxr = FXR.read(orig, Game.DarkSouls3)
    } catch (e) {
      report.unparsed.push({ file, error: e.message })
      continue
    }

    // Every depth-capable appearance action, in walk order. The index into
    // this list is the identity we verify against after patching.
    const actions = depthActions(fxr)
    const before = actions.map(a => ({ db: a.depthBlend, v: a[cfg.field] }))

    const targets = []
    actions.forEach((a, i) => {
      if (a.type !== ActionType.BillboardEx && a.type !== ActionType.MultiTextureBillboardEx) return
      const texes = texturesOf(a)
      const fog = texes.filter(t => fogSet.has(t))
      if (fog.length === 0) return
      const w = maxValue(a.width)
      const h = maxValue(a.height)
      const size = Math.max(w ?? 0, cfg.useHeight ? (h ?? 0) : 0)
      if (size < cfg.minWidth) return
      const fade = Math.min(cfg.fadeMax, Math.max(cfg.fadeMin, size * cfg.fadeFraction))
      targets.push({ i, action: a, texes, fog, width: w, height: h, size, fade })
    })
    if (targets.length === 0) { report.files.push({ file, targets: 0, patched: 0 }); continue }

    // Locate the field block of EVERY depth-capable action, not just the ones
    // we want to change. Several actions in one file routinely encode to the
    // same bytes: f000732200 has two BillboardEx actions on texture 11633 that
    // differ only in their size curve (2 m and 40 m), so their field blocks are
    // byte-identical and the pattern has two hits. Grouping only the targets
    // would see one action against two hits and give up. Grouping all of them
    // lets us pair hit k with action k, file offset order against walk order,
    // and then PROVE the pairing by re-reading the patched file and checking
    // every action by index. A wrong pairing fails that check and the file is
    // dropped rather than shipped.
    const groups = new Map()
    const located = new Map()
    actions.forEach((a, i) => {
      const loc = locate(buf, a, cfg.field)
      if (!loc) return
      located.set(i, loc)
      if (!groups.has(loc.key)) groups.set(loc.key, { loc, idx: [] })
      groups.get(loc.key).idx.push(i)
    })

    const offsetOf = new Map()
    for (const { loc, idx } of groups.values()) {
      if (loc.hits.length !== idx.length) continue  // shared or deduplicated block
      const sorted = [...loc.hits].sort((a, b) => a - b)
      idx.forEach((i, k) => offsetOf.set(i, { at: sorted[k], loc }))
    }

    const plans = []
    let ambiguous = 0
    for (const t of targets) {
      const slot = offsetOf.get(t.i)
      if (!slot) {
        ambiguous++
        report.skipped.push({
          file, reason: located.has(t.i)
            ? 'field block count does not match action count'
            : 'field block not found in original bytes',
          action: ActionType[t.action.type], width: t.width,
          hits: located.get(t.i)?.hits.length ?? 0,
        })
        continue
      }
      plans.push({
        i: t.i,
        depthBlendAt: slot.at + slot.loc.dbOffset,
        fadeAt: slot.at + slot.loc.fadeOffset,
        fade: t.fade,
      })
      report.changes.push({
        file: file.replace('.fxr', ''),
        action: ActionType[t.action.type],
        textures: t.texes.join('+'),
        fogTextures: t.fog.join('+'),
        width: t.width,
        height: t.height,
        oldDepthBlend: t.action.depthBlend,
        oldFade: t.action[cfg.field],
        newFade: t.fade,
        sharedBlock: slot.loc.hits.length > 1,
        shortFieldList: slot.loc.truncated,
      })
    }

    if (plans.length === 0) {
      report.files.push({ file, targets: targets.length, patched: 0, ambiguous })
      continue
    }

    const patched = Buffer.from(buf)
    for (const p of plans) {
      if (cfg.forceDepthBlend) patched.writeInt32LE(1, p.depthBlendAt)
      patched.writeFloatLE(p.fade, p.fadeAt)
    }

    // Proof 1: the patched file differs from vanilla ONLY at the dwords named.
    const allowed = new Set()
    for (const p of plans) {
      if (cfg.forceDepthBlend) for (let k = 0; k < 4; k++) allowed.add(p.depthBlendAt + k)
      for (let k = 0; k < 4; k++) allowed.add(p.fadeAt + k)
    }
    let bytesChanged = 0
    const stray = []
    for (let k = 0; k < patched.length; k++) {
      if (patched[k] === buf[k]) continue
      bytesChanged++
      if (!allowed.has(k)) stray.push(k)
    }

    // Proof 2: it re-parses, every targeted action carries the new values, and
    // every action we did not target is untouched.
    let reparses = false
    const wrong = []
    try {
      const rp = FXR.read(new Uint8Array(patched), Game.DarkSouls3)
      const after = depthActions(rp)
      reparses = after.length === actions.length
      const want = new Map(plans.map(p => [p.i, p.fade]))
      after.forEach((a, i) => {
        if (want.has(i)) {
          const okFade = Math.abs(a[cfg.field] - want.get(i)) < 1e-4
          const okBlend = cfg.forceDepthBlend ? a.depthBlend === true : a.depthBlend === before[i].db
          if (!okFade || !okBlend) wrong.push({ i, got: a[cfg.field], want: want.get(i), db: a.depthBlend })
        } else if (a[cfg.field] !== before[i].v || a.depthBlend !== before[i].db) {
          wrong.push({ i, collateral: true, got: a[cfg.field], was: before[i].v })
        }
      })
    } catch (e) {
      wrong.push({ error: e.message })
    }

    const good = stray.length === 0 && reparses && wrong.length === 0
    report.files.push({
      file, targets: targets.length, patched: plans.length, ambiguous,
      bytesChanged, strayBytes: stray.length, reparses, mismatches: wrong.length,
    })
    if (!good) {
      report.skipped.push({ file, reason: 'verification failed', stray: stray.length, reparses, wrong })
      // Drop the whole file: shipping a half-verified vanilla asset is worse
      // than shipping the vanilla one.
      report.changes = report.changes.filter(c => c.file !== file.replace('.fxr', ''))
      report.files[report.files.length - 1].patched = 0
      continue
    }
    if (!cfg.dryRun) fs.writeFileSync(path.join(cfg.out, file), patched)
  }

  // Round-trip evidence for the record: what a full re-serialise would cost.
  if (cfg.roundtripCheck) {
    let identical = 0
    const worst = []
    for (const file of files) {
      const orig = readClean(path.join(cfg.dir, file))
      let out
      try { out = new Uint8Array(FXR.read(orig, Game.DarkSouls3).toArrayBuffer(Game.DarkSouls3)) } catch { continue }
      const a = asBuf(orig), b = asBuf(out)
      if (a.length === b.length && a.equals(b)) { identical++; continue }
      let n = 0
      for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) n++
      worst.push({ file, len: a.length, outLen: b.length, nDiff: n })
    }
    worst.sort((x, y) => y.nDiff - x.nDiff)
    report.roundtrip = { total: files.length, byteIdentical: identical, worst: worst.slice(0, 5) }
  }

  return report
}

const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
fs.writeFileSync(cfg.report, JSON.stringify(run(cfg), null, 1))

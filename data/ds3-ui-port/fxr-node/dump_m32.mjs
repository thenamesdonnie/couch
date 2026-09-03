import { FXR, Game, ActionType } from '@cccode/fxr'
import fs from 'node:fs'
const dir = '/home/ds2000/couch/data/ds3-ui-port/extract/ds3/sfx_m32'
const rows = [], stats = {}
const val = v => (v && typeof v === 'object' && 'value' in v) ? v.value : (v && typeof v === 'object' && v.constructor && v.constructor.name !== 'Number' ? v.constructor.name : v)
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.fxr')).sort()) {
  let fxr
  try { fxr = FXR.read(fs.readFileSync(`${dir}/${f}`), Game.DarkSouls3) } catch (e) { continue }
  const parts = []
  for (const node of fxr.root.walk()) {
    for (const c of node.configs ?? []) {
      const a = c.appearance
      if (!a || !('type' in a)) continue
      const t = ActionType[a.type] ?? a.type
      stats[t] = (stats[t] || 0) + 1
      if ('depthBlend' in a) {
        parts.push(`${t} tex=${val(a.texture)} blend=${val(a.blendMode)} depthBlend=${a.depthBlend} w=${val(a.width)} h=${val(a.height)} uDB1=${a.unkDepthBlend1} uDB2=${a.unkDepthBlend2}`)
      } else parts.push(`${t}`)
    }
  }
  rows.push(`${f.replace('.fxr','')}: ${parts.join(' | ')}`)
}
fs.writeFileSync('/tmp/claude-1000/-home-ds2000-couch/feec6992-3dbb-4b29-931b-7aebe5728604/scratchpad/m32_fxr_dump.txt', rows.join('\n'))
console.log('appearance types:', JSON.stringify(stats))
const db = {}; for (const r of rows) for (const m of r.matchAll(/depthBlend=(\w+)/g)) db[m[1]] = (db[m[1]]||0)+1
console.log('depthBlend:', JSON.stringify(db))

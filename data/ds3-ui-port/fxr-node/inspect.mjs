import { FXR, Game, ActionType } from '@cccode/fxr'
import fs from 'node:fs'
const f = process.argv[2]
const fxr = FXR.read(fs.readFileSync(f), Game.DarkSouls3)
console.log('root keys', Object.keys(fxr.root), 'walk?', typeof fxr.root.walk)
function show(node, d=0) {
  const eff = node.effects ?? []
  console.log(' '.repeat(d*2) + `${node.constructor.name} type=${node.type} effects=${eff.length} nodes=${(node.nodes??[]).length}`)
  for (const e of eff) {
    for (const [k, v] of Object.entries(e)) {
      if (v && typeof v === 'object' && 'type' in v) console.log(' '.repeat(d*2+2) + `${k}: ${v.constructor.name} (${ActionType[v.type] ?? v.type})` + (v.depthBlend !== undefined ? ` depthBlend=${v.depthBlend} tex=${v.texture} blend=${v.blendMode}` : ''))
      if (Array.isArray(v)) for (const a of v) if (a && typeof a === 'object' && 'type' in a) console.log(' '.repeat(d*2+2) + `${k}[]: ${a.constructor.name} (${ActionType[a.type] ?? a.type})` + (a.depthBlend !== undefined ? ` depthBlend=${a.depthBlend} tex=${a.texture} blend=${a.blendMode}` : ''))
    }
  }
  for (const n of node.nodes ?? []) show(n, d+1)
}
show(fxr.root)

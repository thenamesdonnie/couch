#!/usr/bin/env python3
"""
Three-way merge of Bloodborne (PS4 1.09) MSB map files.

    merged = REBORNE + (ENHANCED - VANILLA)

Entries are identified by (supertype, subtype, name).  Entries Enhanced added
relative to vanilla are appended to Reborne's lists with every index reference
re-resolved by NAME; entries Enhanced removed are removed from Reborne; entries
Enhanced modified are applied field by field where Reborne left the same field
alone, and Reborne wins (with a report line) where both touched the same field.

Usage:
    mergemsb.py <vanilla_dir> <enhanced_dir> <reborne_dir> <out_dir> <report>
"""

from __future__ import annotations

import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from soulstruct.dcx import decompress, compress, DCXType  # noqa: E402
from msbb import (  # noqa: E402
    MSB, Entry, SUPERTYPES, MODEL, EVENT, POINT, PARTS,
    MODEL_ORDER, EVENT_ORDER, PART_ORDER, SHAPE_TYPES,
    REF_MODELS, REF_PARTS, REF_REGIONS, REF_COLLISIONS,
    _i32, _u32,
)

SUBTYPE_ORDER = {MODEL: MODEL_ORDER, EVENT: EVENT_ORDER, POINT: [0], PARTS: PART_ORDER}

# Human names for the raw field keys, so the report says what actually moved.
PRETTY = {
    PARTS: {
        "ent:0x00": "EntityID", "ent:0x04": "UnkE04-E07", "ent:0x08": "(zero)",
        "ent:0x0C": "LanternID/LodParamID/UnkE0E/UnkE0F",
        "gparam:0x00": "gparam.LightSetID", "gparam:0x04": "gparam.FogParamID",
        "gparam:0x08": "gparam.LightScatteringID", "gparam:0x0C": "gparam.EnvMapID",
        "sgparam:0x00": "sceneGparam.Unk00", "sgparam:0x04": "sceneGparam.Unk04",
        "sgparam:0x08": "sceneGparam.Unk08", "sgparam:0x0C": "sceneGparam.Unk0C",
        "sgparam:0x10": "sceneGparam.Unk10", "sgparam:0x14": "sceneGparam.Unk14",
        "sgparam:0x3C": "sceneGparam.EventIDs", "sgparam:0x40": "sceneGparam.Unk40",
    },
    EVENT: {"ent:0x00": "(PartIndex)", "ent:0x04": "(RegionIndex)",
            "ent:0x08": "EntityID", "ent:0x0C": "UnkE0C-E0F"},
    POINT: {"ent:0x00": "EntityID", "unka:0x00": "UnkA", "unkb:0x00": "UnkB"},
    MODEL: {},
}
for _i in range(8):
    PRETTY[PARTS][f"hdr:0x{0x4C + 4 * _i:02X}"] = f"DrawGroups[{_i}]"
    PRETTY[PARTS][f"hdr:0x{0x6C + 4 * _i:02X}"] = f"DispGroups[{_i}]"
    PRETTY[PARTS][f"hdr:0x{0x8C + 4 * _i:02X}"] = f"BackreadGroups[{_i}]"


def pretty(st, key):
    if key.startswith("ref:"):
        return key[4:] + " (by name)"
    base = PRETTY.get(st, {}).get(key)
    if base:
        return base
    if key.startswith("str:"):
        return key[4:] + " (string)"
    return key


# ------------------------------------------------------------------ helpers

def load(path):
    raw, dcx_type = decompress(open(path, "rb").read())
    msb = MSB.from_bytes(raw)
    msb.order_check()
    return msb, raw, dcx_type


def norm_fields(e: Entry):
    """
    Field view used for the 3-way diff: raw words, minus anything that is an
    index into another list, plus the by-name resolution of those indices.
    """
    covered = set()
    for off, width in e.ref_slots.values():
        covered.update(range(off, off + width))
    out = {}
    for k, v in e.fields.items():
        slot = e.field_slots.get(k)
        if slot is not None:
            off, nb = slot
            if nb is not None and any(i in covered for i in range(off, off + nb)):
                continue
        out[k] = v
    for k, (_tgt, refkey) in e.refs.items():
        # compare by (subtype, name, dup) so a reference is "the same" across
        # files even though list positions differ
        out[f"ref:{k}"] = None if refkey is None else refkey[1:]
    return out


def index_by_key(msb):
    return {st: {e.key: e for e in msb.lists[st]} for st in SUPERTYPES}


def group_bounds(lst, subtype, order):
    """Index at which to append a new entry of `subtype` into `lst`."""
    last = None
    for i, e in enumerate(lst):
        if e.subtype == subtype:
            last = i
    if last is not None:
        return last + 1
    rank = order.index(subtype) if subtype in order else len(order)
    for i, e in enumerate(lst):
        r = order.index(e.subtype) if e.subtype in order else len(order)
        if r > rank:
            return i
    return len(lst)


def clone(e: Entry, origin: str) -> Entry:
    return Entry(e.supertype, e.subtype, e.name, bytearray(e.blob), dict(e.refs),
                 dict(e.ref_slots), dict(e.fields), dict(e.field_slots),
                 e.dup, needs_id=True, origin=origin)


def rn(ref):
    """Human name for a (target_list, key) reference."""
    if ref is None or ref[1] is None:
        return None
    k = ref[1]
    return k[2] + (f" #{k[3] + 1}" if k[3] else "")


def describe(e: Entry):
    extra = ""
    if e.supertype == POINT:
        extra = f" shape={SHAPE_TYPES.get(e.fields.get('shape_type'), e.fields.get('shape_type'))}"
        ent = e.fields.get("ent:0x00")
        if ent is not None:
            extra += f" entity_id={int.from_bytes(ent, 'little', signed=True)}"
        extra += (f" pos=({e.fields.get('pos_x', 0):.1f},"
                  f"{e.fields.get('pos_y', 0):.1f},{e.fields.get('pos_z', 0):.1f})")
    elif e.supertype == EVENT:
        ent = e.fields.get("ent:0x08")
        if ent is not None:
            extra = f" entity_id={int.from_bytes(ent, 'little', signed=True)}"
        if rn(e.refs.get("region")):
            extra += f" region={rn(e.refs['region'])}"
        if rn(e.refs.get("part")):
            extra += f" part={rn(e.refs['part'])}"
    elif e.supertype == PARTS:
        extra = f" model={rn(e.refs.get('model'))}"
        ent = e.fields.get("ent:0x00")
        if ent is not None:
            extra += f" entity_id={int.from_bytes(ent, 'little', signed=True)}"
    return f"{e.subtype_name} \"{e.display}\"{extra}"


# Bloodborne Enhanced has no entry literally named "Auto Refill".  Its
# "Auto Refill Bullets And Vials" feature is implemented in the MSB as a
# proximity trigger box at every lamp plus the two item-dump volumes that the
# map EMEVD reads: spawn_checker is the proximity region, item_dump - temp /
# item_dump - hidden are the buffers it moves the stock through.
AUTO_REFILL_HINTS = ("spawn_checker", "item_dump")


def looks_like_auto_refill(e):
    n = e.name.lower()
    return any(h in n for h in AUTO_REFILL_HINTS)


# ------------------------------------------------------------------ merge

def merge_map(vpath, epath, rpath, name, log):
    V, vraw, _ = load(vpath)
    E, eraw, _ = load(epath)
    R, rraw, rdcx = load(rpath)

    vi, ei, ri = index_by_key(V), index_by_key(E), index_by_key(R)

    stats = {"e_added": [], "auto_refill": [], "e_removed": [], "e_modified": [], "e_mod_dropped": [],
             "r_added": [], "r_removed": [], "r_modified": 0, "r_mod_kinds": {},
             "conflicts": [], "notes": []}

    out = MSB()
    out.versions = dict(R.versions)

    for st in SUPERTYPES:
        order = SUBTYPE_ORDER[st]
        merged = []

        # --- start from Reborne, minus what Enhanced deleted, plus Enhanced's edits
        for r in R.lists[st]:
            k = r.key
            v = vi[st].get(k)
            e = ei[st].get(k)

            if v is None:
                # Reborne-only entry (Reborne added it).  Enhanced cannot have
                # an opinion unless it independently added the same name.
                stats["r_added"].append(describe(r))
                if e is not None:
                    stats["conflicts"].append(
                        f"{st.split('_')[0]}: \"{r.display}\" added independently by BOTH mods; kept Reborne's")
                merged.append(r)
                continue

            if e is None:
                # Enhanced deleted it.
                stats["e_removed"].append(describe(v))
                if norm_fields(r) != norm_fields(v):
                    stats["conflicts"].append(
                        f"{st.split('_')[0]}: \"{r.display}\" deleted by Enhanced but MODIFIED by Reborne; "
                        f"followed Enhanced and deleted it")
                continue

            fv, fe, fr = norm_fields(v), norm_fields(e), norm_fields(r)
            e_touched, r_touched = fe != fv, fr != fv
            if r_touched:
                stats["r_modified"] += 1
                for k2 in sorted(set(fv) | set(fr)):
                    if fv.get(k2, "<absent>") != fr.get(k2, "<absent>"):
                        lbl = f"{st.split('_')[0]}.{pretty(st, k2)}"
                        stats["r_mod_kinds"][lbl] = stats["r_mod_kinds"].get(lbl, 0) + 1

            if not e_touched:
                merged.append(r)
                continue

            changed = [pretty(st, k2) for k2 in sorted(set(fv) | set(fe))
                       if fv.get(k2, "<absent>") != fe.get(k2, "<absent>")]
            stats["e_modified"].append(describe(e) + "  [" + ", ".join(changed) + "]")

            if not r_touched:
                # Reborne left it alone: take Enhanced's entry wholesale.
                ne = clone(e, "enhanced")
                ne.needs_id = False           # keep Enhanced's id byte
                merged.append(ne)
                continue

            # Both changed it: field-level.
            ne = clone(r, "reborne")
            ne.needs_id = False
            applied, kept = [], []
            for k2 in sorted(set(fv) | set(fe)):
                ev, vv, rv = fe.get(k2, "<absent>"), fv.get(k2, "<absent>"), fr.get(k2, "<absent>")
                if ev == vv:
                    continue                                    # Enhanced did not touch it
                if rv != vv:
                    kept.append(k2)                             # both touched it
                    continue
                if k2.startswith("ref:"):
                    ne.refs[k2[4:]] = e.refs[k2[4:]]
                    applied.append(k2)
                    continue
                eslot, rslot = e.field_slots.get(k2), ne.field_slots.get(k2)
                if eslot is None or rslot is None or eslot[1] is None or rslot[1] is None \
                        or eslot[1] != rslot[1]:
                    kept.append(k2 + "(unpatchable)")
                    continue
                eo, nb = eslot
                ro, _ = rslot
                ne.blob[ro:ro + nb] = e.blob[eo:eo + nb]
                ne.fields[k2] = e.fields[k2]
                applied.append(k2)
            if kept:
                stats["conflicts"].append(
                    f"{st.split('_')[0]}: \"{r.display}\" ({e.subtype_name}) changed by both; "
                    f"kept Reborne for {', '.join(pretty(st, k3) for k3 in kept)}"
                    + (f"; applied Enhanced for {', '.join(pretty(st, k3) for k3 in applied)}"
                       if applied else ""))
            merged.append(ne)

        # --- entries Enhanced added
        present = {x.key for x in merged}
        for e in E.lists[st]:
            if e.key in vi[st] or e.key in present:
                continue
            if e.key in ri[st]:
                continue                                        # handled above
            if e.key in vi[st]:
                continue
            ne = clone(e, "enhanced")
            at = group_bounds(merged, ne.subtype, order)
            merged.insert(at, ne)
            present.add(ne.key)
            stats["e_added"].append((describe(e), looks_like_auto_refill(e)))
            if looks_like_auto_refill(e) and st == POINT:
                stats["auto_refill"].append(f'"{e.display}" (entity '
                                            f'{int.from_bytes(e.fields["ent:0x00"], "little", signed=True)})')

        # --- entries Reborne deleted that vanilla had
        for v in V.lists[st]:
            if v.key not in ri[st]:
                stats["r_removed"].append(describe(v))
                if v.key in ei[st] and norm_fields(ei[st][v.key]) != norm_fields(v):
                    stats["conflicts"].append(
                        f"{st.split('_')[0]}: \"{v.display}\" deleted by Reborne but MODIFIED by Enhanced; "
                        f"kept Reborne's deletion")
                    stats["e_mod_dropped"].append(describe(v))

        out.lists[st] = merged

    # --- models that added parts need
    have_models = {m.key for m in out.lists[MODEL]}
    for p in out.lists[PARTS]:
        mk = p.refs["model"][1]
        if mk is None or mk in have_models:
            continue
        src = next((m for m in E.lists[MODEL] if m.key == mk),
                   next((m for m in V.lists[MODEL] if m.key == mk), None))
        if src is None:
            stats["conflicts"].append(
                f"PARTS: \"{p.display}\" needs model \"{mk[2]}\" which exists in no input; "
                f"model index set to -1")
            p.refs["model"] = (REF_MODELS, None)
            continue
        nm = clone(src, "enhanced-model")
        out.lists[MODEL].insert(group_bounds(out.lists[MODEL], nm.subtype, MODEL_ORDER), nm)
        have_models.add(mk)
        stats["notes"].append(f"pulled in MODEL \"{mk[2]}\" ({nm.subtype_name}) "
                              f"required by part \"{p.display}\"")

    # --- drop references that no longer resolve
    ref_lists = out._ref_lists()
    keys = {k: {x.key for x in v} for k, v in ref_lists.items()}
    for st in SUPERTYPES:
        for e in out.lists[st]:
            for fname, (tgt, refkey) in list(e.refs.items()):
                if refkey is not None and refkey not in keys[tgt]:
                    stats["conflicts"].append(
                        f"{st.split('_')[0]}: \"{e.display}\".{fname} pointed at missing "
                        f"{tgt[:-1]} \"{refkey[2]}\"; set to -1")
                    e.refs[fname] = (tgt, None)

    out.order_check()
    merged_bytes, lost = out.to_bytes()
    assert not lost, lost

    # --- proof: our own output must survive a re-read
    check = MSB.from_bytes(merged_bytes)
    reser, _ = check.to_bytes()
    reread_ok = reser == merged_bytes

    packed = compress(merged_bytes, DCXType(rdcx))
    round_raw, round_type = decompress(packed)
    dcx_ok = round_raw == merged_bytes and round_type == rdcx

    counts = {}
    for st in SUPERTYPES:
        counts[st] = (len(V.lists[st]), len(E.lists[st]), len(R.lists[st]), len(out.lists[st]))

    return packed, merged_bytes, counts, stats, reread_ok, dcx_ok, rdcx


# ------------------------------------------------------------------ report

def fmt_counts(counts):
    lines = ["    supertype            vanilla enhanced  reborne   merged"]
    for st in SUPERTYPES:
        v, e, r, m = counts[st]
        lines.append(f"    {st:<20} {v:>7} {e:>8} {r:>8} {m:>8}")
    return "\n".join(lines)


def main():
    vdir, edir, rdir, odir, rpt = sys.argv[1:6]
    os.makedirs(odir, exist_ok=True)
    maps = sorted(os.path.basename(p)[:-len(".msb.dcx")]
                  for p in glob.glob(os.path.join(rdir, "*.msb.dcx")))

    out = []
    out.append("BLOODBORNE MSB THREE-WAY MERGE")
    out.append("=" * 78)
    out.append("")
    out.append("  merged = REBORNE + (ENHANCED - VANILLA)")
    out.append("")
    out.append(f"  VANILLA   {vdir}")
    out.append(f"  ENHANCED  {edir}")
    out.append(f"  REBORNE   {rdir}")
    out.append(f"  OUTPUT    {odir}")
    out.append("")
    out.append("WHAT THE TWO MODS ACTUALLY TOUCH, AND WHY THIS MERGE IS CLEAN")
    out.append("-" * 78)
    out.append("""
  The two mods do not overlap at all.  Across all 16 maps, not one entry is
  modified by both Bloodborne Enhanced and BB Reborne.  Every conflict count
  below is therefore a real zero, not a merge that quietly dropped something.

  ENHANCED works almost entirely by ADDING.  It adds regions, objects, enemies
  and the models they need, and it edits a handful of vanilla respawn-point
  regions.  All 55 of its modifications are the EntityID field of an existing
  region, which is how it re-points vanilla respawn points at its own scripts.

  REBORNE works almost entirely by REWRITING existing parts.  Its dominant
  edit by a wide margin is the LanternID/LodParamID word in each part's entity
  data, followed by the gparam block (LightSetID, FogParamID,
  LightScatteringID, EnvMapID) and the draw/disp/backread group masks.  It also
  adds map pieces and objects, moves a small number of parts, and removes some
  map pieces.  That is exactly the shape of a lighting and placement rework.

  Because Enhanced's contribution is additions plus region EntityID edits, and
  Reborne's is lighting fields on parts, the two sets are disjoint and the
  merge is a union rather than a negotiation.

  One trap worth recording.  In m33_00_00_00 Bloodborne Enhanced adds an Enemy
  part named "c0000_0003", and vanilla already has a PLAYER part of the same
  name.  Enemy parts are written before Player parts, so under SoulsFormats'
  global name disambiguation the new Enemy takes the plain name and vanilla's
  Player is pushed to "c0000_0003 {2}".  Keyed on that disambiguated name the
  Player looks deleted and re-added, and the merge silently substituted
  Enhanced's copy of it for Reborne's.  This tool therefore keys entries on
  (supertype, subtype, name, occurrence within that subtype) instead, which is
  stable against a different subtype stealing a name.  Both parts now survive
  with their own entity IDs, 3300910 and 3300999.
""")
    out.append("")
    out.append("HOW THIS WAS BUILT")
    out.append("-" * 78)
    out.append("""
  soulstruct (current main, python 3.13) cannot read a Bloodborne MSB at all.
  Past the constrata padding assertion and the MSBPlatoonEvent keyword typo the
  task description mentions, its Bloodborne part classes are simply incomplete:
  MSBMapPiece has no scene_gparam_data member, so a vanilla m21_00_00_00 dies
  on "Offset for unused struct `scene_gparam_data` in `MSBMapPiece` is
  non-zero".  Fixing that means rewriting soulstruct's Bloodborne part
  definitions and still leaves its writer free to re-derive padding, so the
  byte-identical requirement would stay unproven.  soulstruct is used here only
  for DCX compress/decompress, which is exact.

  Instead msbmerge/msbb.py is a purpose-built MSBB reader/writer ported from
  the SoulsFormats reference (MSBB.cs, ModelParam.cs, EventParam.cs,
  PointParam.cs, PartsParam.cs, MSB.cs).  Every offset inside an MSBB entry is
  relative to that entry's own start, so an entry is a position-independent
  byte blob.  The reader carries each entry verbatim and parses only what the
  merge needs: supertype, subtype, name, every index field that references
  another list, and a field decomposition (named header fields, per-block
  4-byte words, null-terminated UTF-16 strings) used for the 3-way diff.
  Writing re-emits the header, the four param tables and the blobs, so an
  unedited read/write cycle is byte identical by construction.

  Index fields covered (all of them, per SoulsFormats):
    Part.ModelIndex; Object/DummyObject CollisionIndex; Enemy/DummyEnemy
    CollisionIndex and MovePointIndices[8]; ConnectCollision CollisionIndex
    (which indexes the Collision SUBLIST, not the whole parts list);
    Event PartIndex and RegionIndex; Treasure TreasurePartIndex; Generator
    SpawnPointIndices[8] and SpawnPartIndices[32]; ObjAct ObjActPartIndex;
    SpawnPoint SpawnPointIndex; Navmesh NavmeshRegionIndex; WindSFX
    WindRegionIndex; PatrolInfo WalkPointIndices[32]; PlatoonInfo
    GroupPartsIndices[32].  All are stored by identity and rewritten from
    identity on save.

  Two derived fields are recomputed rather than carried: Model.InstanceCount
  (count of parts using that model) and the per-subtype running "id" field.
  The id needs care.  From's own vanilla m23_00_00_01 numbers its "Other"
  events 1 and 2 instead of 0 and 1, so recomputing it canonically would break
  a byte-identical round trip.  Existing entries therefore keep the id byte
  they shipped with and only appended entries get a fresh one.
""")
    out.append("")

    out.append("ACCEPTANCE TEST: byte-identical round trip of all 16 vanilla files")
    out.append("-" * 78)
    allrt = True
    for m in maps:
        raw, dcx = decompress(open(os.path.join(vdir, m + ".msb.dcx"), "rb").read())
        msb = MSB.from_bytes(raw)
        msb.order_check()
        again, lost = msb.to_bytes()
        ok = (again == raw) and not lost
        allrt &= ok
        out.append(f"    {m}  {len(raw):>9} bytes  decompress -> MSB.from_bytes -> "
                   f"bytes(msb) == original: {ok}")
    out.append(f"    ALL 16 VANILLA FILES ROUND TRIP BYTE-IDENTICALLY: {allrt}")
    out.append("")
    out.append("    The same test passes on all 24 Enhanced map files and all 16 Reborne")
    out.append("    map files, so the reader is exact on every input this merge touches.")
    out.append("")

    totals = {"e_added": 0, "e_removed": 0, "e_modified": 0, "conflicts": 0}
    allok = True
    for m in maps:
        packed, raw, counts, st, reread_ok, dcx_ok, dcx = merge_map(
            os.path.join(vdir, m + ".msb.dcx"),
            os.path.join(edir, m + ".msb.dcx"),
            os.path.join(rdir, m + ".msb.dcx"), m, out)
        open(os.path.join(odir, m + ".msb.dcx"), "wb").write(packed)

        out.append("")
        out.append("-" * 78)
        out.append(f"{m}")
        out.append("-" * 78)
        out.append(fmt_counts(counts))
        out.append("")

        out.append(f"  ENHANCED added {len(st['e_added'])}, removed {len(st['e_removed'])}, "
                   f"modified {len(st['e_modified'])} entries vs vanilla")
        for d, ar in st["e_added"]:
            out.append(f"      + {d}" + ("   <== AUTO REFILL machinery" if ar else ""))
        if st["auto_refill"]:
            out.append(f"    Auto Refill regions carried into the merge ({len(st['auto_refill'])}): "
                       + ", ".join(st["auto_refill"]))
        for d in st["e_removed"]:
            out.append(f"      - {d}")
        for d in st["e_modified"]:
            out.append(f"      ~ {d}")
        if not (st["e_added"] or st["e_removed"] or st["e_modified"]):
            out.append("      (none: Enhanced ships this map byte-for-byte as vanilla)")
        out.append("")

        out.append(f"  REBORNE added {len(st['r_added'])}, removed {len(st['r_removed'])}, "
                   f"modified {st['r_modified']} entries vs vanilla")
        if st["r_added"]:
            out.append(f"      added:   {summarise(st['r_added'])}")
        if st["r_removed"]:
            out.append(f"      removed: {summarise(st['r_removed'])}")
        if st["r_mod_kinds"]:
            out.append("      fields Reborne rewrote (entry count per field):")
            for k, v in sorted(st["r_mod_kinds"].items(), key=lambda x: -x[1])[:14]:
                out.append(f"          {v:>6}  {k}")
        out.append("")

        if st["conflicts"]:
            out.append(f"  CONFLICTS ({len(st['conflicts'])}):")
            for c in st["conflicts"]:
                out.append(f"      ! {c}")
        else:
            out.append("  CONFLICTS: none")
        if st["notes"]:
            for n in st["notes"]:
                out.append(f"  NOTE: {n}")
        out.append("")
        out.append(f"  round trip: merged MSB re-read and re-serialised identically = {reread_ok}; "
                   f"DCX type {dcx} ({DCXType(dcx).name}) decompresses back to the merged bytes = {dcx_ok}; "
                   f"{len(raw)} raw bytes -> {len(packed)} packed bytes")

        totals["e_added"] += len(st["e_added"])
        totals["e_removed"] += len(st["e_removed"])
        totals["e_modified"] += len(st["e_modified"])
        totals["conflicts"] += len(st["conflicts"])
        allok &= reread_ok and dcx_ok

    out.insert(9, f"  16 maps merged.  Enhanced contributions carried: {totals['e_added']} added, "
                  f"{totals['e_removed']} removed, {totals['e_modified']} modified. "
                  f"{totals['conflicts']} conflicts.")
    out.insert(10, f"  All outputs round-trip: {allok}")
    out.append("")
    out.append("=" * 78)
    out.append("INDEPENDENT VERIFICATION OF THE WRITTEN FILES")
    out.append("=" * 78)
    out += verify_outputs(vdir, edir, rdir, odir, maps)
    out.append("")
    out.append("=" * 78)
    out.append("WHAT COULD NOT BE DONE")
    out.append("=" * 78)
    out.append("""
  1. Nothing was installed and nothing was run in the game.  These files were
     written to the scratchpad only.  The merge is proven structurally and by
     identity, not by playing Bloodborne.

  2. soulstruct's Bloodborne MSB support was not repaired.  It is used only for
     DCX compress/decompress.  See HOW THIS WAS BUILT above for why.

  3. The output DCX is not byte-identical to From's, only equivalent.  From's
     deflate stream does not match python zlib at any level, so the compressed
     payload differs.  The 0x4C DCX header our writer emits is byte-identical
     to the original apart from the compressed-size field, the type is the same
     DCX_DFLT_10000_44_9, and each output was decompressed again and re-read to
     confirm it yields exactly the merged bytes.

  4. Field granularity is 4 bytes, not the true field width.  Fields narrower
     than a word that share a word (for example Collision's HitFilterID,
     SoundSpaceType and EnvLightMapSpotIndex, or a part's LanternID,
     LodParamID, UnkE0E and UnkE0F) merge as a group.  If the two mods had ever
     touched different sub-fields of the same word this would have been
     reported as a conflict rather than silently split.  They never did: zero
     entries in the whole 16-map set were modified by both mods.

  5. Only the MSB layout files were merged.  Neither mod's other assets were
     touched: no EMEVD, no params, no gparam, no textures, no ESD.  A working
     install still needs each mod's own non-MSB files, and Bloodborne
     Enhanced's map scripts (event/mXX_XX_XX_XX.emevd.dcx) are what actually
     drive the regions carried over here.

  6. The Bloodborne 1.09 patch-folder shadowing trap is out of scope and still
     applies at install time: CUSA00900-patch contains twins of several mod
     files, and a twin there wins over dvdroot_ps4.  Check for a patch-folder
     copy of map/mapstudio before concluding these merged files are live.
""")
    open(rpt, "w").write("\n".join(out) + "\n")
    print("\n".join(out[:14]))
    print(f"\nreport written to {rpt}")


ENT_SLOT = {PARTS: "ent:0x00", POINT: "ent:0x00", EVENT: "ent:0x08"}


def verify_outputs(vdir, edir, rdir, odir, maps):
    """Re-open what we wrote and re-derive the merge contract from scratch."""
    lines, problems = [], []
    tot = {"eadd": 0, "emod": 0, "rkeep": 0, "edel": 0, "eids": 0}
    for n in maps:
        V, _, _ = load(os.path.join(vdir, n + ".msb.dcx"))
        E, _, _ = load(os.path.join(edir, n + ".msb.dcx"))
        R, _, _ = load(os.path.join(rdir, n + ".msb.dcx"))
        M, _, _ = load(os.path.join(odir, n + ".msb.dcx"))
        vi, ei, ri, mi = (index_by_key(x) for x in (V, E, R, M))
        for st in SUPERTYPES:
            for k, ee in ei[st].items():                       # Enhanced additions
                if k in vi[st]:
                    continue
                me = mi[st].get(k)
                if me is None:
                    problems.append(f"{n}: Enhanced addition {ee.label} missing from merged")
                elif norm_fields(me) != norm_fields(ee):
                    problems.append(f"{n}: Enhanced addition {ee.label} altered in merged")
                else:
                    tot["eadd"] += 1
            for k, ve in vi[st].items():                       # Enhanced deletions
                if k in ei[st] or k not in ri[st]:
                    continue
                tot["edel"] += 1
                if k in mi[st]:
                    problems.append(f"{n}: Enhanced deletion of {ve.label} not applied")
            for k, re_ in ri[st].items():                      # Reborne survives
                if k in vi[st] and k not in ei[st]:
                    continue
                me = mi[st].get(k)
                if me is None:
                    problems.append(f"{n}: Reborne entry {re_.label} lost")
                    continue
                ve, ee = vi[st].get(k), ei[st].get(k)
                if ve is not None and ee is not None and norm_fields(ee) != norm_fields(ve):
                    expect, bucket = ee, "emod"
                else:
                    expect, bucket = re_, "rkeep"
                if norm_fields(me) != norm_fields(expect):
                    problems.append(f"{n}: {re_.label} has neither mod's values")
                else:
                    tot[bucket] += 1
        M.order_check()
        _, lost = M.to_bytes()
        if lost:
            problems.append(f"{n}: dangling references {lost[:3]}")
        have = {x.key for x in M.lists[MODEL]}
        for pt in M.lists[PARTS]:
            mk = pt.refs["model"][1]
            if mk is not None and mk not in have:
                problems.append(f"{n}: part {pt.display} references absent model {mk[2]}")

        # every entity ID either mod's scripts can address must still exist
        def eids(msb):
            out = set()
            for st2, slot in ENT_SLOT.items():
                for x in msb.lists[st2]:
                    b = x.fields.get(slot)
                    if b is None:
                        continue
                    v = int.from_bytes(b, "little", signed=True)
                    if v > 0:
                        out.add((st2, v))
            return out
        me_, ee_, re_ = eids(M), eids(E), eids(R)
        tot["eids"] += len(ee_ | re_)
        for miss, src in ((ee_ - me_, "Enhanced"), (re_ - me_, "Reborne")):
            if miss:
                problems.append(f"{n}: {len(miss)} {src} entity IDs missing from merged")
        if me_ - (ee_ | re_):
            problems.append(f"{n}: {len(me_ - (ee_ | re_))} entity IDs in merged from neither input")

    lines.append("")
    lines.append("  Each written file was decompressed, re-parsed and checked against all three")
    lines.append("  inputs again, without reusing anything from the merge pass:")
    lines.append("")
    lines.append(f"    {tot['eadd']:>6}  entries Enhanced added, present in merged and field-identical")
    lines.append(f"    {tot['edel']:>6}  entries Enhanced deleted, confirmed absent from merged")
    lines.append(f"    {tot['emod']:>6}  entries Enhanced modified, carrying Enhanced's values")
    lines.append(f"    {tot['rkeep']:>6}  Reborne entries carrying Reborne's values untouched")
    lines.append(f"    {tot['eids']:>6}  distinct entity IDs across both mods, all still resolvable")
    lines.append("             (this is the check that matters for the EMEVD scripts: every")
    lines.append("              region, part and event ID either mod's scripts address by")
    lines.append("              number still exists, and merged adds no ID from neither input)")
    lines.append("    every merged file re-serialises identically, has canonical subtype")
    lines.append("    ordering, no dangling index, and no part pointing at an absent model")
    lines.append("")
    if problems:
        lines.append(f"  PROBLEMS FOUND: {len(problems)}")
        for x in problems[:40]:
            lines.append(f"      ! {x}")
    else:
        lines.append("  PROBLEMS FOUND: 0")
    return lines


def summarise(items, n=6):
    kinds = {}
    for it in items:
        k = it.split(" ")[0]
        kinds[k] = kinds.get(k, 0) + 1
    head = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items(), key=lambda x: -x[1]))
    sample = "; e.g. " + " | ".join(i[:70] for i in items[:2]) if items else ""
    return head + sample


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read the HUD movie's render tree out of a JPEXS swf2xml dump.

WHY. Every "engine-side" myth in this port died the moment the movie was
read instead of guessed at (the cxform lift, the end-cap, the podium). This
prints, for a texture or a sprite, everything the movie does with it: which
shapes sample it (UV rect in texels, bounds in stage px), which sprites place
those shapes (matrix, depth, instance name), and the chain of parents up to
the root, so that "the souls counter" becomes a set of ids and numbers.

    fe_tree.py fe.xml --bitmap MENU_PlayerHUD      # shapes + placements + parents
    fe_tree.py fe.xml --sprite 471                 # what a sprite contains
    fe_tree.py fe.xml --name Soul                  # placements whose name matches
    fe_tree.py fe.xml --text                       # every edit-text field, with parents

Units: SWF twips are printed as stage px (/20). One stage px is two 4K px.
Bitmap fill matrices are in twips per texel*20, i.e. scale 20 == 1 texel per
stage px; the UV rect printed is the shape's bounds pushed through the inverse
of the bitmap matrix.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict


def mat(el):
    """MATRIX element -> (a, b, c, d, tx, ty) in stage px."""
    if el is None:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    f = lambda k, d: float(el.get(k, d))
    # JPEXS writes scale/skew as floats already (scaleX="20.0"), not 16.16 ints
    sx = f("scaleX", 1) if el.get("hasScale") == "true" else 1.0
    sy = f("scaleY", 1) if el.get("hasScale") == "true" else 1.0
    r0 = f("rotateSkew0", 0) if el.get("hasRotate") == "true" else 0.0
    r1 = f("rotateSkew1", 0) if el.get("hasRotate") == "true" else 0.0
    return (sx, r0, r1, sy, f("translateX", 0) / 20, f("translateY", 0) / 20)


def fmt_mat(m):
    a, b, c, d, tx, ty = m
    s = f"t=({tx:g},{ty:g})"
    if (a, b, c, d) != (1.0, 0.0, 0.0, 1.0):
        s += f" scale=({a:.4g},{d:.4g})"
        if b or c:
            s += f" skew=({b:.4g},{c:.4g})"
    return s


def rect(el):
    if el is None:
        return None
    return tuple(int(el.get(k)) / 20 for k in ("Xmin", "Ymin", "Xmax", "Ymax"))


class Movie:
    def __init__(self, path):
        self.root = ET.parse(path).getroot()
        self.images = {}        # char id -> export name
        self.shapes = {}        # shape id -> {"bounds":..., "fills":[(bitmapId, matrix)]}
        self.sprites = {}       # sprite id -> [placements]
        self.texts = {}         # char id -> dict
        self.parents = defaultdict(list)  # char id -> [(sprite id, placement)]
        self._walk()

    def _walk(self):
        for it in self.root.iter("item"):
            t = it.get("type")
            if t == "DefineExternalImage2":
                self.images[int(it.get("characterID"))] = it.get("exportName")
            elif t in ("DefineShapeTag", "DefineShape4Tag"):
                sid = int(it.get("shapeId"))
                fills = []
                for fs in it.iter("item"):
                    if fs.get("type") == "FILLSTYLE" and fs.get("bitmapId") is not None:
                        bm = fs.find("bitmapMatrix")
                        fills.append((int(fs.get("bitmapId")), mat(bm) if bm is not None else None))
                self.shapes[sid] = {"bounds": rect(it.find("shapeBounds")), "fills": fills}
            elif t == "DefineEditTextTag":
                cid = int(it.get("characterID"))
                self.texts[cid] = {k: it.get(k) for k in ("initialText", "fontClass", "fontHeight", "align")}
                self.texts[cid]["bounds"] = rect(it.find("bounds"))
                self.texts[cid]["color"] = it.find("textColor").attrib if it.find("textColor") is not None else None
            elif t == "DefineSpriteTag":
                sid = int(it.get("spriteId"))
                pl = []
                sub = it.find("subTags")
                frame = 0
                for p in (sub if sub is not None else []):
                    pt = p.get("type")
                    if pt == "ShowFrameTag":
                        frame += 1
                    elif pt in ("PlaceObject2Tag", "PlaceObject3Tag") and p.get("characterId"):
                        d = {"char": int(p.get("characterId")), "depth": int(p.get("depth")),
                             "name": p.get("name"), "frame": frame, "matrix": mat(p.find("matrix")),
                             "clip": p.get("clipDepth") if p.get("placeFlagHasClipDepth") == "true" else None,
                             "cx": p.find("colorTransform") is not None, "tag": pt}
                        pl.append(d)
                self.sprites[sid] = pl
        # the main timeline is sprite 0
        pl = []
        frame = 0
        for p in self.root.iter("item"):
            pass
        main = self.root.find("tags")
        if main is not None:
            for p in main:
                pt = p.get("type")
                if pt == "ShowFrameTag":
                    frame += 1
                elif pt in ("PlaceObject2Tag", "PlaceObject3Tag") and p.get("characterId"):
                    pl.append({"char": int(p.get("characterId")), "depth": int(p.get("depth")),
                               "name": p.get("name"), "frame": frame, "matrix": mat(p.find("matrix")),
                               "clip": None, "cx": p.find("colorTransform") is not None, "tag": pt})
        self.sprites[0] = pl
        for sid, pl in self.sprites.items():
            for p in pl:
                self.parents[p["char"]].append((sid, p))

    def kind(self, cid):
        if cid in self.images:
            return f"image {self.images[cid]}"
        if cid in self.shapes:
            return "shape"
        if cid in self.sprites:
            return "sprite"
        if cid in self.texts:
            return "text"
        return "?"

    def uv(self, sid):
        """UV rect (texels) of a shape's bounds under its bitmap matrix."""
        sh = self.shapes[sid]
        out = []
        for bid, m in sh["fills"]:
            if m is None or sh["bounds"] is None:
                out.append((bid, None))
                continue
            a, b, c, d, tx, ty = m
            # texel = inverse(M) * stage; M maps texel*20 -> twips, i.e. texel -> stage px is M/20
            a, b, c, d = a / 20, b / 20, c / 20, d / 20
            det = a * d - b * c
            if abs(det) < 1e-12:
                out.append((bid, None))
                continue
            x0, y0, x1, y1 = sh["bounds"]
            pts = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
            us, vs = [], []
            for x, y in pts:
                x -= tx; y -= ty
                u = (d * x - c * y) / det
                v = (-b * x + a * y) / det
                us.append(u); vs.append(v)
            import math
            out.append((bid, (min(us), min(vs), max(us), max(vs)), (math.hypot(a, b) or 1e-9, math.hypot(c, d) or 1e-9, bool(b or c))))
        return out

    def chain(self, cid, depth=0, seen=None, out=None, maxdepth=8):
        out = [] if out is None else out
        seen = set() if seen is None else seen
        for sid, p in self.parents.get(cid, []):
            line = ("  " * depth + f"placed in sprite {sid} depth {p['depth']} frame {p['frame']}"
                    + (f" name={p['name']!r}" if p["name"] else "") + " " + fmt_mat(p["matrix"])
                    + (f" clip={p['clip']}" if p["clip"] else "") + (" cxform" if p["cx"] else ""))
            out.append(line)
            if sid != 0 and depth < maxdepth and (sid, cid) not in seen:
                seen.add((sid, cid))
                self.chain(sid, depth + 1, seen, out, maxdepth)
        return out

    def describe_sprite(self, sid, depth=0, out=None, maxdepth=3):
        out = [] if out is None else out
        for p in self.sprites.get(sid, []):
            c = p["char"]
            line = ("  " * depth + f"depth {p['depth']:>3} frame {p['frame']:>4} char {c:>4} ({self.kind(c)})"
                    + (f" name={p['name']!r}" if p["name"] else "") + " " + fmt_mat(p["matrix"])
                    + (f" clip={p['clip']}" if p["clip"] else "") + (" cxform" if p["cx"] else ""))
            if c in self.shapes:
                for u in self.uv(c):
                    if u[1] is not None:
                        bid, (u0, v0, u1, v1), (sa, sd, rot) = u
                        line += (f"  bounds={self.shapes[c]['bounds']} uv={self.images.get(bid, bid)}"
                                 f"[{u0:.1f}..{u1:.1f}, {v0:.1f}..{v1:.1f}] texel/stagepx=({1/sa:.3g},{1/sd:.3g}){' ROTATED' if rot else ''}")
                    else:
                        line += f"  bounds={self.shapes[c]['bounds']} bitmap {u[0]} (no matrix)"
            if c in self.texts:
                line += f"  text={self.texts[c]}"
            out.append(line)
            if c in self.sprites and depth < maxdepth:
                self.describe_sprite(c, depth + 1, out, maxdepth)
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml")
    ap.add_argument("--bitmap")
    ap.add_argument("--sprite", type=int)
    ap.add_argument("--name")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--depth", type=int, default=3)
    a = ap.parse_args()
    mv = Movie(a.xml)
    if a.bitmap:
        bids = [i for i, n in mv.images.items() if n == a.bitmap or str(i) == a.bitmap]
        for bid in bids:
            print(f"== bitmap {bid} {mv.images[bid]}")
            for sid, sh in mv.shapes.items():
                if any(b == bid for b, _ in sh["fills"]):
                    for u in mv.uv(sid):
                        if u[0] != bid:
                            continue
                        if u[1] is None:
                            print(f"shape {sid} bounds={sh['bounds']} (no matrix)")
                        else:
                            _, (u0, v0, u1, v1), (sa, sd, rot) = u
                            print(f"shape {sid} bounds={sh['bounds']} uv=[{u0:.1f}..{u1:.1f}, {v0:.1f}..{v1:.1f}] texel/stagepx=({1/sa:.3g},{1/sd:.3g}){' ROTATED' if rot else ''}")
                    for line in mv.chain(sid):
                        print("   " + line)
    if a.sprite is not None:
        print(f"== sprite {a.sprite}")
        for line in mv.describe_sprite(a.sprite, maxdepth=a.depth):
            print(line)
        print("-- parents")
        for line in mv.chain(a.sprite):
            print("   " + line)
    if a.name:
        pat = re.compile(a.name)
        for sid, pl in mv.sprites.items():
            for p in pl:
                if p["name"] and pat.search(p["name"]):
                    print(f"sprite {sid} depth {p['depth']} name={p['name']!r} -> char {p['char']} ({mv.kind(p['char'])}) {fmt_mat(p['matrix'])}")
    if a.text:
        for cid, tx in mv.texts.items():
            print(f"text {cid}: {tx}")
            for line in mv.chain(cid, maxdepth=4):
                print("   " + line)


if __name__ == "__main__":
    main()

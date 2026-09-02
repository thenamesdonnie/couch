"""DIRDASH v7.

Field comparison showed the ONLY functional difference between DashStart's forward
CMSG and a run strafe CMSG is animeEndEventType (0 FireNextStateEvent vs 2
FireIdleEvent). That is why v5 never advanced DashStart -> Dash. Dash's and
DashEnd's forward CMSGs match the strafes on that field already.

So: one shared set of 87 sped-up clip clones, two sets of CMSG clones (DashStart
with animeEndEventType 0, Dash with 2), stock RunEnd strafes for DashEnd, and every
new clip named in the exact stock form with a fresh _AutoSet_NN index so the file
keeps its zero-duplicate-names invariant.
"""
import re, sys, collections, hashlib
from pf import Packfile
from append_hkx import Appender

SRC = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
OUT = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash7.hkx'
RATIO = (4.3188 / 0.6666666865348816) / (2.776 / 0.7333333)
SZ_CLIP, SZ_CMSG, SZ_MSG, SZ_VBS = 352, 256, 216, 48

pf = Packfile(SRC); cls = dict(pf.items)
def nm(o):
    try: return pf.cstr(o + 56) or ''
    except Exception: return ''
def find(c, n):
    r = [o for o, cc in pf.items if cc == c and nm(o) == n]
    assert len(r) == 1, (c, n, len(r)); return r[0]
def states_of(sm):
    p, n = pf.array(sm + 208)
    return {pf.cstr(pf.ptr(p + i*8) + 96): pf.ptr(p + i*8) for i in range(n)}
UPPER = states_of(find('hkbStateMachine', 'Move StateMachine'))
LOWER = states_of(find('hkbStateMachine', 'Move StateMachine_mirror'))
RUNSEL = find('hkbManualSelectorGenerator', 'Run Normal Light Direction ManualSelectorGenerator')
RUNVBS = pf.ptr(RUNSEL + 16); RUNTE = pf.ptr(RUNSEL + 176)

# every name in the stock file, and the AutoSet indices already used per animationName
ALLNAMES = set()
used = collections.defaultdict(set)
PAT = re.compile(r'^(.*)_hkx_AutoSet_(\d+)$')
for o, c in pf.items:
    n = nm(o)
    if n: ALLNAMES.add(n)
    if c == 'hkbClipGenerator':
        m = PAT.match(n or '')
        if m: used[m.group(1)].add(int(m.group(2)))
def fresh_clip_name(anim):
    i = 0
    while i in used[anim] or ('%s_hkx_AutoSet_%02d' % (anim, i)) in ALLNAMES:
        i += 1
    used[anim].add(i)
    nn = '%s_hkx_AutoSet_%02d' % (anim, i)
    ALLNAMES.add(nn); return nn
def fresh(name):
    assert name not in ALLNAMES, name
    ALLNAMES.add(name); return name

A = Appender(SRC)

def clone_clip(src_off):
    assert pf.ptr(src_off + 152) is None
    anim = pf.cstr(src_off + 144)
    o = A.add_object('hkbClipGenerator', SZ_CLIP, pf.data[src_off:src_off + SZ_CLIP])
    A.add_local(o + 56,  A.add_string(fresh_clip_name(anim)))
    A.add_local(o + 144, A.add_string(anim))
    A.f32(o + 176, RATIO)
    return o

def clone_cmsg(src_off, new_name, kids, anime_end=None):
    o = A.add_object('CustomManualSelectorGenerator', SZ_CMSG, pf.data[src_off:src_off + SZ_CMSG])
    A.add_local(o + 56, A.add_string(fresh(new_name)))
    arr = A.set_array(o, 136, 8, len(kids))
    for i, k in enumerate(kids):
        A.add_global(arr + i*8, k)
    te = pf.ptr(src_off + 168)
    if te is not None:
        A.add_global(o + 168, te)
    if anime_end is not None:
        A.s32(o + 160, anime_end)
    return o

def make_selector(label, children):
    vbs = A.add_object('hkbVariableBindingSet', SZ_VBS, pf.data[RUNVBS:RUNVBS + SZ_VBS])
    bp, bn = pf.array(RUNVBS + 16)
    barr = A.set_array(vbs, 16, 40, bn)
    for i in range(bn):
        A.data[barr + i*40:barr + (i+1)*40] = pf.data[bp + i*40:bp + (i+1)*40]
        A.add_local(barr + i*40, A.add_string(pf.cstr(bp + i*40)))
    sel = A.add_object('hkbManualSelectorGenerator', SZ_MSG, pf.data[RUNSEL:RUNSEL + SZ_MSG])
    A.add_global(sel + 16, vbs)
    A.add_local(sel + 56, A.add_string(fresh(label + ' Direction ManualSelectorGenerator')))
    A.add_global(sel + 176, RUNTE)
    arr = A.set_array(sel, 136, 8, len(children))
    for i, c in enumerate(children):
        A.add_global(arr + i*8, c)
    return sel

print("RATIO %.6f" % RATIO)
STRAFE = {d: find('CustomManualSelectorGenerator', 'Run%s Normal Light' % d) for d in ('Back', 'Left', 'Right')}
CLIPS = {}
for d, src in STRAFE.items():
    p, n = pf.array(src + 136)
    CLIPS[d] = [clone_clip(pf.ptr(p + i*8)) for i in range(n)]
    print("  %-5s cloned %d clips at speed %.6f (from %s, animId %d)" % (d, n, RATIO, nm(src), pf.s32(src + 156)))

DS = {d: clone_cmsg(STRAFE[d], 'Run%s Normal Light DashStart' % d, CLIPS[d], anime_end=0) for d in ('Back','Left','Right')}
DA = {d: clone_cmsg(STRAFE[d], 'Run%s Normal Light Dash' % d,      CLIPS[d], anime_end=None) for d in ('Back','Left','Right')}
print("  DashStart strafe CMSGs %s  animeEndEventType -> 0 (FireNextStateEvent)" % {d: hex(v) for d, v in DS.items()})
print("  Dash      strafe CMSGs %s  animeEndEventType kept 2 (FireIdleEvent)" % {d: hex(v) for d, v in DA.items()})

PLAN = [
    ('DashStart', 'DashStart', 'DashStart_mirror', 'DashStart CustomManualSelectorGenerator', DS),
    ('Dash',      'Dash',      'Dash_mirror',      'Dash CustomManualSelectorGenerator',      DA),
    ('DashEnd',   'DashEnd',   'DashEnd_mirror',   'DashEnd CustomManualSelectorGenerator',
        {d: find('CustomManualSelectorGenerator', 'RunEnd %s CustomManualSelectorGenerator' % d) for d in ('Back','Left','Right')}),
]
for label, up, lo, fwd_name, m in PLAN:
    sel = make_selector(label, [find('CustomManualSelectorGenerator', fwd_name), m['Back'], m['Left'], m['Right']])
    for layer, sname, table in (('Upper', up, UPPER), ('Lower', lo, LOWER)):
        old = A.retarget_global(table[sname] + 88, sel)
        print("     %-5s %-18s generator %#x -> %#x" % (layer, sname, old, sel))

out = A.build(); open(OUT, 'wb').write(out)
orig = open(SRC, 'rb').read()
print("\nwrote %s  %d bytes  sha256 %s" % (OUT, len(out), hashlib.sha256(out).hexdigest()[:16]))
print("stock data region preserved verbatim:", out[A.dabs:A.dabs + pf.dloc] == orig[A.dabs:A.dabs + pf.dloc])

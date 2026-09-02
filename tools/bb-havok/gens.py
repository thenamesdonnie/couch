from graph import *
def binds(o):
    vbs = pf.ptr(o+16)
    if vbs is None or cls.get(vbs)!='hkbVariableBindingSet': return []
    return [(mp, var(vi), bi, bt) for mp,vi,bi,bt in bindings(vbs)]
def clipinfo(o):
    return dict(name=pf.cstr(o+56), anim=pf.cstr(o+144), bind=binds(o),
                playbackSpeed=pf.f32(o+176), mode=pf.u8(o+190) if True else None)
def walk(o, depth=0, seen=None, maxdepth=4):
    if seen is None: seen=set()
    pad='  '*depth
    c = cls.get(o)
    if c is None: print(pad+"<null/unknown %s>"%(hex(o) if o else 'NULL')); return
    nm = pf.cstr(o+56)
    b = binds(o)
    bstr = ('  bind:'+','.join("%s<-%s"%(m,v) for m,v,_,_ in b)) if b else ''
    if c=='hkbClipGenerator':
        print("%s%s '%s' anim=%s%s"%(pad,c,nm,pf.cstr(o+144),bstr)); return
    print("%s%s '%s'%s"%(pad,c,nm,bstr))
    if o in seen or depth>=maxdepth:
        if o in seen: print(pad+"  (already shown)")
        return
    seen.add(o)
    if c in ('hkbManualSelectorGenerator','CustomManualSelectorGenerator'):
        p,n = pf.array(o+136)
        print("%s  generators[%d] selectedGeneratorIndex=%d"%(pad,n,pf.s16(o+152)))
        for i in range(n):
            g=pf.ptr(p+i*8)
            print("%s   [%d]"%(pad,i), end=' ')
            if g is None: print("NULL"); continue
            print()
            walk(g, depth+2, seen, maxdepth)
    elif c=='hkbBlenderGenerator':
        p,n = pf.array(o+160)
        print("%s  children[%d] blendParameter=%.3f"%(pad,n,pf.f32(o+140)))
        for i in range(n):
            ch=pf.ptr(p+i*8)
            if ch is None: continue
            cb=binds(ch)
            print("%s   child[%d] weight=%.3f%s"%(pad,i,pf.f32(ch+64), ('  bind:'+','.join("%s<-%s"%(m,v) for m,v,_,_ in cb)) if cb else ''))
            g=pf.ptr(ch+48)
            if g: walk(g, depth+2, seen, maxdepth)
    elif c=='hkbModifierGenerator':
        g=pf.ptr(o+144)
        if g: walk(g,depth+1,seen,maxdepth)
    elif c=='hkbStateMachine':
        print("%s  (nested state machine)"%pad)
import sys
for label,off in [('Walk',0x17d480),('Run',0x18a9f0),('DashStart',0x19b140),('Dash',0x19cfe0),('DashEnd',0x19e9a0),('RunEnd',0x1a0360),('WalkEnd',0x177600)]:
    print("\n########## %s ##########"%label)
    walk(off)

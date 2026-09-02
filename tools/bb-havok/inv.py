from graph import *
def clips(o, acc=None, depth=0):
    if acc is None: acc=[]
    c=cls.get(o)
    if c=='hkbClipGenerator': acc.append(pf.cstr(o+144)); return acc
    if c in ('hkbManualSelectorGenerator','CustomManualSelectorGenerator'):
        p,n=pf.array(o+136)
        for i in range(n):
            g=pf.ptr(p+i*8)
            if g: clips(g,acc,depth+1)
    elif c=='hkbBlenderGenerator':
        p,n=pf.array(o+160)
        for i in range(n):
            ch=pf.ptr(p+i*8)
            if ch: 
                g=pf.ptr(ch+48)
                if g: clips(g,acc,depth+1)
    elif c=='hkbModifierGenerator':
        g=pf.ptr(o+144)
        if g: clips(g,acc,depth+1)
    return acc
def ids(o):
    import re, collections
    s=set()
    for a in clips(o):
        m=re.match(r'a(\d+)_(\d+)',a or '')
        if m: s.add(m.group(2))
    return sorted(s)
def sub(o,i):
    p,n=pf.array(o+136); return pf.ptr(p+i*8)
DIR=['Front(0)','Back(1)','Left(2)','Right(3)']
for label,root in [('Walk',0x17d480),('Run',0x18a9f0),('RunEnd',0x1a0360),('WalkEnd',0x177600)]:
    print("\n### %s"%label)
    r=root
    if pf.cstr(r+56) and 'UpperCondition' in str([b[1] for b in ( [(m,var(vi),bi,bt) for m,vi,bi,bt in bindings(pf.ptr(r+16))] if pf.ptr(r+16) and cls.get(pf.ptr(r+16))=='hkbVariableBindingSet' else [] )]):
        r=sub(root,0)  # Normal branch
    print("  dir selector: '%s'"%pf.cstr(r+56))
    for i in range(4):
        g=sub(r,i)
        if g is None: print("   %-9s NULL"%DIR[i]); continue
        print("   %-9s '%-40s' animIDs=%s"%(DIR[i],pf.cstr(g+56),','.join(ids(g))))
for label,root in [('DashStart',0x19b140),('Dash',0x19cfe0),('DashEnd',0x19e9a0)]:
    print("\n### %s  '%s'  (no direction selector)  animIDs=%s"%(label,pf.cstr(root+56),','.join(ids(root))))

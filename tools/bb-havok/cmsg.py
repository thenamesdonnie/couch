from graph import *
OT={0:'OffsetNone',11:'IdleCategory',13:'WeaponCategoryRight',14:'WeaponCategoryLeft'}
def show(label,o):
    print("%-34s offsetType=%-20s animId=%-7d enableScript=%d enableTae=%d  '%s'" % (
        label, OT.get(pf.s32(o+152),str(pf.s32(o+152))), pf.s32(o+156),
        pf.u8(o+164), pf.u8(o+165), pf.cstr(o+56)))
def sub(o,i):
    p,n=pf.array(o+136); return pf.ptr(p+i*8)
print("\n-- Dash chain (no direction selector) --")
for lbl,off in [('DashStart',0x19b140),('Dash',0x19cfe0),('DashEnd',0x19e9a0)]: show(lbl,off)
print("\n-- Run, per direction --")
rdir = sub(0x18a9f0,0)
for i,d in enumerate(['Front','Back','Left','Right']):
    g=sub(rdir,i)
    if cls.get(g)=='CustomManualSelectorGenerator': show('Run '+d,g)
    else:
        for j in range(pf.array(g+136)[1]):
            show('Run %s [%d]'%(d,j), sub(g,j))
print("\n-- Walk, per direction --")
wdir = sub(0x17d480,0)
for i,d in enumerate(['Front','Back','Left','Right']): show('Walk '+d, sub(wdir,i))

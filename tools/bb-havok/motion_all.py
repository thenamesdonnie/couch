import glob, math, re, collections
from soulstruct.havok.core import HKX
rows=collections.defaultdict(list)
for p in sorted(glob.glob('/home/ds2000/couch/data/bb-hks/anibnd/anim/*.hkx')):
    n=p.split('/')[-1]; m=re.match(r'a(\d+)_(\d+)\.hkx',n)
    try:
        h=HKX.from_path(p); a=h.root.namedVariants[0].variant.animations[0]
        em=a.extractedMotion; rfs=em.referenceFrameSamples
        f=list(rfs[0]); l=list(rfs[-1])
        dist=math.hypot(float(l[0])-float(f[0]), float(l[2])-float(f[2]))
        dur=float(a.duration)
        rows[m.group(2)].append((m.group(1), dist, dur, dist/dur if dur else 0,
                                 round(float(l[0])-float(f[0]),3), round(float(l[2])-float(f[2]),3)))
    except Exception as e:
        rows[m.group(2)].append((m.group(1), None, None, None, None, str(e)[:40]))
LBL={'005000':'Dash (fwd loop)','005200':'DashStart','006700':'DashEnd','004000':'RunFront',
     '004001':'RunBack','004002':'RunLeft','004003':'RunRight','003002':'WalkLeft'}
print("%-9s %-16s %6s %7s %7s %9s  %s"%("animId","what","n","meanDur","meanDist","units/s","per-set units/s"))
speeds={}
for k in sorted(rows):
    good=[r for r in rows[k] if r[3]]
    if not good: print(k,"unreadable"); continue
    sp=[r[3] for r in good]
    speeds[k]=sum(sp)/len(sp)
    print("%-9s %-16s %6d %7.3f %8.3f %9.3f  min %.2f max %.2f"%(
        k,LBL.get(k,''),len(good),sum(r[2] for r in good)/len(good),
        sum(r[1] for r in good)/len(good),speeds[k],min(sp),max(sp)))
print()
for tgt in ('004001','004002','004003'):
    if tgt in speeds and '005000' in speeds:
        print("ratio Dash(005000)/%s = %.4f"%(tgt, speeds['005000']/speeds[tgt]))
print("ratio Dash/RunFront = %.4f"%(speeds['005000']/speeds['004000']))

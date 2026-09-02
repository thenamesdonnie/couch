import sys, math
from soulstruct.havok.core import HKX
def info(p):
    h=HKX.from_path(p)
    ac=h.root.namedVariants[0].variant
    a=ac.animations[0]
    em=getattr(a,'extractedMotion',None)
    d=dict(cls=type(a).__name__, duration=getattr(a,'duration',None),
           nframes=getattr(a,'numFrames',None), em=type(em).__name__ if em else None)
    if em is not None:
        rfs=getattr(em,'referenceFrameSamples',None)
        d['nsamples']=len(rfs) if rfs is not None else None
        d['em_duration']=getattr(em,'duration',None)
        if rfs is not None and len(rfs):
            f=list(rfs[0]); l=list(rfs[-1])
            d['first']=[round(x,4) for x in f]; d['last']=[round(x,4) for x in l]
            dx,dy,dz=l[0]-f[0],l[1]-f[1],l[2]-f[2]
            d['delta']=[round(dx,4),round(dy,4),round(dz,4)]
            d['dist']=round(math.hypot(dx,dz),4)
    return d
for p in sys.argv[1:]:
    print(p.split('/')[-1], info(p))

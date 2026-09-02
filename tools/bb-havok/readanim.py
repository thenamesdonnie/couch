import sys
from soulstruct.havok.core import HKX
p=sys.argv[1]
h=HKX.from_path(p)
print("root:",type(h.root).__name__)
def walk(o,d=0,seen=None):
    if seen is None: seen=set()
    if id(o) in seen or d>4: return
    seen.add(id(o))
    print("  "*d+type(o).__name__)
    for f in getattr(o,'__annotations__',{}) or []:
        try: v=getattr(o,f)
        except Exception: continue
        if hasattr(v,'__annotations__'): print("  "*(d+1)+f+":"); walk(v,d+2,seen)
        elif isinstance(v,list) and v and hasattr(v[0],'__annotations__'):
            print("  "*(d+1)+f+f"[{len(v)}]:"); walk(v[0],d+2,seen)
        else:
            s=repr(v)
            print("  "*(d+1)+f+" = "+(s[:90]+"..." if len(s)>90 else s))
walk(h.root)

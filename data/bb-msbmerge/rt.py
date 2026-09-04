import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soulstruct.dcx import decompress
from msbb import MSB
V=sys.argv[1]
ok=True
for p in sorted(glob.glob(V+'/*.msb.dcx')):
    n=os.path.basename(p)
    try:
        raw,t=decompress(open(p,'rb').read())
        m=MSB.from_bytes(raw)
        m.order_check()
        out,lost=m.to_bytes()
        same = out==raw
        ok &= same
        print(f"{n} dcx={t} {len(raw)}B identical={same} lost={len(lost)}")
        if not same:
            for i in range(min(len(out),len(raw))):
                if out[i]!=raw[i]:
                    print('   first diff at 0x%X'%i); break
            print('   len',len(out),len(raw))
    except Exception as ex:
        ok=False
        import traceback; traceback.print_exc()
        print(f"{n} FAILED {ex}")
print("ALL IDENTICAL" if ok else "FAILURES")

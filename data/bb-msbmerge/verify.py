"""Independent check that merged = REBORNE + (ENHANCED - VANILLA)."""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soulstruct.dcx import decompress
from msbb import MSB, SUPERTYPES, PARTS, POINT
from mergemsb import load, norm_fields, index_by_key
V='/home/ds2000/couch/data/bb-mod-backups-copy/BloodborneEnhanced-0.11.2-fix9/files/map/mapstudio'
E='/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/map/mapstudio'
R=sys.argv[1]; M=sys.argv[2]
bad=0; tot={'eadd':0,'emod':0,'rkeep':0,'edel':0}
for p in sorted(glob.glob(M+'/*.msb.dcx')):
    n=os.path.basename(p)[:-8]
    v,_,_=load(f'{V}/{n}.msb.dcx'); e,_,_=load(f'{E}/{n}.msb.dcx')
    r,_,_=load(f'{R}/{n}.msb.dcx'); m,_,_=load(p)
    vi,ei,ri,mi=index_by_key(v),index_by_key(e),index_by_key(r),index_by_key(m)
    for st in SUPERTYPES:
        # 1. everything Enhanced ADDED must be in merged, field-identical
        for k,ee in ei[st].items():
            if k in vi[st]: continue
            me=mi[st].get(k)
            if me is None:
                print('MISSING ENHANCED ADD', n, st, ee.name); bad+=1; continue
            tot['eadd']+=1
            if norm_fields(me)!=norm_fields(ee):
                d=[x for x in set(norm_fields(me))|set(norm_fields(ee))
                   if norm_fields(me).get(x,'<a>')!=norm_fields(ee).get(x,'<a>')]
                print('ENHANCED ADD ALTERED', n, st, ee.name, d); bad+=1
        # 2. everything Enhanced DELETED must be gone
        for k,ve in vi[st].items():
            if k in ei[st] or k not in ri[st]: continue
            tot['edel']+=1
            if k in mi[st]:
                print('ENHANCED DELETE NOT APPLIED', n, st, ve.name); bad+=1
        # 3. Reborne entries survive with Reborne's values, except where
        #    Enhanced modified them (then Enhanced's values, since no overlap)
        for k,re_ in ri[st].items():
            if k in vi[st] and k not in ei[st]: continue   # enhanced deleted
            me=mi[st].get(k)
            if me is None:
                print('LOST REBORNE ENTRY', n, st, re_.name); bad+=1; continue
            ve, ee = vi[st].get(k), ei[st].get(k)
            expect = re_
            if ve is not None and ee is not None and norm_fields(ee)!=norm_fields(ve):
                expect = ee; tot['emod']+=1
            else:
                tot['rkeep']+=1
            if norm_fields(me)!=norm_fields(expect):
                d=[x for x in set(norm_fields(me))|set(norm_fields(expect))
                   if norm_fields(me).get(x,'<a>')!=norm_fields(expect).get(x,'<a>')]
                print('WRONG VALUES', n, st, re_.name, d[:6]); bad+=1
    # 4. no dangling indices, and ordering is canonical
    m.order_check()
    _,lost=m.to_bytes()
    if lost: print('DANGLING', n, lost[:3]); bad+=1
    # 5. every part's model resolves
    have={x.key for x in m.lists['MODEL_PARAM_ST']}
    for pt in m.lists[PARTS]:
        mn=pt.refs['model'][1]
        if mn is not None and mn not in have:
            print('MODEL MISSING', n, pt.name, mn); bad+=1
print()
print('checks:', tot)
print('PROBLEMS:', bad)

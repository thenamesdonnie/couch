import sys, os, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soulstruct.dcx import decompress
from msbb import MSB, SUPERTYPES, PARTS, POINT, EVENT, MODEL
from mergemsb import load, norm_fields, index_by_key
V='/home/ds2000/couch/data/bb-mod-backups-copy/BloodborneEnhanced-0.11.2-fix9/files/map/mapstudio'
E='/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/map/mapstudio'
R=sys.argv[1]
overlap=0
fieldhits=collections.Counter()
for p in sorted(glob.glob(R+'/*.msb.dcx')):
    n=os.path.basename(p)[:-8]
    v,_,_=load(f'{V}/{n}.msb.dcx'); e,_,_=load(f'{E}/{n}.msb.dcx'); r,_,_=load(p)
    vi,ei,ri=index_by_key(v),index_by_key(e),index_by_key(r)
    for st in SUPERTYPES:
        for k,ve in vi[st].items():
            ee,re_=ei[st].get(k),ri[st].get(k)
            if ee is None or re_ is None: continue
            fv,fe,fr=norm_fields(ve),norm_fields(ee),norm_fields(re_)
            et = {kk for kk in set(fv)|set(fe) if fv.get(kk,'<a>')!=fe.get(kk,'<a>')}
            rt = {kk for kk in set(fv)|set(fr) if fv.get(kk,'<a>')!=fr.get(kk,'<a>')}
            for kk in rt: fieldhits[f'{st.split("_")[0]}/{kk}']+=1
            if et and rt:
                overlap+=1
                print('BOTH TOUCHED', n, st, ve.name, 'E:',sorted(et),'R:',sorted(rt))
print('entries touched by both:',overlap)
print()
for k,c in fieldhits.most_common(25): print(f'{c:8d} {k}')

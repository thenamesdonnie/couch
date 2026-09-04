import sys, os, glob, re, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mergemsb import load
from msbb import SUPERTYPES
V='/home/ds2000/couch/data/bb-mod-backups-copy/BloodborneEnhanced-0.11.2-fix9/files/map/mapstudio'
E='/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/map/mapstudio'
R=sys.argv[1]
strip=lambda s: re.sub(r' \{\d+\}$','',s)
issues=0
for p in sorted(glob.glob(R+'/*.msb.dcx')):
    n=os.path.basename(p)[:-8]
    ms={t:load(f'{d}/{n}.msb.dcx')[0] for t,d in (('V',V),('E',E),('R',R))}
    for st in SUPERTYPES:
        c={t:collections.Counter(strip(x.name) for x in m.lists[st]) for t,m in ms.items()}
        dups={t:{k for k,v in cc.items() if v>1} for t,cc in c.items()}
        # a name that is duplicated in one version but with a DIFFERENT count elsewhere
        for k in dups['V']|dups['E']|dups['R']:
            if not (c['V'][k]==c['E'][k]==c['R'][k]):
                print('DUP COUNT MISMATCH', n, st, repr(k), {t:c[t][k] for t in c}); issues+=1
print('duplicate-name hazards:', issues)

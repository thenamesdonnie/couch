import re,sys
lines=open('/home/ds2000/couch/data/bb-hks/c0000.list.named.txt',encoding='utf-8').read().split('\n')
hdr=[]
for i,l in enumerate(lines):
    if l.startswith('function <') or l.startswith('main <'):
        m=re.match(r'(?:function|main) <:([^:]*):',l)
        hdr.append((i,m.group(1) if m else '?'))
def owner(ln):
    lo,hi=0,len(hdr)-1; best='?'
    for i,n in hdr:
        if i<=ln: best=n
        else: break
    return best
pat=sys.argv[1]
counts={}
for i,l in enumerate(lines):
    if re.search(pat,l):
        o=owner(i)
        counts.setdefault(o,[]).append((i+1,l.strip()))
for o,v in counts.items():
    print("### %s  (%d hits)"%(o,len(v)))
    for ln,t in v[:int(sys.argv[2]) if len(sys.argv)>2 else 4]:
        print("   %d: %s"%(ln,t[:120]))

import struct, collections

class Packfile:
    def __init__(self, path):
        d = open(path,'rb').read()
        self.d = d
        self.nsec = struct.unpack_from('<i', d, 20)[0]
        self.sections = {}
        self.seclist = []
        for i in range(self.nsec):
            o = 64 + i*0x40
            name = d[o:o+19].rstrip(b'\0').decode()
            vals = struct.unpack_from('<7I', d, o+20)
            self.sections[name] = vals
            self.seclist.append((name,)+vals)
        # classnames
        cn_abs, cn_loc = self.sections['__classnames__'][0], self.sections['__classnames__'][1]
        sec = d[cn_abs:cn_abs+cn_loc]
        self.classnames = {}   # offset in section -> name
        i = 0
        while i < len(sec)-5:
            if sec[i:i+4] == b'\xff\xff\xff\xff': break
            sig = struct.unpack_from('<I', sec, i)[0]
            j = sec.index(b'\0', i+5)
            self.classnames[i+5] = (sec[i+5:j].decode(), sig)
            i = j+1
        # data section
        (self.dabs, self.dloc, self.dglob, self.dvirt, self.dexp, self.dimp, self.dend) = self.sections['__data__']
        self.data = d[self.dabs:self.dabs+self.dloc]
        # local fixups: src -> dst (both within data section)
        self.local = {}
        for o in range(self.dabs+self.dloc, self.dabs+self.dglob, 8):
            s,t = struct.unpack_from('<II', d, o)
            if s == 0xffffffff: continue
            self.local[s] = t
        # global fixups: src -> (section, offset)
        self.glob = {}
        for o in range(self.dabs+self.dglob, self.dabs+self.dvirt, 12):
            s,si,t = struct.unpack_from('<III', d, o)
            if s == 0xffffffff: continue
            self.glob[s] = (si,t)
        # virtual fixups: item offset -> class name
        self.virt = {}
        for o in range(self.dabs+self.dvirt, min(self.dabs+self.dexp, len(d)-11), 12):
            s,si,noff = struct.unpack_from('<III', d, o)
            if s == 0xffffffff: continue
            if noff not in self.classnames: continue
            self.virt[s] = self.classnames[noff][0]
        self.items = sorted(self.virt.items())

    # ---- readers, offsets relative to data section ----
    def u8(self,o):  return self.data[o]
    def s8(self,o):  return struct.unpack_from('<b', self.data, o)[0]
    def u16(self,o): return struct.unpack_from('<H', self.data, o)[0]
    def s16(self,o): return struct.unpack_from('<h', self.data, o)[0]
    def u32(self,o): return struct.unpack_from('<I', self.data, o)[0]
    def s32(self,o): return struct.unpack_from('<i', self.data, o)[0]
    def f32(self,o): return struct.unpack_from('<f', self.data, o)[0]
    def ptr(self,o):
        if o in self.local: return self.local[o]
        if o in self.glob:  return self.glob[o][1]
        return None
    def cstr(self,o):
        p = self.ptr(o)
        if p is None: return None
        e = self.data.index(b'\0', p)
        return self.data[p:e].decode('utf-8','replace')
    def array(self,o):
        """hkArray at offset o -> (data_offset or None, size)"""
        size = self.u32(o+8)
        return (self.ptr(o), size)

if __name__ == '__main__':
    import sys
    pf = Packfile(sys.argv[1] if len(sys.argv)>1 else '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx')
    for n in pf.seclist: print(n[0], [hex(x) for x in n[1:]])
    print("classes:", len(pf.classnames), "items:", len(pf.items))
    print("local fixups:", len(pf.local), "global:", len(pf.glob), "virtual:", len(pf.virt))
    c = collections.Counter(v for _,v in pf.items)
    for k,v in c.most_common(): print("  %-40s %d" % (k,v))

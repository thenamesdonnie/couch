import io, sys, struct
sys.path.insert(0,'/home/ds2000/src/hksc-disassembler/src')
from hksc_disassembler.loader.hs import HavokScriptFile
from hksc_disassembler.loader import hs_function as HF
from hksc_disassembler.common.reader import read_integer, align_to_bytes
def patched(self,f,header):
    self.upValueCount=read_integer(f,False,4,header.byteorder)
    self.paramCount=read_integer(f,False,4,header.byteorder)
    self.isVarArg=HF.HSVarArg(read_integer(f,False,1,header.byteorder))
    self.slotCount=read_integer(f,False,4,header.byteorder)
    self.unk=read_integer(f,False,4,header.byteorder)
    self.instructionCount=read_integer(f,False,4,header.byteorder)
    align_to_bytes(f,4)
    self._instr_off=f.tell()
    for _ in range(self.instructionCount):
        i=HF.HSInstruction(); i.read(f,header.byteorder); self.instructions.append(i)
    self.constantCount=read_integer(f,False,4,header.byteorder)
    for _ in range(self.constantCount):
        c=HF.HSConstant(); c.read(f,header); self.constants.append(c)
    self.hasDebugInfo=read_integer(f,False,4,header.byteorder)
    if self.hasDebugInfo: self.debugInfo.read(f,header)
    n=read_integer(f,False,4,header.byteorder)
    for _ in range(n):
        c=HF.HSFunction(); c.read(f,header); self.childFunctions.append(c)
    self.functionOffset=f.tell()
HF.HSFunction.read=patched
PATH=sys.argv[1] if len(sys.argv)>1 else '/home/ds2000/games/ps4/CUSA00900/dvdroot_ps4/action/script/c0000.hks'
data=open(PATH,'rb').read()
hs=HavokScriptFile(); hs.read(io.BytesIO(data))
MAIN=hs.mainFunction
def instr_off(idx,k):   # proto index, 1-based instruction number
    return MAIN.childFunctions[idx]._instr_off + 4*(k-1)
def word(off): return struct.unpack('>I',data[off:off+4])[0]
def jmp(sbx): return (28<<25) | ((0xFFFF+sbx)<<8)

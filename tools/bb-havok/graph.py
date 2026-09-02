from pf import Packfile
import sys, collections
PATH='/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.hkx'
pf = Packfile(PATH)
cls = dict(pf.items)
# string data
sd = [o for o,c in pf.items if c=='hkbBehaviorGraphStringData'][0]
def strarray(o):
    p,n = pf.array(o)
    return [pf.cstr(p+i*8) for i in range(n)] if p is not None else []
EVENTS = strarray(sd+16); VARS = strarray(sd+48)
def ev(i): return EVENTS[i] if 0<=i<len(EVENTS) else "<%d>"%i
def var(i): return VARS[i] if 0<=i<len(VARS) else "<%d>"%i

TI_SIZE = 72
TFLAGS=[(1,'USE_TRIGGER_INTERVAL'),(2,'USE_INITIATE_INTERVAL'),(4,'UNINTERRUPTIBLE_WHILE_PLAYING'),(8,'UNINTERRUPTIBLE_WHILE_DELAYED'),(16,'DELAY_STATE_CHANGE'),(32,'DISABLED'),(64,'DISALLOW_RETURN_TO_PREV'),(128,'DISALLOW_RANDOM'),(256,'DISABLE_CONDITION'),(512,'ALLOW_SELF_TRANS_FROM_ANY'),(1024,'IS_GLOBAL_WILDCARD'),(2048,'IS_LOCAL_WILDCARD'),(4096,'FROM_NESTED_VALID'),(8192,'TO_NESTED_VALID'),(16384,'ABUT_AT_END')]
def flagstr(f):
    return '|'.join(n for b,n in TFLAGS if f & b) or 'NONE'

def transitions(tia_off):
    """tia_off = offset of hkbStateMachineTransitionInfoArray item"""
    p,n = pf.array(tia_off+16)
    out=[]
    if p is None: return out
    for i in range(n):
        b = p + i*TI_SIZE
        out.append(dict(
            transition = pf.ptr(b+32),
            condition  = pf.ptr(b+40),
            eventId    = pf.s32(b+48),
            toStateId  = pf.s32(b+52),
            priority   = pf.s16(b+64),
            flags      = pf.u16(b+66),
        ))
    return out

def bindings(vbs_off):
    p,n = pf.array(vbs_off+16)
    out=[]
    if p is None: return out
    for i in range(n):
        b=p+i*40
        out.append((pf.cstr(b), pf.s32(b+28), pf.s8(b+32), pf.u8(b+33)))
    return out

if __name__=='__main__':
    # sanity: are ANY conditions non-null?
    nc=0; tot=0
    for o,c in pf.items:
        if c=='hkbStateMachineTransitionInfoArray':
            for t in transitions(o):
                tot+=1
                if t['condition'] is not None: nc+=1
    print("transitions total %d, with non-null condition: %d" % (tot,nc))
    # sanity: transition target classes
    tc=collections.Counter()
    for o,c in pf.items:
        if c=='hkbStateMachineTransitionInfoArray':
            for t in transitions(o):
                tc[cls.get(t['transition'],'NULL' if t['transition'] is None else 'UNKNOWN')]+=1
    print("transition effect classes:", tc.most_common())
    # sanity: eventIds in range
    bad=sum(1 for o,c in pf.items if c=='hkbStateMachineTransitionInfoArray' for t in transitions(o) if not (-1<=t['eventId']<len(EVENTS)))
    print("out-of-range eventIds:", bad)

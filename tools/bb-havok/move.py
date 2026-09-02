from graph import *
def dump_sm(o, deep=True):
    name=pf.cstr(o+56)
    p,n=pf.array(o+208)
    print("=== StateMachine '%s' @%#x  startStateId=%d ==="%(name,o,pf.s32(o+168)))
    wc=pf.ptr(o+224)
    if wc:
        print("  -- wildcard transitions --")
        for t in transitions(wc):
            print("     on %-30s -> stateId %-4d prio %-3d flags %s  effect=%s cond=%s"%(
                ev(t['eventId']),t['toStateId'],t['priority'],flagstr(t['flags']),
                cls.get(t['transition'],'NULL'), 'NULL' if t['condition'] is None else 'SET'))
    for i in range(n):
        sp=pf.ptr(p+i*8)
        sid=pf.s32(sp+104); sname=pf.cstr(sp+96); gen=pf.ptr(sp+88)
        print("  [state %d] '%s'  generator=%s @%s enable=%d"%(sid,sname,cls.get(gen,'NULL'),hex(gen) if gen else '-',pf.u8(sp+112)))
        tia=pf.ptr(sp+80)
        if tia:
            for t in transitions(tia):
                print("      on %-30s -> stateId %-4d prio %-3d flags %s cond=%s"%(
                    ev(t['eventId']),t['toStateId'],t['priority'],flagstr(t['flags']),
                    'NULL' if t['condition'] is None else 'SET'))
        else:
            print("      (no local transitions)")
dump_sm(0x177070)

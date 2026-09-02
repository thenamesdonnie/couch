"""DIRDASH v2: MoveDirection-bound four-way selectors on DashStart/Dash/DashEnd.

Forward keeps the untouched dash clips (5200/5000/6700).
Left/Right/Back get NEW hkbClipGenerator objects cloning the run strafe clips
(4002/4003/4001) with playbackSpeed raised by the measured root-motion ratio so
the sideways sprint covers ground at the forward dash rate.
"""
import re, sys

SRC = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.xml'
DST = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash2.xml'

# measured: extracted-motion translation per second, mean over every weapon set
DASH_UPS   = 4.3188 / 0.6666666865348816     # clip 005000, 9 sets, identical to 2dp
STRAFE_UPS = 2.776  / 0.7333333              # clips 004001/2/3, 18 sets each, identical
RATIO = DASH_UPS / STRAFE_UPS

s = open(SRC, encoding='ascii').read()

def get_obj(oid):
    m = re.search(r'<hkobject class="([^"]+)" name="%s" signature="([^"]*)">(.*?)</hkobject>\n'
                  % re.escape(oid), s, re.S)
    assert m, "object %s not found" % oid
    return m.group(1), m.group(2), m.group(3)

def stateinfo_id(name):
    m = re.search(r'<hkobject class="hkbStateMachineStateInfo" name="(#\d+)"[^>]*>'
                  r'(?:(?!</hkobject>).)*?<hkparam name="name">%s</hkparam>' % re.escape(name), s, re.S)
    assert m, "state %s not found" % name
    return m.group(1)

nxt = 13060
def newid():
    global nxt
    v = '#%d' % nxt; nxt += 1; return v

new_objects = []

def clone_strafe_cmsg(cmsg_id, label):
    """Clone a run-strafe CMSG and all its clip generators at RATIO playback speed."""
    cls, sig, body = get_obj(cmsg_id)
    assert cls == 'CustomManualSelectorGenerator'
    kids = re.search(r'<hkparam name="generators" numelements="(\d+)">(.*?)</hkparam>', body, re.S)
    kid_ids = kids.group(2).split()
    new_kids = []
    for k in kid_ids:
        kcls, ksig, kbody = get_obj(k)
        assert kcls == 'hkbClipGenerator', (k, kcls)
        assert re.search(r'name="triggers">null<', kbody), "clip %s has triggers, not handled" % k
        nid = newid()
        nb = re.sub(r'(<hkparam name="playbackSpeed">)[^<]*(</hkparam>)',
                    lambda m: m.group(1) + ('%.6f' % RATIO) + m.group(2), kbody, count=1)
        nb, n = re.subn(r'(<hkparam name="name">)([^<]*)(</hkparam>)',
                        lambda m: m.group(1) + m.group(2) + '_DashSpd' + m.group(3), nb, count=1)
        assert n == 1
        new_objects.append('        <hkobject class="hkbClipGenerator" name="%s" signature="%s">%s</hkobject>\n'
                           % (nid, ksig, nb))
        new_kids.append(nid)
    cid = newid()
    nb = body.replace(kids.group(0),
        '<hkparam name="generators" numelements="%d">\n%s\n</hkparam>' % (len(new_kids), '\n'.join(new_kids)))
    nb = re.sub(r'(<hkparam name="name">)([^<]*)(</hkparam>)',
                lambda m: m.group(1) + 'DashStrafe' + label + m.group(3), nb, count=1)
    new_objects.append('        <hkobject class="CustomManualSelectorGenerator" name="%s" signature="%s">%s</hkobject>\n'
                       % (cid, sig, nb))
    print("  cloned %s (%s) -> %s + %d clips at playbackSpeed %.6f" % (cmsg_id, label, cid, len(new_kids), RATIO))
    return cid

print("measured dash   %.4f units/s (clip 005000)" % DASH_UPS)
print("measured strafe %.4f units/s (clips 004001/2/3)" % STRAFE_UPS)
print("RATIO = %.6f" % RATIO)

BACK  = clone_strafe_cmsg('#4348', 'Back')
LEFT  = clone_strafe_cmsg('#4378', 'Left')
RIGHT = clone_strafe_cmsg('#4408', 'Right')

# DashStart and Dash share the sped-up strafe set; DashEnd uses the stock RunEnd strafes.
PLAN = [
    ('DashStart', '#4460', BACK,   LEFT,   RIGHT),
    ('Dash',      '#4481', BACK,   LEFT,   RIGHT),
    ('DashEnd',   '#4499', '#4533', '#4547', '#4561'),
]
for label, fwd, b, l, r in PLAN:
    sid = stateinfo_id(label)
    gen_id, bind_id = newid(), newid()
    new_objects.append(
'        <hkobject class="hkbManualSelectorGenerator" name="%s" signature="0x591a8476">\n'
'            <hkparam name="variableBindingSet">%s</hkparam>\n'
'            <hkparam name="userData">0</hkparam>\n'
'            <hkparam name="name">%s Direction ManualSelectorGenerator</hkparam>\n'
'            <hkparam name="generators" numelements="4">\n%s\n%s\n%s\n%s\n</hkparam>\n'
'            <hkparam name="selectedGeneratorIndex">0</hkparam>\n'
'            <hkparam name="indexSelector">null</hkparam>\n'
'            <hkparam name="selectedIndexCanChangeAfterActivate">true</hkparam>\n'
'            <hkparam name="generatorChangedTransitionEffect">null</hkparam>\n'
'            <hkparam name="endOfClipEventId">-1</hkparam>\n'
'        </hkobject>\n'
'        <hkobject class="hkbVariableBindingSet" name="%s" signature="0xe942f339">\n'
'            <hkparam name="bindings" numelements="1">\n'
'                <hkobject>\n'
'                    <hkparam name="memberPath">selectedGeneratorIndex</hkparam>\n'
'                    <hkparam name="variableIndex">14</hkparam>\n'
'                    <hkparam name="bitIndex">255</hkparam>\n'
'                    <hkparam name="bindingType">BINDING_TYPE_VARIABLE</hkparam>\n'
'                </hkobject>\n'
'            </hkparam>\n'
'            <hkparam name="indexOfBindingToEnable">-1</hkparam>\n'
'        </hkobject>\n' % (gen_id, bind_id, label, fwd, b, l, r, bind_id))
    pat = re.compile(r'(<hkobject class="hkbStateMachineStateInfo" name="%s".*?<hkparam name="generator">)([^<]*)(</hkparam>)'
                     % re.escape(sid), re.S)
    s, n = pat.subn(lambda m: m.group(1) + gen_id + m.group(3), s, count=1)
    assert n == 1, label
    print("  %-9s state %s generator -> %s   [F %s | B %s | L %s | R %s]" % (label, sid, gen_id, fwd, b, l, r))

s = s.replace('    </hksection>', ''.join(new_objects) + '    </hksection>', 1)
open(DST, 'w', encoding='ascii').write(s)
print("wrote %s  (%d new objects, next free id #%d)" % (DST, len(new_objects), nxt))

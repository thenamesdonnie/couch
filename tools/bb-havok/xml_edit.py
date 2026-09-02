"""Give DashStart/Dash/DashEnd the same MoveDirection selector every other
locomotion state already has, using generators that already exist in the file."""
import re, sys

SRC = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.xml'
DST = '/home/ds2000/couch/data/bb-hks/anibnd/hkx/c0000_behavior.dirdash.xml'
s = open(SRC, encoding='ascii').read()

# stateInfo object id -> (label, forward generator, back, left, right)
PLAN = [
    ('#4471', 'DashStart', '#4460', '#4348', '#4378', '#4408'),  # sideways: run strafe
    ('#4476', 'Dash',      '#4481', '#4348', '#4378', '#4408'),
    ('#4497', 'DashEnd',   '#4499', '#4533', '#4547', '#4561'),  # sideways: RunEnd strafe
]
# resolve DashStart/DashEnd stateInfo ids by name rather than trusting guesses
def stateinfo_id(name):
    m = re.search(r'<hkobject class="hkbStateMachineStateInfo" name="(#\d+)"[^>]*>(?:(?!</hkobject>).)*?'
                  r'<hkparam name="name">%s</hkparam>' % re.escape(name), s, re.S)
    return m.group(1) if m else None
resolved = []
for _sid, label, fwd, b, l, r in PLAN:
    sid = stateinfo_id(label)
    assert sid, "state %s not found" % label
    resolved.append((sid, label, fwd, b, l, r))
    print("state %-9s -> %s" % (label, sid))

nxt = 13060
new_objects = []
for sid, label, fwd, b, l, r in resolved:
    gen_id, bind_id = '#%d' % nxt, '#%d' % (nxt+1); nxt += 2
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
    # repoint the state's generator
    pat = re.compile(r'(<hkobject class="hkbStateMachineStateInfo" name="%s".*?<hkparam name="generator">)([^<]*)(</hkparam>)' % re.escape(sid), re.S)
    s, n = pat.subn(lambda m: m.group(1) + gen_id + m.group(3), s, count=1)
    assert n == 1, "generator repoint failed for %s" % label
    print("  %s.generator -> %s  (children %s %s %s %s)" % (label, gen_id, fwd, b, l, r))

s = s.replace('    </hksection>', ''.join(new_objects) + '    </hksection>', 1)
open(DST, 'w', encoding='ascii').write(s)
print("wrote", DST, len(s), "chars;", len(new_objects)*2, "new objects")

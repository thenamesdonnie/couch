# Bloodborne 1.09: locked-on sprint faces the stick (Elden Ring style). v7.
# Three code caves in the zero-filled tail of the code segment (0x50db000..).
#
# History: v2 (caves a/b/c on the live sprint state) is the verified working
# turn. v3 hooked the turn-anim picker: no effect. v4 made a/b follow ROT+0x58
# bit 3: the body stopped turning, so the flag-copy hook (cave_c) evidently
# never runs for the player (two classes carry that routine, 0x536fe80 and
# 0x5370610, and the player's is not the hooked one); a/b/c go back to v2.
# v5 zeroed the quantised turn angle FUN_01513c10 hands to the rotation
# applier: still skidded, because that is not what the script sees.
# v6 zeroed the Havok TurnAngle (FUN_01a18bf0 publishes INP+0x24 * 57.29578)
# while locked: still skidded. Donnie's test settled it: no skid if the stick
# stays pushed after releasing circle (script goes Dash -> Run), skid only
# when everything is released (script fires "Dash to DashEnd", the 1.0 s
# sprint-stop slide, which our snap-back to the target then rotates).
# v7 / cave_a: a hold timer in scratch memory (0x56d3f00, zero-filled tail of
# the RW segment past memsz 0x56d30f4). Sprinting arms it to 1.0 s; when the
# sprint ends with the stick released the input keeps facing the stick
# direction until it expires (the slide plays straight, Elden Ring style);
# a stick push cancels it at once (the Dash -> Run case, unchanged from v2).
# cave_f now publishes TurnAngle = 0 whenever locked on, so the turn after
# the hold is a plain rotation and Act_Turn can never fire W_Turn_Dash.
#
# live sprint := INP = [ChrIns+0x280], INP->circleHold(+0xd0) > DAT_05127b48
#                (the 0.4 s dash-button window: exactly the test that sets the
#                engine's own sprint flag REQ+0x9c bit 1 in FUN_01526750),
#            AND LOCO = [ChrIns+0x1c8], LOCO->state(+0x138) | 2 == 3.
# The float compare is done as a signed-int compare, valid for non-negative
# floats, so no xmm register is touched (xmm0 = dt is live at cave_b).
.intel_syntax noprefix
.set DASH_WINDOW, 0x5127b48
.set BASE, 0x50db000                   # must match ld -Ttext
.text
.globl _start
_start:
.set HOLD, 0x56d3f00                   # scratch float: seconds of facing hold left
.set HOLD_SECS, 0x3f800000             # 1.0f = the DashEnd clip length
.set STICK_DEAD, 0x3dcccccd            # 0.1f
cave_a:                                 # from 0x15267b3 (PlayerInput::update top)
                                        # r15 = ChrIns, r12 = INP; rax/xmm0 dead (just after a call)
                                        # dt is at [rbp-0x134]
    cmp byte ptr [r15+0x245], 0         # ChrIns.notLocked
    jne 1f
    mov eax, [r12+0xd0]
    .byte 0x3b, 0x05                    # cmp eax, [rip+disp32] -> DASH_WINDOW
    .long DASH_WINDOW - (BASE + (9f - _start))
9:
    jle 4f
    mov rax, [r15+0x1c8]
    test rax, rax
    jz 4f
    mov eax, [rax+0x138]
    or eax, 2
    cmp eax, 3
    jne 4f
    .byte 0xc7, 0x05                    # sprinting: mov dword [HOLD], HOLD_SECS
    .long HOLD - (BASE + (9f - _start))
    .long HOLD_SECS
9:
    jmp 1f
4:  .byte 0x8b, 0x05                    # mov eax, [HOLD]
    .long HOLD - (BASE + (9f - _start))
9:
    test eax, eax
    jle 2f                              # no hold: face the lock target
    mov eax, [r12+0x40]                 # stick x
    and eax, 0x7fffffff
    cmp eax, STICK_DEAD
    ja 5f
    mov eax, [r12+0x44]                 # stick y
    and eax, 0x7fffffff
    cmp eax, STICK_DEAD
    ja 5f
    .byte 0xc5, 0xfa, 0x10, 0x05        # vmovss xmm0, [HOLD]
    .long HOLD - (BASE + (9f - _start))
9:
    vsubss xmm0, xmm0, dword ptr [rbp-0x134]
    .byte 0xc5, 0xfa, 0x11, 0x05        # vmovss [HOLD], xmm0
    .long HOLD - (BASE + (9f - _start))
9:
    jmp 1f                              # holding: keep facing the stick
5:  .byte 0xc7, 0x05                    # stick pushed: mov dword [HOLD], 0
    .long HOLD - (BASE + (9f - _start))
    .long 0
9:
    jmp 2f
1:  cmp byte ptr [r12+0x194], 0
    jne 2f
    jmp 0x1526897                       # variant B: face the stick
2:  jmp 0x15267cc                       # variant A: face the lock target
.org 0xc0
cave_b:                                 # from 0x152b020 (additional turn helper)
                                        # rdi = ChrIns, rax dead, xmm0 = dt live
    vxorps xmm1, xmm1, xmm1
    cmp byte ptr [rdi+0x245], 0
    jne 1f
    mov rax, [rdi+0x280]
    test rax, rax
    jz 2f
    mov eax, [rax+0xd0]
    .byte 0x3b, 0x05
    .long DASH_WINDOW - (BASE + (9f - _start))
9:
    jle 2f
    mov rax, [rdi+0x1c8]
    test rax, rax
    jz 2f
    mov eax, [rax+0x138]
    or eax, 2
    cmp eax, 3
    jne 2f
1:  jmp 0x152b02d                       # continue: turn allowed
2:  jmp 0x152b058                       # return 0
.org 0x110
cave_c:                                 # from 0x152b40d (copy notLocked into ROT+0x58 bit 3)
                                        # rbx = ChrIns, rax = ROT (live), cl = output
    mov cl, [rbx+0x245]
    test cl, cl
    jnz 1f
    push rax
    mov rax, [rbx+0x280]
    test rax, rax
    jz 2f
    mov eax, [rax+0xd0]
    .byte 0x3b, 0x05                    # cmp eax, [rip+disp32] -> DASH_WINDOW
    .long DASH_WINDOW - (BASE + (9f - _start))
9:
    jle 2f
    mov rax, [rbx+0x1c8]
    test rax, rax
    jz 2f
    mov eax, [rax+0x138]
    or eax, 2
    cmp eax, 3
    jne 2f
    mov cl, 1
2:  pop rax
1:  jmp 0x152b413
.org 0x160
.set DEG_PER_RAD, 0x49283c4             # the 57.29578f the original multiplies by
cave_f:                                 # from 0x1a19109 (FUN_01a18bf0, TurnAngle publish)
                                        # rdx = ChrIns, rcx = INP, rax dead, result in xmm0
    vmovss xmm0, dword ptr [rcx+0x24]
    .byte 0xc5, 0xfa, 0x59, 0x05        # vmulss xmm0, xmm0, [rip+disp32] -> DEG_PER_RAD
    .long DEG_PER_RAD - (BASE + (9f - _start))
9:
    cmp byte ptr [rdx+0x245], 0
    jne 3f                              # not locked: vanilla
    vxorps xmm0, xmm0, xmm0             # locked: TurnAngle = 0
3:  jmp 0x1a19116

#!/usr/bin/env python3
"""Read event flags out of a Bloodborne (PS4/shadPS4) save.

Rewritten into the repo 28 Aug 2026 after the original was lost with a
session scratchpad - that risk was logged as an open item in todo.md on
26 Aug and duly bit us two days later. Do not leave this in /tmp again.

PROVEN FORMAT (empirical, see docs/research/bloodborne-lamp-saga-20260826.md):
  * userdata0000 / backup0000 are plaintext, exactly 1310720 bytes, no checksum.
  * u32 at 0x34 = event-flag block offset, u32 at 0x38 = its length (150001),
    u32 at 0x3C = offset+length (the validation chain). The offset is NOT
    constant across saves, so read it from the header every time.
  * The block is 1200 group slots x 125 bytes (= 1000 flags each) + 1 pad byte.
  * Within a slot, for a flag id ending in the 3 digits `sub`:
        byte = base + slot*125 + (sub >> 3)
        mask = 0x80 >> (sub & 7)            # MSB-first
NOT KNOWN: the general flag-group -> slot-index map (a runtime table in the
executable). Only the slots below are pinned, by diffing real saves.

Usage:
  bb-eventflags.py <save> --slot 50 --sub 857        # one flag, positional
  bb-eventflags.py <save> --mod-settings             # the Enhanced settings
"""
import argparse
import struct
import sys

SAVE_SIZE = 1310720
BLOCK_LEN = 150001
GROUP_STRIDE = 125

# Empirically pinned. group 12100 = Bloodborne Enhanced's settings block,
# group 12411 = Central Yharnam progress.
GROUP_SLOTS = {12100: 50, 12411: 170, 5: 5}

# Enhanced 0.11.2-fix9: "Enabled" flag id per setting (only the Enabled id is
# ever tested by game logic; the Disabled id is inert bookkeeping).
MOD_SETTINGS = [
    (862, "Auto Refill Bullets And Vials"),
    (872, "Lamp Menu"),
    (880, "Lamp Menu: Warp"),
    (857, "Quick Warp to Bosses"),
    (893, "Prompt Quick Warp to Bosses"),
    (881, "Prime Hunter's Mark: Warp"),
    (889, "Always Show Summon Signs"),
    (871, "Stocked Shop"),
    (892, "Temporary Stocked Shop"),
    (848, "Shops Plus"),
    (855, "Infinite Durability"),
    (867, "Lamp Menu: Boss Rematches"),
]


def block_base(save: bytes) -> int:
    off, length, check = struct.unpack_from("<III", save, 0x34)
    if length != BLOCK_LEN or check != off + length:
        sys.exit(f"header validation failed: off={off} len={length} check={check}")
    return off


def read_flag_at(save: bytes, slot: int, sub: int) -> bool:
    base = block_base(save)
    byte = base + slot * GROUP_STRIDE + (sub >> 3)
    return bool(save[byte] & (0x80 >> (sub & 7)))


def read_flag(save: bytes, flag_id: int) -> bool:
    group, sub = divmod(flag_id, 1000)
    if group not in GROUP_SLOTS:
        sys.exit(f"flag {flag_id}: group {group} has no known slot; use --slot")
    return read_flag_at(save, GROUP_SLOTS[group], sub)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--slot", type=int)
    ap.add_argument("--sub", type=int)
    ap.add_argument("--flag", type=int)
    ap.add_argument("--mod-settings", action="store_true")
    a = ap.parse_args()

    save = open(a.save, "rb").read()
    if len(save) != SAVE_SIZE:
        sys.exit(f"unexpected save size {len(save)} (want {SAVE_SIZE})")

    if a.mod_settings:
        print(f"Bloodborne Enhanced settings live in {a.save} (group 12100, slot 50):")
        for sub, name in MOD_SETTINGS:
            print(f"  {name:<34} {'ON' if read_flag_at(save, 50, sub) else 'off'}")
    elif a.flag is not None:
        print(read_flag(save, a.flag))
    elif a.slot is not None and a.sub is not None:
        print(read_flag_at(save, a.slot, a.sub))
    else:
        ap.error("give --mod-settings, --flag, or both --slot and --sub")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pull menu movies (and anything else by exact path) out of the DS3 archives.

    menu_gfx_extract.py /menu/01_001_fe_soul.gfx [/menu/...]   -> extract/ds3/gfx/

The HUD is not one movie: `01_000_fe.gfx` draws bars, badge, equipment slots
and messages, but the SOULS COUNTER is `01_001_fe_soul.gfx` and the autosave
spinner `01_002_fe_saveicon.gfx`. They share `01_common.tpf.dcx`, which is why
a texture edit shows up on screen while the movie you are reading never
mentions it. `dict_DarkSouls3.txt` lists every path.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dvdbnd import DvdBnd, DS3

GAME = Path.home() / ".steam/steam/steamapps/common/DARK SOULS III/Game"
KEYS_CS = Path.home() / "couch/data/ds3-ui-port/uxm_keys.cs"
OUT = Path.home() / "couch/data/ds3-ui-port/extract/ds3/gfx"


def ds3_keys() -> dict[str, str]:
    txt = KEYS_CS.read_text(encoding="utf-8-sig")
    m = re.search(r"DarkSouls3Keys\s*=\s*new Dictionary<string, string>\s*\{(.*?)\n\s*\};", txt, re.S)
    # only the DS3 block: the file holds several games' dicts with the same labels
    return dict(re.findall(
        r'\["([^"]+)"\]\s*=\s*@"(-----BEGIN RSA PUBLIC KEY-----.*?-----END RSA PUBLIC KEY-----)"',
        m.group(1), re.S))


def main():
    bnd = DvdBnd(GAME, ds3_keys(), DS3)
    OUT.mkdir(parents=True, exist_ok=True)
    for p in sys.argv[1:]:
        data = bnd.get(p)
        if data is None:
            print("MISSING", p)
            continue
        dst = OUT / Path(p).name
        dst.write_bytes(data)
        print(f"{p} -> {dst} ({len(data)} bytes, magic {data[:3]!r})")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Why is 4K120 being pruned? Read the DP->HDMI adapter's own capability
registers (DPCD) and say, in words, where the ceiling is.

Run as root (the AUX channel device needs it):
    sudo python3 ~/couch/tools/dpcd-probe.py

Reads /dev/drm_dp_aux1 (the connected DP-2 connector's AUX). Decodes:
  * the trained link (rate x lanes = raw bandwidth on the GPU->adapter hop)
  * the branch/downstream block at 0x080 (what the adapter says its HDMI
    side can do - the max TMDS clock byte is the classic 600MHz=4K60 cap)
  * DSC support at 0x060 (compression is the only way 4K120 RGB fits
    through DP1.4 without dropping to 4:2:0)
  * HDMI 2.1 pass-through caps at 0x0A0 if present (PCON FRL)
"""
import glob
import os, sys

# The connected DP connector's AUX channel, found live (the connector - and
# with it the aux number - renames on every replug on this box).
AUX = None
for st in glob.glob('/sys/class/drm/card*-DP-*/status'):
    if open(st).read().strip() == 'connected':
        d = os.path.dirname(st)
        auxes = [a for a in os.listdir(d) if a.startswith('drm_dp_aux')]
        if auxes:
            AUX = '/dev/' + auxes[0]
            print('probing %s (%s)' % (AUX, os.path.basename(d)))
            break
if not AUX:
    sys.exit('no connected DP connector with an AUX channel found')

def rd(f, off, n):
    os.lseek(f, off, os.SEEK_SET)
    return os.read(f, n)

try:
    f = os.open(AUX, os.O_RDONLY)
except PermissionError:
    sys.exit('needs root: sudo python3 %s' % sys.argv[0])

base = rd(f, 0x000, 16)
rate_tbl = {0x06: '1.62', 0x0a: '2.70', 0x14: '5.40', 0x1e: '8.10'}
print('== link (GPU -> adapter) ==')
print('DPCD rev          : %x.%x' % (base[0] >> 4, base[0] & 0xf))
print('max link rate     : %s Gbps/lane' % rate_tbl.get(base[1], hex(base[1])))
print('max lanes         : %d' % (base[2] & 0x1f))
lane_set = rd(f, 0x100, 2)
print('trained rate      : %s Gbps/lane x %d lanes'
      % (rate_tbl.get(lane_set[0], hex(lane_set[0])), lane_set[1] & 0x1f))

down = rd(f, 0x080, 16)
print('\n== adapter downstream (adapter -> TV) ==')
present = rd(f, 0x005, 1)[0]
print('downstream present: %s (raw 0x%02x)' % (bool(present & 1), present))
dp_type = (down[0] & 0x07)
types = {0: 'DisplayPort', 1: 'VGA', 2: 'DVI', 3: 'HDMI', 4: 'others/no-EDID', 5: 'DP++'}
print('port type         : %s (raw 0x%02x)' % (types.get(dp_type, dp_type), down[0]))
print('detailed caps raw : %02x %02x %02x %02x' % (down[0], down[1], down[2], down[3]))
if down[1]:
    print('max TMDS clock    : %d MHz (legacy field; FRL below is what'
          ' matters for HDMI 2.1)' % (down[1] * 2.5))
# FRL: kernel reads the max FRL bandwidth from detailed-cap byte 2
# (drm_dp_get_pcon_max_frl_bw). Non-zero = the adapter announces HDMI 2.1
# FRL conversion to the driver; 0 = the driver will never try FRL.
frl_field = (down[2] >> 2) & 0x7
frl_gbps = {0: 0, 1: 9, 2: 18, 3: 24, 4: 32, 5: 40, 6: 45}.get(frl_field, -1)
print('PCON max FRL      : %s Gbps (byte2 raw 0x%02x)  <-- 0 here means'
      ' the driver sees no HDMI 2.1 path' % (frl_gbps, down[2]))
print('DSC pass-through  : %s (0x060 bit1)' % bool(rd(f, 0x060, 1)[0] & 2))

dsc = rd(f, 0x060, 16)
print('\n== DSC (compression over the DP hop) ==')
print('DSC supported     : %s (0x060 raw 0x%02x)' % (bool(dsc[0] & 1), dsc[0]))
if dsc[0] & 1:
    print('DSC version       : %d.%d' % (dsc[1] & 0xf, dsc[1] >> 4))

pcon = rd(f, 0x0a0, 16)
print('\n== PCON / HDMI 2.1 FRL pass-through (0x0A0) ==')
print('raw               :', pcon.hex())
frl_bw = pcon[2] & 0x7f if len(pcon) > 2 else 0
if pcon[1] & 0x01:
    print('FRL link supported: yes')
print('(non-zero bytes here mean the adapter does HDMI 2.1 FRL conversion)')

os.close(f)

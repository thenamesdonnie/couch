#!/bin/bash
# Find the CASE fan's (pwm1/fan1) real limits: the duty it keeps spinning at,
# and the duty it can start from rest. Restores the board's own control on
# exit, including if you Ctrl-C it. The CPU fan (pwm2) is never touched.
set -u
H=/sys/class/hwmon/hwmon1
[ "$(cat $H/name)" = "nct6798" ] || { echo "wrong chip at $H"; exit 1; }

OLD_E=$(cat $H/pwm1_enable); OLD_D=$(cat $H/pwm1)
restore() {
  echo "$OLD_D" > $H/pwm1 2>/dev/null
  echo "$OLD_E" > $H/pwm1_enable 2>/dev/null
  echo
  echo "restored: duty $OLD_D mode $OLD_E (board back in charge)"
}
trap restore EXIT INT TERM

rpm() { cat $H/fan1_input; }
set_duty() { echo "$1" > $H/pwm1; }

echo 1 > $H/pwm1_enable          # manual
echo "spinning up to full first..."
set_duty 255; sleep 6
echo "  255 -> $(rpm) RPM"

echo
echo "STEPPING DOWN (where does it keep turning?)"
STOP=""
for d in 140 120 110 100 90 85 80 75 70 65 60; do
  set_duty $d; sleep 7
  r=$(rpm)
  pct=$(( d * 100 / 255 ))
  printf "  duty %3d (%2d%%) -> %5s RPM\n" "$d" "$pct" "$r"
  if [ "$r" -eq 0 ] && [ -z "$STOP" ]; then STOP=$d; echo "    ^ STALLED here"; break; fi
done

echo
echo "STEPPING UP FROM REST (what duty gets it going again?)"
set_duty 0; sleep 6
START=""
for d in 70 80 90 100 110 120 140; do
  set_duty $d; sleep 7
  r=$(rpm)
  pct=$(( d * 100 / 255 ))
  printf "  duty %3d (%2d%%) -> %5s RPM\n" "$d" "$pct" "$r"
  if [ "$r" -gt 0 ]; then START=$d; echo "    ^ STARTS here"; break; fi
done

echo
echo "RESULT: stalls at ${STOP:-<did not stall down to 60>}, starts at ${START:-<did not start by 140>}"

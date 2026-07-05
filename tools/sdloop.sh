#!/bin/bash
# Rig-side reliability loop: run the shakedown N times LOCALLY (detached via
# nohup) so a flaky/high-latency SSH from the controller can never kill a run
# mid-SPI-transaction. Usage: sdloop.sh <N> [--commit]
cd ~/local/gwifi/gwifi-openwrt/tools || exit 9
N=${1:-12}
MODE=${2:-}
pass=0
for n in $(seq 1 "$N"); do
  echo "=== run $n / $N  $(date -u +%H:%M:%S) mode='${MODE:-dry}' ==="
  if timeout 180 python3 flash_puck_usb.py --log ~/local/gwifi/fleet-flash/logs/sdloop-$n.log \
        shakedown --spins 3000 $MODE 2>&1 \
        | grep -E "SPI stream OK|FATAL|WRITE PATH OK|byte-identical|ABORTED"; then
    :
  fi
  # record pass/fail by scanning the per-run log
  if grep -q "WRITE PATH OK\|DRY-RUN: would" ~/local/gwifi/fleet-flash/logs/sdloop-$n.log 2>/dev/null; then
    pass=$((pass+1))
  fi
done
echo "=== LOOP DONE: $pass / $N passed ==="

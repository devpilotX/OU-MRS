#!/bin/bash
# Phase 9.7AA-lite live watcher
while true; do
  clear
  echo "=== $(date '+%Y-%m-%d %H:%M:%S IST') === (HEAD: $(git rev-parse --short HEAD))"
  echo "FILTERS: VOL_CONFIRM=$(grep ^OU_VOL_CONFIRM .env | cut -d= -f2)  ATR_PCT_FILTER=$(grep ^OU_ATR_PCT_FILTER .env | cut -d= -f2)"
  echo
  for s in BNF NF MCN; do
    python3 -c "
import json
d = json.load(open('state/live_$s.json'))
z = d['z']
ze = d.get('z_entry', 1.5)
if abs(z) >= ze:
    flag = '  *** SETUP (|z|>=' + str(ze) + ') ***'
elif abs(z) >= ze - 0.2:
    flag = '  ~near entry'
else:
    flag = ''
print(f'$s  z={z:+.3f}  ltp={d[\"ltp\"]:>9}  mean={d[\"mean\"]:.2f}  candles={d[\"candles_count\"]}{flag}')
"
  done
  echo
  echo "--- last 8 [entry]/[exit]/[skip] events (last 10 min) ---"
  sudo journalctl -u ou-mrs.service -S "$(date -d '10 min ago' '+%Y-%m-%d %H:%M:%S')" --no-pager 2>/dev/null \
    | grep -E '\[entry\]|\[exit\]|\[skip\] Phase 9.7Z' | tail -8
  echo
  echo "(Ctrl+C to exit. Refreshing in 5s...)"
  sleep 5
done

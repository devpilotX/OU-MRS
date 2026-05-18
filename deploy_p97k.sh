#!/bin/bash
# Phase 9.7k deploy — definitive, no set -e, explicit error handling
TS=$(date +%s)
PHASE=p97k
die() { echo "FAIL: $1"; exit 1; }

echo "===== PHASE 9.7k DEPLOYMENT @ $(date '+%H:%M:%S') IST ====="
echo "TS=$TS"
echo ""

echo "===== STEP 0: PRE-FLIGHT ====="
[ -f .env ] || die ".env missing"
[ -f ou_mrs.py ] || die "ou_mrs.py missing"
[ -f strategy.py ] || die "strategy.py missing"
[ -d venv ] || die "venv missing"

ACTIVE=$(systemctl is-active ou-mrs.service 2>/dev/null)
[ "$ACTIVE" = "inactive" ] || die "bot is '$ACTIVE', expected 'inactive'"
echo "OK bot is inactive"

grep -q '^OU_ADX_THRESHOLD=28$' .env || die ".env does not have OU_ADX_THRESHOLD=28"
echo "OK .env baseline correct"

CANDLE_COUNT=$(grep -c 'rows = broker.get_candles(_fetch_start, now, "ONE_MINUTE")' ou_mrs.py)
if [ -z "$CANDLE_COUNT" ]; then CANDLE_COUNT=0; fi
[ "$CANDLE_COUNT" = "1" ] || die "anchor matched '$CANDLE_COUNT' times, expected 1"
echo "OK get_candles anchor unique"

if grep -q "Phase 9.7k: stagger" ou_mrs.py; then die "already patched (idempotency)"; fi
echo "OK not yet patched"
echo ""

echo "===== STEP 1: BACKUP (TS=$TS) ====="
cp .env .env.bak.$PHASE.$TS || die "backup .env failed"
cp ou_mrs.py ou_mrs.py.bak.$PHASE.$TS || die "backup ou_mrs.py failed"
cp strategy.py strategy.py.bak.$PHASE.$TS || die "backup strategy.py failed"
ls -la *.bak.$PHASE.$TS
echo ""

echo "===== STEP 2: F1 ADX 28 -> 32 ====="
sed -i 's/^OU_ADX_THRESHOLD=28$/OU_ADX_THRESHOLD=32/' .env || die "sed .env failed"
grep -q '^OU_ADX_THRESHOLD=32$' .env || die ".env update did not land"
grep '^OU_ADX_THRESHOLD=' .env
echo ""

echo "===== STEP 3: F2 stagger injection ====="
venv/bin/python3 << 'PYEOF'
import re, sys
path = "ou_mrs.py"
with open(path) as f: src = f.read()
if "Phase 9.7k: stagger" in src:
    print("FAIL: already patched"); sys.exit(1)
pat = re.compile(r'^([ \t]+)rows = broker\.get_candles\(_fetch_start, now, "ONE_MINUTE"\)$', re.MULTILINE)
matches = pat.findall(src)
if len(matches) != 1:
    print(f"FAIL: expected 1 anchor, found {len(matches)}"); sys.exit(1)
indent = matches[0]
old_line = f'{indent}rows = broker.get_candles(_fetch_start, now, "ONE_MINUTE")'
new_block = f'{indent}time.sleep(0.4)  # Phase 9.7k: stagger Angel API calls (3 req/sec limit, 157 rate-limits on 14 May)\n{old_line}'
src2 = src.replace(old_line, new_block, 1)
with open(path, "w") as f: f.write(src2)
print("OK ou_mrs.py patched: 0.4s stagger before get_candles")
PYEOF
[ $? -eq 0 ] || die "F2 python patch failed"
echo ""

echo "===== STEP 4: VERIFY PATCHES ====="
echo "--- .env ---"
grep '^OU_ADX_THRESHOLD=' .env
echo "--- ou_mrs.py stagger (context) ---"
grep -n -B1 'rows = broker.get_candles' ou_mrs.py | head -5
echo ""

echo "===== STEP 5: py_compile ====="
venv/bin/python3 -m py_compile ou_mrs.py || die "ou_mrs.py compile error"
echo "OK ou_mrs.py compiles"
venv/bin/python3 -m py_compile strategy.py || die "strategy.py compile error"
echo "OK strategy.py compiles"
echo ""

echo "===== STEP 6: env reload ====="
venv/bin/python3 << 'PYEOF'
import os
from dotenv import load_dotenv
load_dotenv()
v = float(os.environ.get("OU_ADX_THRESHOLD"))
assert v == 32.0, f"FAIL got {v}"
print(f"OK OU_ADX_THRESHOLD loads as {v}")
PYEOF
[ $? -eq 0 ] || die "env reload check failed"
echo ""

echo "===== STEP 7: DIFFS ====="
echo "--- .env diff ---"
diff .env.bak.$PHASE.$TS .env
echo "--- ou_mrs.py diff ---"
diff ou_mrs.py.bak.$PHASE.$TS ou_mrs.py
echo ""

echo "===== STEP 8: TIMER ====="
sudo systemctl list-timers ou-mrs.timer --no-pager
echo ""

echo "============================================="
echo "PHASE 9.7k DEPLOYMENT COMPLETE"
echo "============================================="
echo "TS                : $TS"
echo "Backups           : *.bak.$PHASE.$TS"
echo "Applied:"
echo "  F1: OU_ADX_THRESHOLD 28 -> 32"
echo "  F2: 0.4s stagger before broker.get_candles"
echo ""
echo "ROLLBACK:"
echo "  cp .env.bak.$PHASE.$TS .env"
echo "  cp ou_mrs.py.bak.$PHASE.$TS ou_mrs.py"
echo "  cp strategy.py.bak.$PHASE.$TS strategy.py"

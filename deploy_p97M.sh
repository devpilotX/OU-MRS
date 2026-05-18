#!/bin/bash
# Phase 9.7M — evidence-based revert to sweep winner + retry/stagger tuning
TS=$(date +%s)
PHASE=p97M
die() { echo "FAIL: $1"; exit 1; }

echo "===== PHASE 9.7M DEPLOY @ $(date '+%H:%M:%S') IST ====="
echo "TS=$TS"
echo ""

echo "===== STEP 0: PRE-FLIGHT ====="
[ -f .env ] || die ".env missing"
[ -f ou_mrs.py ] || die "ou_mrs.py missing"
[ -f angel_adapter.py ] || die "angel_adapter.py missing"
grep -q '^OU_ADX_THRESHOLD=35$' .env || die ".env doesn't have ADX=35 (current state)"
grep -q '^OU_Z_ENTRY=1.5$' .env || die ".env doesn't have Z_ENTRY=1.5"
grep -q 'Phase 9.7L: bump 0.4->1.5' ou_mrs.py || die "ou_mrs.py missing 9.7L marker"
grep -q 'for attempt in range(4):' angel_adapter.py || die "angel_adapter.py missing retry loop"
if grep -q "Phase 9.7M" ou_mrs.py angel_adapter.py .env 2>/dev/null; then die "9.7M already applied"; fi
ACTIVE=$(systemctl is-active ou-mrs.service)
[ "$ACTIVE" = "inactive" ] || die "ou-mrs.service is $ACTIVE, must be inactive for safe deploy"
echo "OK pre-flight (bot inactive, all baselines correct)"
echo ""

echo "===== STEP 1: BACKUP ====="
cp .env .env.bak.$PHASE.$TS || die "backup .env"
cp ou_mrs.py ou_mrs.py.bak.$PHASE.$TS || die "backup ou_mrs.py"
cp angel_adapter.py angel_adapter.py.bak.$PHASE.$TS || die "backup angel_adapter.py"
ls -la .env.bak.$PHASE.$TS ou_mrs.py.bak.$PHASE.$TS angel_adapter.py.bak.$PHASE.$TS
echo ""

echo "===== STEP 2: FIX A+B — .env ADX 35->30, Z_ENTRY 1.5->1.4 ====="
sed -i 's/^OU_ADX_THRESHOLD=35$/OU_ADX_THRESHOLD=30/' .env
sed -i 's/^OU_Z_ENTRY=1.5$/OU_Z_ENTRY=1.4/' .env
grep -q '^OU_ADX_THRESHOLD=30$' .env || die "ADX patch failed"
grep -q '^OU_Z_ENTRY=1.4$' .env || die "Z patch failed"
# Add provenance marker (commented line above)
python3 << 'MARKEOF'
src = open('.env').read()
if "# Phase 9.7M:" not in src:
    src = src.replace("OU_ADX_THRESHOLD=30",
                      "# Phase 9.7M (2026-05-15): revert to sweep winner from commit b4bc29e\nOU_ADX_THRESHOLD=30")
    src = src.replace("OU_Z_ENTRY=1.4",
                      "# Phase 9.7M: backtest PF 1.29 with z=1.4 adx=30 (52d479a)\nOU_Z_ENTRY=1.4")
    open('.env', 'w').write(src)
print("OK .env markers added")
MARKEOF
echo ".env trading config after edits:"
grep -E "OU_ADX_THRESHOLD|OU_Z_ENTRY|Phase 9.7M" .env
echo ""

echo "===== STEP 3: FIX C+D — angel_adapter.py retries 4->2, backoff 30s->90s ====="
python3 << 'PYEOF1'
src = open('angel_adapter.py').read()
# Fix C: retries
old_c = 'for attempt in range(4):'
new_c = 'for attempt in range(2):  # Phase 9.7M: 4->2 retries to cap quota burn at 90s vs 450s'
if old_c not in src:
    raise SystemExit(f"FAIL: anchor '{old_c}' not found")
if src.count(old_c) != 1:
    raise SystemExit(f"FAIL: anchor not unique ({src.count(old_c)} occurrences)")
src = src.replace(old_c, new_c)
# Fix D: backoff
old_d = 'wait = (30 * (2 ** attempt)) + _random.uniform(0, 5)'
new_d = 'wait = (90 * (2 ** attempt)) + _random.uniform(0, 5)  # Phase 9.7M: 30s->90s past Angel per-min window'
if old_d not in src:
    raise SystemExit(f"FAIL: anchor '{old_d}' not found")
if src.count(old_d) != 1:
    raise SystemExit(f"FAIL: backoff anchor not unique ({src.count(old_d)} occurrences)")
src = src.replace(old_d, new_d)
open('angel_adapter.py', 'w').write(src)
print("OK angel_adapter.py patched (Fix C+D)")
PYEOF1
echo ""

echo "===== STEP 4: FIX E — ou_mrs.py:349 stagger 1.5s -> 2.5s ====="
python3 << 'PYEOF2'
src = open('ou_mrs.py').read()
old = 'time.sleep(1.5)  # Phase 9.7L: bump 0.4->1.5 (Angel getCandleData ~1 req/sec, 0.4 was insufficient)'
new = 'time.sleep(2.5)  # Phase 9.7M: bump 1.5->2.5 for extra margin with ADX=30 (more cycles needed)'
if old not in src:
    raise SystemExit(f"FAIL: stagger anchor not found")
if src.count(old) != 1:
    raise SystemExit(f"FAIL: stagger anchor not unique ({src.count(old)} occurrences)")
src = src.replace(old, new)
open('ou_mrs.py', 'w').write(src)
print("OK ou_mrs.py patched (Fix E)")
PYEOF2
echo ""

echo "===== STEP 5: py_compile sanity ====="
python3 -c "import py_compile; py_compile.compile('angel_adapter.py', doraise=True)" && echo "OK angel_adapter.py compiles"
python3 -c "import py_compile; py_compile.compile('ou_mrs.py', doraise=True)" && echo "OK ou_mrs.py compiles"
python3 -c "import py_compile; py_compile.compile('strategy.py', doraise=True)" && echo "OK strategy.py compiles"
echo ""

echo "===== STEP 6: env reload sanity ====="
python3 -c "
from dotenv import dotenv_values
v = dotenv_values('.env')
adx = float(v.get('OU_ADX_THRESHOLD', '0'))
z = float(v.get('OU_Z_ENTRY', '0'))
assert adx == 30.0, f'ADX={adx}, expected 30'
assert z == 1.4, f'Z={z}, expected 1.4'
print(f'OK ADX={adx} Z_ENTRY={z}')
"
echo ""

echo "===== STEP 7: code markers verify ====="
echo "Phase 9.7M markers in modified files:"
grep -n "Phase 9.7M" .env ou_mrs.py angel_adapter.py
echo ""

echo "===== STEP 8: bot will wake Monday 09:14 IST with new config ====="
systemctl list-timers ou-mrs.timer --no-pager | head -5
echo ""

echo "================================================"
echo "PHASE 9.7M DEPLOYMENT COMPLETE"
echo "================================================"
echo "TS=$TS PHASE=p97M"
echo ""
echo "Applied (evidence-based):"
echo "  Fix A: .env OU_ADX_THRESHOLD  35 -> 30  (sweep winner, commit b4bc29e)"
echo "  Fix B: .env OU_Z_ENTRY        1.5 -> 1.4 (sweep winner)"
echo "  Fix C: angel_adapter.py       4 -> 2 retries (cap quota burn)"
echo "  Fix D: angel_adapter.py       30s -> 90s initial backoff (past Angel window)"
echo "  Fix E: ou_mrs.py:349 stagger  1.5s -> 2.5s (extra margin)"
echo ""
echo "Expected on Monday 09:14 IST:"
echo "  - Bot wakes via timer with new config"
echo "  - Rate-limit storms suppressed (smaller retry budget, longer backoff)"
echo "  - More entry opportunities (ADX 30 vs 35) when market is chop/range"
echo "  - Same defensive behavior on trend days (regime filter still active)"
echo ""
echo "ROLLBACK (single paste):"
echo "  cp .env.bak.p97M.$TS .env"
echo "  cp ou_mrs.py.bak.p97M.$TS ou_mrs.py"
echo "  cp angel_adapter.py.bak.p97M.$TS angel_adapter.py"
echo ""

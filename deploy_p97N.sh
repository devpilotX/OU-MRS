#!/bin/bash
# Phase 9.7N — backtest-validated config (32, 1.5) + z_stop alignment to 3.5 across all symbols
TS=$(date +%s)
PHASE=p97N
die() { echo "FAIL: $1"; exit 1; }

echo "===== PHASE 9.7N DEPLOY @ $(date '+%H:%M:%S') IST ====="
echo "TS=$TS"
echo ""

echo "===== STEP 0: PRE-FLIGHT ====="
[ -f .env ] || die ".env missing"
grep -q '^OU_ADX_THRESHOLD=30$' .env || die ".env doesn't have ADX=30 (post-9.7M state)"
grep -q '^OU_Z_ENTRY=1.4$' .env || die ".env doesn't have Z_ENTRY=1.4"
grep -q '^OU_Z_STOP_BNF=2.5$' .env || die ".env doesn't have Z_STOP_BNF=2.5"
grep -q '^OU_Z_STOP_FNF=3.0$' .env || die ".env doesn't have Z_STOP_FNF=3.0"
if grep -q "Phase 9.7N" .env 2>/dev/null; then die "9.7N already applied"; fi
ACTIVE=$(systemctl is-active ou-mrs.service)
[ "$ACTIVE" = "inactive" ] || die "ou-mrs.service is $ACTIVE, must be inactive"
echo "OK pre-flight (post-9.7M state confirmed, bot inactive)"
echo ""

echo "===== STEP 1: BACKUP ====="
cp .env .env.bak.$PHASE.$TS || die "backup .env"
ls -la .env.bak.$PHASE.$TS
echo ""

echo "===== STEP 2: FIX A — OU_ADX_THRESHOLD 30 -> 32 ====="
sed -i 's/^OU_ADX_THRESHOLD=30$/OU_ADX_THRESHOLD=32/' .env
sed -i 's|^# Phase 9.7M (2026-05-15): revert to sweep winner from commit b4bc29e$|# Phase 9.7N (2026-05-15): sweep-validated optimum (32, 1.5) — PF 2.21 net +13748 (sweep_p97N_1778851948)|' .env
grep -q '^OU_ADX_THRESHOLD=32$' .env || die "ADX edit failed"
echo "OK ADX 30 -> 32"

echo "===== STEP 3: FIX B — OU_Z_ENTRY 1.4 -> 1.5 ====="
sed -i 's/^OU_Z_ENTRY=1.4$/OU_Z_ENTRY=1.5/' .env
sed -i 's|^# Phase 9.7M: backtest PF 1.29 with z=1.4 adx=30 (52d479a)$|# Phase 9.7N: 15-combo sweep + 9-combo refinement confirmed Z=1.5 dominates Z=1.4 by 75%% net PnL|' .env
grep -q '^OU_Z_ENTRY=1.5$' .env || die "Z_ENTRY edit failed"
echo "OK Z_ENTRY 1.4 -> 1.5"

echo "===== STEP 4: FIX C — OU_Z_STOP_BNF 2.5 -> 3.5 (backtest alignment) ====="
sed -i 's/^OU_Z_STOP_BNF=2.5$/OU_Z_STOP_BNF=3.5/' .env
grep -q '^OU_Z_STOP_BNF=3.5$' .env || die "Z_STOP_BNF edit failed"
echo "OK Z_STOP_BNF 2.5 -> 3.5"

echo "===== STEP 5: FIX D — OU_Z_STOP_FNF 3.0 -> 3.5 (backtest alignment) ====="
sed -i 's/^OU_Z_STOP_FNF=3.0$/OU_Z_STOP_FNF=3.5/' .env
grep -q '^OU_Z_STOP_FNF=3.5$' .env || die "Z_STOP_FNF edit failed"
echo "OK Z_STOP_FNF 3.0 -> 3.5"
echo ""

echo "===== STEP 6: VERIFICATION ====="
echo ".env trading config after Phase 9.7N:"
grep -E "^OU_ADX|^OU_Z_|^OU_REGIME|^OU_TRAIL" .env
echo ""

echo "===== STEP 7: SANITY BACKTEST AT 9.7N TARGET ====="
BT_ADX=32 BT_ZENTRY=1.5 BT_REGIME_FILTER=CHOP,RANGE timeout 90 venv/bin/python backtest.py 2>&1 | tail -8
echo ""

echo "===== STEP 8: TIMER STATUS ====="
systemctl list-timers ou-mrs.timer --no-pager
echo ""

echo "================================================"
echo "PHASE 9.7N DEPLOYMENT COMPLETE"
echo "================================================"
echo "TS=$TS PHASE=p97N"
echo ""
echo "Applied (backtest-validated):"
echo "  Fix A: OU_ADX_THRESHOLD  30   -> 32   (sweep PF 1.36 -> 2.21)"
echo "  Fix B: OU_Z_ENTRY        1.4  -> 1.5  (sweep net +75%)"
echo "  Fix C: OU_Z_STOP_BNF     2.5  -> 3.5  (backtest alignment)"
echo "  Fix D: OU_Z_STOP_FNF     3.0  -> 3.5  (backtest alignment)"
echo ""
echo "Expected backtest at deploy config (37 trading days BNF):"
echo "  trades=17, PF=2.21, net=+Rs 13748, sharpe=3.51, sortino=5.07, maxDD=-3.34%"
echo ""
echo "Expected on Monday 09:14 IST:"
echo "  - Bot wakes via timer with sweep-validated config"
echo "  - More selective entries (Z>=1.5 vs 1.4) on chop/range days"
echo "  - Tolerant stops on BNF (z_stop 2.5 -> 3.5) gives mean reversion more room"
echo "  - Same low rate-limit burn (9.7M retries/backoff/stagger preserved)"
echo ""
echo "ROLLBACK (single paste):"
echo "  cp .env.bak.p97N.$TS .env"
echo ""
echo "ROLLBACK ALL THE WAY TO PRE-9.7L (if needed):"
echo "  cp .env.bak.p97L.1778831019 .env"
echo "  cp ou_mrs.py.bak.p97L.1778831019 ou_mrs.py 2>/dev/null"
echo "  cp angel_adapter.py.bak.p97L.1778831019 angel_adapter.py 2>/dev/null"

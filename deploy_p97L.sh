#!/bin/bash
# Phase 9.7L deploy — Fix A (dashboard) + Fix B (stagger) + Fix C (ADX=35)
TS=$(date +%s)
PHASE=p97L
die() { echo "FAIL: $1"; exit 1; }

echo "===== PHASE 9.7L DEPLOY @ $(date '+%H:%M:%S') IST ====="
echo "TS=$TS"
echo ""

echo "===== STEP 0: PRE-FLIGHT ====="
[ -f .env ] || die ".env missing"
[ -f ou_mrs.py ] || die "ou_mrs.py missing"
[ -f dashboard/ws_tick_pump.py ] || die "ws_tick_pump.py missing"
grep -q '^OU_ADX_THRESHOLD=32$' .env || die ".env doesn't have ADX=32 baseline"
grep -q 'Phase 9.7k: stagger' ou_mrs.py || die "ou_mrs.py missing 9.7k marker"
if grep -q "Phase 9.7L" ou_mrs.py; then die "9.7L already applied to ou_mrs.py"; fi
if grep -q "Phase 9.7L" dashboard/ws_tick_pump.py; then die "9.7L already applied to ws_tick_pump.py"; fi
echo "OK pre-flight"
echo ""

echo "===== STEP 1: BACKUP ====="
cp .env .env.bak.$PHASE.$TS || die "backup .env"
cp ou_mrs.py ou_mrs.py.bak.$PHASE.$TS || die "backup ou_mrs.py"
cp dashboard/ws_tick_pump.py dashboard/ws_tick_pump.py.bak.$PHASE.$TS || die "backup ws_tick_pump.py"
ls -la .env.bak.$PHASE.$TS ou_mrs.py.bak.$PHASE.$TS dashboard/ws_tick_pump.py.bak.$PHASE.$TS
echo ""

echo "===== STEP 2: FIX A -- ws_tick_pump.py env gate ====="
venv/bin/python3 - <<'PYEOF1'
path = "dashboard/ws_tick_pump.py"
with open(path) as f: src = f.read()
old = "    def start(self) -> None:\n        if not self.token_map:"
new = (
    "    def start(self) -> None:\n"
    "        # Phase 9.7L: env gate releases Angel REST quota for bot\n"
    "        import os as _os_p97L\n"
    "        if _os_p97L.environ.get(\"DASHBOARD_LIVE_TICK\", \"1\") != \"1\":\n"
    "            log.warning(\"[ws_pump] disabled via DASHBOARD_LIVE_TICK=0 env var\")\n"
    "            return\n"
    "        if not self.token_map:"
)
if old not in src:
    print("FAIL: anchor missing"); raise SystemExit(1)
with open(path, "w") as f: f.write(src.replace(old, new, 1))
print("OK ws_tick_pump.py patched")
PYEOF1
[ $? -eq 0 ] || die "Fix A patch"
echo ""

echo "===== STEP 3: FIX B -- ou_mrs.py stagger 0.4 -> 1.5 ====="
venv/bin/python3 - <<'PYEOF2'
path = "ou_mrs.py"
with open(path) as f: src = f.read()
old = 'time.sleep(0.4)  # Phase 9.7k: stagger Angel API calls (3 req/sec limit, 157 rate-limits on 14 May)'
new = 'time.sleep(1.5)  # Phase 9.7L: bump 0.4->1.5 (Angel getCandleData ~1 req/sec, 0.4 was insufficient)'
if old not in src:
    print("FAIL: 9.7k anchor missing"); raise SystemExit(1)
with open(path, "w") as f: f.write(src.replace(old, new, 1))
print("OK ou_mrs.py patched")
PYEOF2
[ $? -eq 0 ] || die "Fix B patch"
echo ""

echo "===== STEP 4: FIX C -- .env updates ====="
sed -i 's/^OU_ADX_THRESHOLD=32$/OU_ADX_THRESHOLD=35/' .env || die "sed ADX"
grep -q '^OU_ADX_THRESHOLD=35$' .env || die "ADX update did not land"
if grep -q '^DASHBOARD_LIVE_TICK=' .env; then
  sed -i 's/^DASHBOARD_LIVE_TICK=.*$/DASHBOARD_LIVE_TICK=0/' .env
else
  echo 'DASHBOARD_LIVE_TICK=0' >> .env
fi
grep -q '^DASHBOARD_LIVE_TICK=0$' .env || die "TICK update did not land"
echo ".env after edits:"
grep -E '^OU_ADX_THRESHOLD=|^DASHBOARD_LIVE_TICK=' .env
echo ""

echo "===== STEP 5: py_compile ====="
venv/bin/python3 -m py_compile ou_mrs.py || die "ou_mrs.py compile"
echo "OK ou_mrs.py"
venv/bin/python3 -m py_compile dashboard/ws_tick_pump.py || die "ws_tick_pump.py compile"
echo "OK ws_tick_pump.py"
venv/bin/python3 -m py_compile dashboard/app.py || die "dashboard/app.py compile"
echo "OK dashboard/app.py"
echo ""

echo "===== STEP 6: env reload check ====="
venv/bin/python3 -c "from dotenv import dotenv_values; v=dotenv_values('.env'); t=float(v['OU_ADX_THRESHOLD']); d=v['DASHBOARD_LIVE_TICK']; assert t==35.0,'ADX bad'; assert d=='0','TICK bad'; print(f'OK ADX={t} DASHBOARD_LIVE_TICK={d}')"
[ $? -eq 0 ] || die "env reload"
echo ""

echo "===== STEP 7: BASELINE rate-limit count ====="
OLD_LOG=logs/ou_mrs_20260515_091400.log
if [ -f "$OLD_LOG" ]; then
  BASELINE=$(grep -c "RATE-LIMIT" "$OLD_LOG")
else
  BASELINE=0
fi
echo "Pre-restart rate-limits in $OLD_LOG: $BASELINE"
echo ""

echo "===== STEP 8: RESTART DASHBOARD ====="
sudo systemctl restart ou-mrs-dashboard.service || die "dashboard restart"
sleep 3
DASH=$(systemctl is-active ou-mrs-dashboard.service 2>/dev/null)
[ "$DASH" = "active" ] || die "dashboard not active: $DASH"
echo "OK dashboard active"
echo ""

echo "===== STEP 9: RESTART BOT ====="
sudo systemctl restart ou-mrs.service || die "bot restart"
sleep 5
BOT=$(systemctl is-active ou-mrs.service 2>/dev/null)
[ "$BOT" = "active" ] || die "bot not active: $BOT"
echo "OK bot active"
echo ""

echo "===== STEP 10: brief 30s watch ====="
sleep 30
NEW_LOG=$(ls -t logs/ou_mrs_*.log 2>/dev/null | head -1)
echo "NEW_LOG: $NEW_LOG"
echo "--- last 25 lines ---"
tail -25 "$NEW_LOG"
echo ""
echo "--- new RATE-LIMIT count in new log ---"
RL=$(grep -c "RATE-LIMIT" "$NEW_LOG" 2>/dev/null)
if [ -z "$RL" ]; then RL=0; fi
echo "$RL"
echo ""

echo "===== STEP 11: confirm pump disabled ====="
sudo journalctl -u ou-mrs-dashboard.service --since "1 min ago" --no-pager 2>/dev/null | grep -iE "ws_pump|disabled" | tail -5
echo ""

echo "================================================"
echo "PHASE 9.7L DEPLOYMENT COMPLETE"
echo "================================================"
echo "TS=$TS PHASE=$PHASE"
echo ""
echo "Applied:"
echo "  Fix A: ws_tick_pump.py env-gated (DASHBOARD_LIVE_TICK=0)"
echo "  Fix B: ou_mrs.py stagger 0.4s -> 1.5s"
echo "  Fix C: .env OU_ADX_THRESHOLD 32 -> 35 (target 2-3 trades)"
echo ""
echo "ROLLBACK:"
echo "  cp .env.bak.$PHASE.$TS .env"
echo "  cp ou_mrs.py.bak.$PHASE.$TS ou_mrs.py"
echo "  cp dashboard/ws_tick_pump.py.bak.$PHASE.$TS dashboard/ws_tick_pump.py"
echo "  sudo systemctl restart ou-mrs-dashboard.service ou-mrs.service"

#!/bin/bash
# Day-1 morning diagnostic for Phase 9.8 rollout.
# Run AFTER 09:14 IST start, anytime after 09:30 ideally.
# Usage: ssh to the VPS, then :  bash scripts/day1_review.sh

set +e
set +H
cd /home/ubuntu/bots/ou-mrs

echo "============================================"
echo " Day 1 morning review for Phase 9.8 filter"
echo " ========================================="
echo ""

echo "===== A. TIMER AND SERVICE STATE ====="
sudo systemctl status ou-mrs.timer --no-pager | head -6
echo "---"
sudo systemctl status ou-mrs.service --no-pager | head -15

echo ""
echo "===== B. git HEAD ====="
git log --oneline -1

echo ""
echo "===== C. PFM HALT STATE (must not be halted early) ====="
ls -la state/pfm_halt.json 2>/dev/null && cat state/pfm_halt.json || echo "(absent, clean start)"

echo ""
echo "===== D. REGIME FILTER CONFIRMATION IN JOURNAL ====="
# Search for signals that would have entered pre-filter but were rejected.
# Look for explicit Phase 9.8 gate log lines if any, or count entry rejection signatures.
sudo journalctl -u ou-mrs.service --since "09:14 today" --no-pager | tail -150 > /tmp/journal_today.txt
echo "--- last 150 lines from journal (saved to /tmp/journal_today.txt) ---"
tail -40 /tmp/journal_today.txt

echo ""
echo "--- entry related counts ---"
ENTRY_SIGNALS=$(grep -cE "(entry signal|signal triggered| BUY | SELL )" /tmp/journal_today.txt)
ENTRY_BLOCKS=$(grep -cE "(filtered out|regime_allow|blocked|reject|TREND|skip)" /tmp/journal_today.txt)
TRADES=$(grep -cE "(Order placed|POS=)" /tmp/journal_today.txt)
echo "entry related lines:  $ENTRY_SIGNALS"
echo "block reject lines: $ENTRY_BLOCKS"
echo "orders placed:      $TRADES"

echo ""
echo "===== E. BUG #2 PROOF POINT (check any NF NG FNF order had correct tradingsymbol) ====="
if [ -f trades.jsonl ]; then
  tail -10 trades.jsonl | python3 -c "import json,sys; [print(json.dumps({'instrument': j get('instrument','?'),'symbol': j.get('symbol',,'tradingsymbol'?)==[]'tradingsymbol', '?')})) for l in sys.stdin for j in [json.loads(l)]]" 2>/dev/null || tail -10 trades.jsonl
else
  echo "(trades.jsonl absent)"
fi

echo ""
echo "===== F. PHASE 9.8 PITON STATISTICS ====="
if [ -f bt_out/metrics.json ]; then
  echo "--- latest backtest snapshot ---"
  cat bt_out/metrics.json | python3 -m json.tool | head -15
fi

echo ""
echo "===== G. LIVE STATE FILES ====="
for f in state/live_BNF.json state/live_NF.json state/live_FNF.json; do
  if [ -f "$f" ]; then
    echo "--- $f ---"
    cat "$f" | python3 -m json.tool 2>/dev/null | head -20 || echo "(parse error)"
  fi
done

echo ""
echo "============================================"
echo " VERDICT:"
echo " Phase 9.8 filter working if: entry_related > 0 and block_reject > 0 and orders_placed < entry_related"
echo " Bug #2 fixed if: any NF or FNF orders have correct tradingsymbol (not BNF symbol)"
echo " ============================================"

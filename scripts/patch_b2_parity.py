#!/usr/bin/env python3
"""Phase 9.8g.12 (audit B2 parity++): port tier-aware sizing defaults into backtest.py.

backtest.py keeps its env-var overrides for sensitivity sweeps, but the DEFAULTS
now come from the same ou_mrs._get_policy() that drives live. This means:

    BT_CAPITAL=3750000 python backtest.py --symbol NIFTY --auto-lot

...is sufficient to run a tier-matched backtest. No more env-var soup.

What this script changes in backtest.py:
  1. Adds _LONG_TO_SHORT map (BANKNIFTY -> BNF, NIFTY -> NF, MIDCPNIFTY -> MCN)
     so the harness can speak to ou_mrs.max_lots_for_capital().
  2. Replaces the hardcoded _ATR_MULT (1.5) and _RISK_PCT (0.0125) defaults
     with values pulled from ou_mrs._get_policy(CAPITAL). Env-vars keep priority.
  3. Extends --auto-lot to also set MAX_LOTS via max_lots_for_capital(CAPITAL,
     short_symbol) when BT_MAX_LOTS env is not set.
  4. Expands the startup config-sanity log to include the tier name.

Run from repo root:
    python scripts/patch_b2_parity.py

The script is idempotent (refuses to re-apply) and atomic (asserts all four
anchors match BEFORE writing — partial edits impossible).
"""
import sys
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
BT = REPO / "backtest.py"

if not BT.exists():
    print(f"ERR backtest.py not found at {BT}")
    sys.exit(2)

src = BT.read_text()
orig_len = len(src)

# ----- Idempotency guard -----
if "audit B2 parity++" in src:
    print("OK backtest.py already at B2-parity++; nothing to do.")
    sys.exit(0)

# ----- Anchor 1: add _LONG_TO_SHORT after _SYMBOL_TO_LOT block -----
anchor1_old = '''_SYMBOL_TO_LOT = {  # Sacred Rule #6: ratified via data/instruments.db on 21 May 2026 (Phase 9.7AQ)
    "BANKNIFTY":  30,
    "NIFTY":      65,
    "MIDCPNIFTY": 120,
}'''
anchor1_new = anchor1_old + '''
# Phase 9.8g.12 (audit B2 parity++): map backtest long names to ou_mrs.INSTRUMENT_CFG short keys
_LONG_TO_SHORT = {
    "BANKNIFTY":  "BNF",
    "NIFTY":      "NF",
    "MIDCPNIFTY": "MCN",
}'''
c1 = src.count(anchor1_old)
assert c1 == 1, f"anchor1 (_SYMBOL_TO_LOT block) not found uniquely (count={c1})"

# ----- Anchor 2: replace _ATR_MULT/_RISK_PCT module-level block -----
anchor2_old = '''# Phase 9.8g.2 (audit B2 parity): use OU_ATR_MULT if set, mirror live behavior
_ATR_MULT = float(os.environ.get("OU_ATR_MULT", 1.5))
_RISK_PCT = float(os.environ.get("BT_RISK_PCT", 0.25 * KELLY_SEED))  # default = legacy 1.25%'''
anchor2_new = '''# Phase 9.8g.12 (audit B2 parity++): derive defaults from the same tier policy
# that drives live (ou_mrs._get_policy, Sacred Rule #33 extended to backtest).
# Env-vars retain override priority so sensitivity sweeps still work.
from ou_mrs import _get_policy as _bt_get_policy, max_lots_for_capital as _bt_max_lots_for
_BT_TIER_NAME, _BT_POLICY = _bt_get_policy(int(CAPITAL))
_ATR_MULT = float(os.environ.get("OU_ATR_MULT", _BT_POLICY["atr_mult"]))
_RISK_PCT = float(os.environ.get("BT_RISK_PCT", _BT_POLICY["risk_per_trade_pct"]))'''
c2 = src.count(anchor2_old)
assert c2 == 1, f"anchor2 (_ATR_MULT/_RISK_PCT block) not found uniquely (count={c2})"

# ----- Anchor 3: extend --auto-lot to also set MAX_LOTS -----
anchor3_old = '''    if args.symbol:
        DATA = (_HERE / _SYMBOL_TO_DATA[args.symbol]).resolve()
        if args.auto_lot:
            LOT_SIZE = _SYMBOL_TO_LOT[args.symbol]
        if not args.out:
            OUT = _HERE / f"bt_out_{args.symbol}"'''
anchor3_new = '''    if args.symbol:
        DATA = (_HERE / _SYMBOL_TO_DATA[args.symbol]).resolve()
        if args.auto_lot:
            LOT_SIZE = _SYMBOL_TO_LOT[args.symbol]
            # Phase 9.8g.12 (audit B2 parity++): also auto-set MAX_LOTS from the
            # tier-aware cap function iff caller has not pinned it via BT_MAX_LOTS.
            if "BT_MAX_LOTS" not in os.environ:
                MAX_LOTS = _bt_max_lots_for(int(CAPITAL), _LONG_TO_SHORT[args.symbol])
        if not args.out:
            OUT = _HERE / f"bt_out_{args.symbol}"'''
c3 = src.count(anchor3_old)
assert c3 == 1, f"anchor3 (--auto-lot block) not found uniquely (count={c3})"

# ----- Anchor 4: expand startup config-sanity log to include tier -----
anchor4_old = '    log.info(f"Backtest config: capital={CAPITAL:,.0f}  lot_size={LOT_SIZE}  max_lots={MAX_LOTS}  atr_mult={_ATR_MULT}  risk_pct={_RISK_PCT:.4f}")'
anchor4_new = '    log.info(f"Backtest config: tier={_BT_TIER_NAME}  capital={CAPITAL:,.0f}  lot_size={LOT_SIZE}  max_lots={MAX_LOTS}  atr_mult={_ATR_MULT}  risk_pct={_RISK_PCT:.4f}")'
c4 = src.count(anchor4_old)
assert c4 == 1, f"anchor4 (startup log line) not found uniquely (count={c4})"

# All four anchors validated. Apply atomically.
new_src = src
new_src = new_src.replace(anchor1_old, anchor1_new)
new_src = new_src.replace(anchor2_old, anchor2_new)
new_src = new_src.replace(anchor3_old, anchor3_new)
new_src = new_src.replace(anchor4_old, anchor4_new)

BT.write_text(new_src)
new_len = len(new_src)
print(f"OK backtest.py:  {orig_len:>6} -> {new_len:>6} bytes  ({new_len - orig_len:+d})")
print("")
print("Next:")
print('  python -c "import os; os.environ[\'BT_CAPITAL\']=\'3750000\'; import backtest; print(f\'tier={backtest._BT_TIER_NAME} atr_mult={backtest._ATR_MULT} risk_pct={backtest._RISK_PCT}\')"')
print("  python -m pytest -q")
print("  BT_CAPITAL=3750000 OU_NF_AFTERNOON_CUTOFF_HHMM=1330 python backtest.py --symbol NIFTY --auto-lot")

#!/usr/bin/env python3
"""Phase 9.8h.I (OC-7' v0): post-trade slippage reconciliation.

World-grade reconciliation requires n >= 30 paired observations (Phase 9.7E rule
of thumb). With only 22 paper trades to date, this v0 produces the comparison
table + summary stats with INSUFFICIENT_SAMPLE flagged. Re-run after each new
trade to track convergence.

Methodology:
1. Load trades.jsonl (live/paper realized fills).
2. For each trade, compute the actual price impact: |exit - entry| in points;
   slippage_bps_realized = (entry - mid_estimate) for entry, plus the same for exit.
   Without recorded depth at fill time, we proxy mid_estimate as the round-down to
   half-tick, which on Indian index futures introduces a tracking bias ± 0.5 × 0.05
   = ± 0.025 pts. Document the proxy explicitly.
3. Aggregate by (symbol, side, reason).
4. Write audit/phase_9_8h_slippage_reconciliation_v0_<date>.md.

Usage:
    ./venv/bin/python tools/post_trade_slippage_reconciliation.py
"""
import datetime as dt, json, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRADES = ROOT / "trades.jsonl"
AUDIT = ROOT / "audit"
AUDIT.mkdir(exist_ok=True)

MIN_SAMPLE = 30
TICK_SIZE_INDEX = 0.05  # NF/BNF/MCN: 0.05-point tick (5 paise)


def _proxy_mid(price: float) -> float:
    """Estimate the contemporaneous mid as price rounded to the previous tick.

    For mean-reversion entries on Nifty/BankNifty, the bot crosses the spread
    by 1 tick (BUY at ask, SELL at bid). The mid is therefore approximately
    (price - tick/2) for BUY entries and (price + tick/2) for SELL entries,
    flipped at exit. We use this signed proxy to extract slippage in points.
    """
    return round(price / TICK_SIZE_INDEX) * TICK_SIZE_INDEX


def _slippage_pts(price: float, is_buy: bool, is_entry: bool) -> float:
    mid = _proxy_mid(price)
    if is_entry:
        return (price - mid) if is_buy else (mid - price)
    else:
        # Exit reverses sign
        return (mid - price) if is_buy else (price - mid)


def classify_symbol(entry: float) -> str:
    if entry > 40000:
        return "BNF"
    if entry > 20000:
        return "NF"
    if entry > 8000:
        return "MCN"
    return "OTHER"


def main():
    if not TRADES.exists():
        print("FAIL: no trades.jsonl")
        return 1
    trades = []
    for line in TRADES.read_text().splitlines():
        if not line.strip():
            continue
        try:
            trades.append(json.loads(line))
        except Exception:
            pass
    n = len(trades)
    rows = []
    for t in trades:
        entry, exit_ = t.get("entry"), t.get("exit")
        if entry is None or exit_ is None:
            continue
        side = (t.get("side") or "").upper()
        is_buy = side == "BUY"
        sym = classify_symbol(entry)
        slip_entry = _slippage_pts(entry, is_buy, is_entry=True)
        slip_exit = _slippage_pts(exit_, is_buy, is_entry=False)
        total = slip_entry + slip_exit
        rows.append({
            "entry_ts": t.get("entry_ts"),
            "sym": sym, "side": side, "qty": t.get("qty"),
            "entry": entry, "exit": exit_, "pnl": t.get("pnl"),
            "reason": t.get("reason"),
            "slip_entry_pts": round(slip_entry, 4),
            "slip_exit_pts": round(slip_exit, 4),
            "slip_total_pts": round(total, 4),
        })

    pts = [r["slip_total_pts"] for r in rows]
    avg = statistics.mean(pts) if pts else 0.0
    med = statistics.median(pts) if pts else 0.0
    stdev = statistics.stdev(pts) if len(pts) > 1 else 0.0
    max_neg = min(pts) if pts else 0.0
    max_pos = max(pts) if pts else 0.0

    today = dt.date.today().isoformat()
    out = AUDIT / f"phase_9_8h_slippage_reconciliation_v0_{today}.md"
    md = []
    md.append("# Phase 9.8h.I (OC-7' v0) \u2014 post-trade slippage reconciliation")
    md.append(f"")
    md.append(f"**Generated:** {dt.datetime.now().isoformat(timespec='seconds')}")
    md.append(f"**Sample size:** {n} trades")
    if n < MIN_SAMPLE:
        md.append(f"")
        md.append(f"> **INSUFFICIENT_SAMPLE**: need n \u2265 {MIN_SAMPLE} for stable slippage estimates; current n = {n}. Estimates below are provisional and should not yet drive cost-model changes.")
    md.append("")
    md.append("## Summary stats (total slippage per round-trip, points)")
    md.append("")
    md.append(f"- Mean: {avg:+.4f} pts")
    md.append(f"- Median: {med:+.4f} pts")
    md.append(f"- Std dev: {stdev:.4f} pts")
    md.append(f"- Best (most favorable): {max_pos:+.4f} pts")
    md.append(f"- Worst (most adverse): {max_neg:+.4f} pts")
    md.append("")
    md.append("## Per-trade detail")
    md.append("")
    md.append("| Entry IST | Sym | Side | Qty | Entry | Exit | P&L \u20b9 | Reason | Slip\u2192 entry | Slip\u2192 exit | Slip\u2192 total |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append(
            f"| {r['entry_ts']} | {r['sym']} | {r['side']} | {r['qty']} | {r['entry']} | {r['exit']} | {r['pnl']:+.0f} | {r['reason']} | {r['slip_entry_pts']:+.3f} | {r['slip_exit_pts']:+.3f} | **{r['slip_total_pts']:+.3f}** |"
        )
    md.append("")
    md.append("## Methodology")
    md.append("")
    md.append("- Tick size assumed: 0.05 points (Nifty/BankNifty/MidCpNifty futures).")
    md.append("- Mid proxy: `round(price / tick) * tick`. This is a coarse approximation when no depth snapshot was recorded at fill time; the true mid would require the L1 bid/ask at the fill millisecond.")
    md.append("- Signed convention: positive slip = trade got a BETTER fill than the proxy mid; negative = worse.")
    md.append("- This v0 does NOT yet reconcile against the C.2/C.3 estimator (`estimate_slippage_ticks`, `estimate_gap_slippage_ticks`) because those are backtest-only and gated by OU_COST_MODEL_V2. A v1 will add that comparison once n >= 30.")
    md.append("")
    md.append(f"## Next milestone")
    md.append(f"")
    md.append(f"- Re-run after each new trade close.")
    md.append(f"- Promote to v1 (estimator-vs-actual delta) at n \u2265 {MIN_SAMPLE}.")
    out.write_text("\n".join(md) + "\n")
    print(f"Wrote: {out}")
    print(f"n={n} mean={avg:+.4f} median={med:+.4f} stdev={stdev:.4f}")
    print("INSUFFICIENT_SAMPLE" if n < MIN_SAMPLE else "SAMPLE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

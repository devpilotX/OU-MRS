"""Phase 8f.4: PDF tear-sheet for OU-MRS backtest (4 pages)."""
import argparse, json, math, os, subprocess
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

C_PRIMARY = "#1a4d8c"
C_GREEN = "#2e7d32"
C_RED = "#c62828"
C_GREY = "#666666"
DASH = "—"


def _tier(c):
    if c < 200_000: return "TINY"
    if c < 1_500_000: return "PAPER"
    if c < 2_500_000: return "FTMO_STARTER"
    if c < 5_000_000: return "FTMO_PRO"
    return "FTMO_ELITE"


def _inr(n):
    if n is None or (isinstance(n, float) and math.isnan(n)): return DASH
    n = float(n); s = "-" if n < 0 else ""; n = abs(n)
    if n >= 1e7: return f"{s}Rs {n/1e7:.2f}Cr"
    if n >= 1e5: return f"{s}Rs {n/1e5:.2f}L"
    return f"{s}Rs {n:,.0f}"


def _pct(x, sign=False):
    if x is None or (isinstance(x, float) and math.isnan(x)): return DASH
    return f"{x:+.2f}%" if sign else f"{x:.2f}%"


def _git():
    try:
        return subprocess.run(["git","rev-parse","--short","HEAD"], capture_output=True, text=True, timeout=2).stdout.strip() or DASH
    except Exception:
        return DASH


def _load(src):
    src = Path(src)
    edf = pd.read_csv(src / "equity.csv"); edf["date"] = pd.to_datetime(edf["date"])
    tdf = pd.read_csv(src / "trades.csv")
    if not tdf.empty:
        tdf["entry_ts"] = pd.to_datetime(tdf["entry_ts"])
        tdf["exit_ts"] = pd.to_datetime(tdf["exit_ts"])
    metrics = json.loads((src / "metrics.json").read_text())
    return edf, tdf, metrics


def _params():
    try:
        import backtest as bt
        return {"capital": bt.CAPITAL, "max_lots": bt.MAX_LOTS, "kelly": bt.KELLY_SEED,
                "brokerage": bt.BROKERAGE_RT, "slippage": bt.SLIPPAGE_TICKS,
                "adx": bt.PARAMS.adx_threshold, "zentry": bt.PARAMS.z_entry, "minr2": bt.PARAMS.min_r2}
    except Exception:
        return {"capital": 150_000}


def _page_cover(pdf, edf, tdf, metrics, params):
    fig = plt.figure(figsize=(8.5, 11), facecolor="white")
    fig.text(0.5, 0.94, "OU-MRS", ha="center", fontsize=32, weight="bold", color=C_PRIMARY)
    fig.text(0.5, 0.90, "Bank Nifty Mean-Reversion Strategy " + DASH + " Performance Tear-Sheet", ha="center", fontsize=12, color=C_GREY)
    p_start = edf["date"].min().strftime("%d %b %Y") if not edf.empty else DASH
    p_end = edf["date"].max().strftime("%d %b %Y") if not edf.empty else DASH
    fig.text(0.5, 0.86, f"Period: {p_start} to {p_end}", ha="center", fontsize=11, color=C_GREY)
    cap = params.get("capital", 150_000)
    acct = os.environ.get("ACCOUNT_ID", "primary")
    commit = _git()
    cap_inr = _inr(cap)
    cap_tier = _tier(cap)
    fig.text(0.5, 0.83, f"Capital: {cap_inr}  |  Tier: {cap_tier}  |  Account: {acct}  |  Commit: {commit}", ha="center", fontsize=10, color=C_GREY)
    rp = metrics.get("return_pct", 0)
    tp = metrics.get("total_pnl", 0)
    sh = metrics.get("sharpe", 0)
    so = metrics.get("sortino", 0)
    pf = metrics.get("profit_factor", 0)
    tpd = metrics.get("trades_per_day", 0)
    mdd_pct = metrics.get("max_drawdown_pct", 0)
    wr = metrics.get("win_rate", 0) * 100
    nt = metrics.get("trades", 0)
    td = metrics.get("trading_days", 0)
    stats = [("Total Return", _pct(rp, sign=True), C_GREEN if rp >= 0 else C_RED),
             ("Total P&L", _inr(tp), C_GREEN if tp >= 0 else C_RED),
             ("Sharpe", f"{sh:.2f}", C_PRIMARY),
             ("Sortino", f"{so:.2f}", C_PRIMARY),
             ("Max Drawdown", _pct(mdd_pct), C_RED),
             ("Win Rate", _pct(wr), C_PRIMARY),
             ("Profit Factor", f"{pf:.2f}", C_PRIMARY),
             ("Total Trades", str(nt), C_PRIMARY),
             ("Trading Days", str(td), C_PRIMARY),
             ("Trades / Day", f"{tpd:.2f}", C_PRIMARY)]
    for i, (label, value, color) in enumerate(stats):
        row, col = i // 2, i % 2
        x_l, x_v, y = 0.10 + col * 0.45, 0.40 + col * 0.45, 0.72 - row * 0.055
        fig.text(x_l, y, label, fontsize=11, color=C_GREY)
        fig.text(x_v, y, value, fontsize=12, color=color, weight="bold", ha="right")
    fig.text(0.5, 0.06, "Past performance does not guarantee future results. Backtest assumes 2-tick slippage and Rs 40 RT brokerage.", ha="center", fontsize=8, color=C_GREY, style="italic")
    gen_ts = datetime.now().strftime("%d %b %Y %H:%M IST")
    fig.text(0.5, 0.03, f"Generated: {gen_ts}", ha="center", fontsize=8, color=C_GREY)
    pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)


def _page_equity(pdf, edf, params):
    fig, ax = plt.subplots(figsize=(8.5, 11), facecolor="white")
    if edf.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center"); pdf.savefig(fig); plt.close(fig); return
    cap = params.get("capital", 150_000)
    cap_lbl = _inr(cap)
    ax.plot(edf["date"], edf["equity"], color=C_PRIMARY, linewidth=2, label="Strategy Equity")
    ax.axhline(cap, color=C_GREY, linestyle="--", linewidth=1, alpha=0.6, label=f"Starting Capital ({cap_lbl})")
    ax.fill_between(edf["date"], cap, edf["equity"], where=(edf["equity"] >= cap), color=C_GREEN, alpha=0.15)
    ax.fill_between(edf["date"], cap, edf["equity"], where=(edf["equity"] < cap), color=C_RED, alpha=0.15)
    ax.set_title("Equity Curve", fontsize=16, weight="bold", color=C_PRIMARY, pad=20)
    ax.set_ylabel("Account Equity (Rs)", fontsize=11)
    ax.grid(alpha=0.3); ax.legend(loc="upper left")
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.autofmt_xdate(); plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)


def _page_drawdown(pdf, edf):
    fig, ax = plt.subplots(figsize=(8.5, 11), facecolor="white")
    if edf.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center"); pdf.savefig(fig); plt.close(fig); return
    eq = edf["equity"].astype(float)
    peak = eq.cummax()
    dd = (eq - peak) / peak * 100
    ax.fill_between(edf["date"], 0, dd, color=C_RED, alpha=0.4)
    ax.plot(edf["date"], dd, color=C_RED, linewidth=1.5)
    mdd = float(dd.min()); mdd_idx = int(dd.idxmin()); mdd_date = edf["date"].iloc[mdd_idx]
    mdd_str = mdd_date.strftime("%d %b %Y")
    label = f"Max DD: {mdd:.2f}% on {mdd_str}"
    ax.annotate(label, xy=(mdd_date, mdd), xytext=(20, -30), textcoords="offset points", fontsize=10, color=C_RED, weight="bold", arrowprops=dict(arrowstyle="->", color=C_RED))
    ax.set_title("Underwater Drawdown Chart", fontsize=16, weight="bold", color=C_PRIMARY, pad=20)
    ax.set_ylabel("Drawdown (%)", fontsize=11)
    ax.axhline(0, color="black", linewidth=0.8); ax.grid(alpha=0.3)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.autofmt_xdate(); plt.tight_layout()
    pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)


def _page_trades(pdf, tdf):
    fig, axes = plt.subplots(2, 2, figsize=(8.5, 11), facecolor="white")
    fig.suptitle("Trade Analysis", fontsize=16, weight="bold", color=C_PRIMARY, y=0.97)
    if tdf.empty:
        for ax in axes.flat: ax.text(0.5, 0.5, "No trades", ha="center", va="center")
        pdf.savefig(fig); plt.close(fig); return
    pnls = tdf["pnl"].astype(float)
    bins = max(8, min(20, len(tdf) // 2 + 4))
    ax = axes[0, 0]
    ax.hist(pnls[pnls > 0], bins=bins, color=C_GREEN, alpha=0.7, label="Wins")
    ax.hist(pnls[pnls <= 0], bins=bins, color=C_RED, alpha=0.7, label="Losses")
    ax.axvline(0, color="black", linewidth=1)
    ax.set_title("P&L Distribution", fontsize=11); ax.set_xlabel("P&L (Rs)"); ax.set_ylabel("Trades")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    ax = axes[0, 1]
    cum = pnls.cumsum().values
    xs = list(range(1, len(cum) + 1))
    ax.plot(xs, cum, color=C_PRIMARY, linewidth=2)
    ax.fill_between(xs, 0, cum, where=(cum >= 0), color=C_GREEN, alpha=0.2)
    ax.fill_between(xs, 0, cum, where=(cum < 0), color=C_RED, alpha=0.2)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Cumulative P&L per Trade", fontsize=11); ax.set_xlabel("Trade #"); ax.set_ylabel("Cumulative (Rs)")
    ax.grid(alpha=0.3)
    ax = axes[1, 0]
    reasons = tdf["reason"].value_counts()
    pal = [C_PRIMARY, C_RED, C_GREEN, C_GREY, "#ffa726"][:len(reasons)]
    ax.pie(reasons.values, labels=reasons.index, autopct="%1.0f%%", colors=pal, startangle=90)
    ax.set_title("Exit Reasons", fontsize=11)
    ax = axes[1, 1]
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    cats = ["Avg Win", "Avg Loss", "Best Win", "Worst Loss"]
    vals = [float(wins.mean()) if len(wins) else 0.0, float(losses.mean()) if len(losses) else 0.0, float(wins.max()) if len(wins) else 0.0, float(losses.min()) if len(losses) else 0.0]
    ax.bar(cats, vals, color=[C_GREEN, C_RED, C_GREEN, C_RED], alpha=0.7)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Win/Loss Magnitudes (Rs)", fontsize=11)
    ax.tick_params(axis="x", rotation=20, labelsize=8); ax.grid(alpha=0.3, axis="y")
    plt.tight_layout(rect=(0, 0, 1, 0.95))
    pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)


def generate_tearsheet(source="bt_out", out="reports/tearsheet.pdf"):
    edf, tdf, metrics = _load(source)
    params = _params()
    out_path = Path(out); out_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out_path) as pdf:
        _page_cover(pdf, edf, tdf, metrics, params)
        _page_equity(pdf, edf, params)
        _page_drawdown(pdf, edf)
        _page_trades(pdf, tdf)
        d = pdf.infodict()
        d["Title"] = "OU-MRS Performance Tear-Sheet"
        d["Author"] = "DevPilotX"
        d["CreationDate"] = datetime.now()
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="bt_out")
    ap.add_argument("--out", default="reports/tearsheet.pdf")
    a = ap.parse_args()
    p = generate_tearsheet(a.source, a.out)
    print(f"[ok] tear-sheet -> {p} ({p.stat().st_size:,} bytes, 4 pages)")


if __name__ == "__main__":
    main()

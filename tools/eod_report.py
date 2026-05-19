#!/usr/bin/env python3
"""Phase 9.7AD: End-of-Day report for OU-MRS.
Runs at 15:35 IST via ou-mrs-eod.timer. Reads trades.jsonl + state/.
No sudo / no journalctl dependency."""
import json, os, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent.parent
EOD_DIR = ROOT / "bt_out" / "eod"
EOD_DIR.mkdir(parents=True, exist_ok=True)

today = datetime.now(IST).strftime("%Y-%m-%d")
report_path = EOD_DIR / f"{today}.md"

def read_jsonl(path):
    if not path.exists(): return []
    out = []
    for line in path.read_text().splitlines():
        try: out.append(json.loads(line))
        except: pass
    return out

def fmt_inr(n):
    try: return f"Rs {n:+,.2f}"
    except: return str(n)

all_trades = read_jsonl(ROOT / "trades.jsonl")
today_trades = [t for t in all_trades if str(t.get("entry_ts","")).startswith(today)]
total_pnl = sum(t.get("pnl", 0) for t in today_trades)
wins = [t for t in today_trades if t.get("pnl", 0) > 0]
losses = [t for t in today_trades if t.get("pnl", 0) <= 0]

# Reason distribution from trades.jsonl (lifetime)
reasons_lifetime = {}
for t in all_trades:
    r = t.get("reason", "?")
    reasons_lifetime[r] = reasons_lifetime.get(r, 0) + 1

pfm = {}
try:
    p = ROOT / "state" / "pfm_state.json"
    if p.exists(): pfm = json.loads(p.read_text())
except: pass

live = {}
for s in ('BNF','NF','MCN'):
    try:
        p = ROOT / "state" / f"live_{s}.json"
        if p.exists(): live[s] = json.loads(p.read_text())
    except: pass

git_head = ""
try:
    git_head = subprocess.run(["git","log","--oneline","-1"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10).stdout.strip()
except: pass

svc_active = "unknown"
try:
    svc_active = subprocess.run(["systemctl","is-active","ou-mrs.service"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
except: pass

# Active OU_* env overrides from .env
env_overrides = {}
envf = ROOT / ".env"
if envf.exists():
    for line in envf.read_text().splitlines():
        line = line.strip()
        if line.startswith("OU_") and "=" in line:
            k, v = line.split("=", 1)
            env_overrides[k] = v

R = []
R.append(f"# OU-MRS End-of-Day Report  {today}")
R.append("")
R.append(f"Generated: {datetime.now(IST).strftime('%H:%M:%S IST')}  |  HEAD: `{git_head}`  |  Service: `{svc_active}`")
R.append("")

R.append("## Today's trades")
R.append("")
if today_trades:
    R.append("| # | Side | Lots | Entry | Exit | PnL | Reason | Held (min) |")
    R.append("|---|---|---|---|---|---|---|---|")
    for i, t in enumerate(today_trades, 1):
        try:
            from datetime import datetime as dt
            ets = t.get("entry_ts",""); xts = t.get("exit_ts","")
            held = "?" 
            if ets and xts:
                e = dt.fromisoformat(ets); x = dt.fromisoformat(xts)
                held = f"{(x-e).total_seconds()/60:.0f}"
        except: held = "?"
        R.append(f"| {i} | {t.get('side','?')} | {t.get('qty','?')} | "
                  f"{t.get('entry','?'):.2f} | {t.get('exit','?'):.2f} | "
                  f"{fmt_inr(t.get('pnl',0))} | {t.get('reason','?')} | {held} |")
    R.append("")
    R.append(f"**Total: {len(today_trades)} trade(s), {len(wins)}W/{len(losses)}L, "
              f"PnL = {fmt_inr(total_pnl)}**")
else:
    R.append("_No trades today._")

R.append("")
R.append("## Lifetime exit-reason distribution (trades.jsonl)")
R.append("")
if reasons_lifetime:
    total = sum(reasons_lifetime.values())
    R.append("| Reason | Count | % |")
    R.append("|---|---|---|")
    for r, c in sorted(reasons_lifetime.items(), key=lambda x: -x[1]):
        R.append(f"| {r} | {c} | {c/total*100:.1f}% |")
else:
    R.append("_No trades on record._")

R.append("")
R.append("## End-of-day live state")
R.append("")
if live:
    R.append("| Symbol | z | LTP | in_trade |")
    R.append("|---|---|---|---|")
    for s, d in live.items():
        R.append(f"| {s} | {d.get('z','?'):+.3f} | {d.get('ltp','?')} | {d.get('in_trade', False)} |")

R.append("")
R.append("## Active env overrides (.env)")
R.append("")
if env_overrides:
    for k, v in env_overrides.items():
        R.append(f"- `{k}={v}`")

R.append("")
R.append("## PFM state")
R.append("")
if pfm:
    R.append(f"- peak_equity: {fmt_inr(pfm.get('peak_equity', 0))}")
    R.append(f"- cumulative_pnl: {fmt_inr(pfm.get('cumulative_pnl', 0))}")
    R.append(f"- days_traded: {pfm.get('days_traded', 0)}")
    R.append(f"- profit_target_progress: {pfm.get('profit_target_progress', 0)}")
    R.append(f"- consistency_frac: {pfm.get('consistency_frac', 0)}")
    R.append(f"- best_day_pnl: {fmt_inr(pfm.get('best_day_pnl', 0))}")

text = "\n".join(R) + "\n"
report_path.write_text(text)
print(text)
print(f"[eod] Report saved -> {report_path}")

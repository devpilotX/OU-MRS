#!/usr/bin/env python3
"""Phase 9.7U: Auto FUT-token sweep.

Reads data/instruments.db, finds nearest-expiry FUTIDX tokens for
BANKNIFTY / NIFTY / MIDCPNIFTY (and FINNIFTY if active), compares against
.env values, and optionally rewrites .env surgically.

Usage:
  venv/bin/python tools/fut_token_sweep.py             # dry-run (default)
  venv/bin/python tools/fut_token_sweep.py --refresh   # re-sync scrip master first
  venv/bin/python tools/fut_token_sweep.py --write     # commit to .env
  venv/bin/python tools/fut_token_sweep.py --refresh --write
  venv/bin/python tools/fut_token_sweep.py --include-fnf  # also rewrite FNF if active
"""
import argparse, datetime, sqlite3, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "instruments.db"
ENV = ROOT / ".env"
SYNC = ROOT / "scripts" / "sync_instruments.py"

UNDERLYINGS = [
    ("BANKNIFTY",  "BANKNIFTY",  "BNF"),
    ("NIFTY",      "NIFTY",      "NF"),
    ("MIDCPNIFTY", "MIDCPNIFTY", "MCN"),
    ("FINNIFTY",   "FINNIFTY",   "FNF"),
]

MON = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

def parse_expiry(s):
    try:
        return datetime.date(int(s[5:9]), MON[s[2:5].upper()], int(s[:2]))
    except Exception:
        return None

def load_active_aliases():
    for line in ENV.read_text().splitlines():
        s = line.strip()
        if s.startswith("INSTRUMENTS="):
            return set(x.strip() for x in s.split("=", 1)[1].split(",") if x.strip())
    return set()

def load_env_value(prefix, kind):
    key = prefix + "_FUT_" + kind
    for line in ENV.read_text().splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        if s.startswith(key + "="):
            return s.split("=", 1)[1].split("#")[0].strip()
    return None

def query_nearest(today):
    out = {}
    conn = sqlite3.connect(str(DB))
    try:
        for name, prefix, alias in UNDERLYINGS:
            rows = conn.execute(
                "SELECT token, symbol, expiry, lot_size FROM instruments "
                "WHERE instrument_type=? AND name=? AND exchange=?",
                ("FUTIDX", name, "NFO"),
            ).fetchall()
            cand = []
            for tok, sym, exp, lot in rows:
                d = parse_expiry(exp)
                if d is None:
                    continue
                cand.append((d, tok, sym, exp, lot))
            cand.sort()
            future = [c for c in cand if c[0] >= today]
            if future:
                out[name] = future[0]
    finally:
        conn.close()
    return out

def rewrite_env(updates):
    text = ENV.read_text()
    ts = int(time.time())
    backup = ENV.parent / (".env.bak.p97U." + str(ts))
    backup.write_text(text)
    new_lines = []
    written = set()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            new_lines.append(line)
            continue
        matched = None
        for key in updates:
            if s.startswith(key + "="):
                matched = key
                break
        if matched:
            new_lines.append(matched + "=" + updates[matched])
            written.add(matched)
        else:
            new_lines.append(line)
    missing = [k for k in updates if k not in written]
    if missing:
        new_lines.append("")
        new_lines.append("# Phase 9.7U auto-appended " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M IST"))
        for k in missing:
            new_lines.append(k + "=" + updates[k])
    ENV.write_text(chr(10).join(new_lines) + chr(10))
    return str(backup)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--include-fnf", action="store_true")
    args = ap.parse_args()
    if args.refresh:
        print("[refresh] re-syncing scrip master...")
        r = subprocess.run([sys.executable, str(SYNC)], cwd=str(ROOT))
        if r.returncode != 0:
            print("FAIL: sync_instruments exit=" + str(r.returncode))
            sys.exit(1)
    if not DB.exists():
        print("FAIL: " + str(DB) + " missing. Re-run with --refresh.")
        sys.exit(1)
    today = datetime.date.today()
    print("Today: " + today.isoformat() + " (" + today.strftime("%A") + ")")
    active = load_active_aliases()
    print("Active in .env INSTRUMENTS: " + ",".join(sorted(active)))
    print()
    nearest = query_nearest(today)
    hdr = "{:11} {:5} {:14} {:14} {:23} {:23} {:10} {}".format("UNDERLYING","ALIAS","CUR_TOKEN","NEW_TOKEN","CUR_SYMBOL","NEW_SYMBOL","EXPIRY","STATUS")
    print(hdr)
    print("-" * len(hdr))
    updates = {}
    for name, prefix, alias in UNDERLYINGS:
        if name not in nearest:
            print("{:11} {:5} (no FUTIDX rows in DB)".format(name, alias))
            continue
        d, tok_new, sym_new, exp, lot = nearest[name]
        tok_cur = load_env_value(prefix, "TOKEN") or "(missing)"
        sym_cur = load_env_value(prefix, "SYMBOL") or "(missing)"
        is_active = alias in active or (alias == "FNF" and args.include_fnf)
        if not is_active:
            status = "INACTIVE"
        elif tok_cur == tok_new and sym_cur == sym_new:
            status = "OK"
        elif sym_cur == "(missing)" and tok_cur == tok_new:
            status = "SYMBOL-MISSING"
        else:
            status = "STALE"
        print("{:11} {:5} {:14} {:14} {:23} {:23} {:10} {}".format(name, alias, tok_cur, tok_new, sym_cur, sym_new, exp, status))
        if is_active and status in ("STALE", "SYMBOL-MISSING"):
            updates[prefix + "_FUT_TOKEN"] = tok_new
            updates[prefix + "_FUT_SYMBOL"] = sym_new
    print()
    if not updates:
        print("Result: all active tokens are CURRENT. No .env changes needed.")
        return
    print("Pending updates (" + str(len(updates)) + " keys):")
    for k in sorted(updates):
        print("  " + k + " = " + updates[k])
    if args.write:
        bak = rewrite_env(updates)
        print()
        print("WROTE .env. Backup at: " + bak)
    else:
        print()
        print("DRY-RUN (no changes). Re-run with --write to commit.")

if __name__ == "__main__":
    main()

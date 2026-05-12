#!/usr/bin/env python3
"""
OU-MRS Filter Audit Tool
Read-only diagnostic. Inspects live state files to report regime-filter activity.
Usage: venv/bin/python3 tools/filter_audit.py
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # Phase A5: tools/ -> repo root
STATE = ROOT / "state"
SYMBOLS = ["BNF", "NF"]

def load(symbol):
    p = STATE / f"live_{symbol}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())

def fmt_money(x):
    return f"Rs {x:>+14,.2f}"

def main():
    bar = "=" * 64
    print(bar)
    print("  OU-MRS FILTER AUDIT")
    print(f"  Run at: {datetime.now().isoformat(timespec='seconds')}")
    print(bar)

    total_armed = 0
    total_blocked = 0

    for sym in SYMBOLS:
        s = load(sym)
        if not s:
            print(f"\n[{sym}] no state file")
            continue
        z = s.get("z", 0.0)
        ze = s.get("z_entry", 1.6)
        st = s.get("state", "?")
        sr = s.get("state_reason", "?")
        pos = s.get("position")
        td = s.get("trades_today", 0)
        pnl = s.get("pnl_today", 0.0)
        ltp = s.get("ltp", 0.0)
        mean = s.get("mean", 0.0)
        upd = s.get("updated_at", "?")
        kill = s.get("kill", False)

        cross = abs(z) >= ze
        likely_blocked = cross and st == "idle" and pos is None and not kill

        if likely_blocked:
            flag = "BLOCKED  (filter rejected)"
            total_blocked += 1
        elif cross:
            flag = "ARMED    (entry possible)"
            total_armed += 1
        else:
            flag = "QUIET    (z below threshold)"

        print(f"\n[{sym}] last update: {upd}")
        print(f"  LTP={ltp:>11.2f}   mean={mean:>11.2f}   z={z:>+6.3f}   z_entry={ze}")
        print(f"  state = {st}")
        print(f"  reason = '{sr}'")
        print(f"  trades_today={td}   pnl_today={fmt_money(pnl)}")
        print(f"  kill={kill}   has_position={pos is not None}")
        print(f"  ==> {flag}")
        if likely_blocked:
            print(f"      |z|={abs(z):.3f} cleared {ze} but no entry taken.")
            print(f"      Most likely cause: regime filter rejected (TREND day).")

    print("\n" + "-" * 64)
    print(f"Summary: armed={total_armed}  blocked={total_blocked}")
    if total_blocked > 0:
        print("Filter is actively defending capital today.")
    elif total_armed > 0:
        print("Filter has approved entries - watch live state for fills.")
    else:
        print("Quiet session - no signal pressure.")
    print(bar)

if __name__ == "__main__":
    main()

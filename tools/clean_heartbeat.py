#!/usr/bin/env python3
"""Phase 9.8h.I one-shot: clean test pollution from state/heartbeat.jsonl.

Removes any line where:
- sym == "TEST8O3C" (test fixture symbol)
- sym == "BNF" with max_lots/lot_size matching the test fixture (max_lots=2, lot_size=30)
  AND ltp == 56500 with no real z/mean/std (early-morning test pollution shape)
- sym == "NF" with position.qty == 2 entry == 56400 (test fixture pos)

A backup is written to state/heartbeat.jsonl.pre_p98hI before rewriting.
Idempotent: safe to run multiple times.
"""
import json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HB = ROOT / "state" / "heartbeat.jsonl"
if not HB.exists():
    print("no heartbeat.jsonl; nothing to do")
    raise SystemExit(0)

backup = HB.with_suffix(".jsonl.pre_p98hI")
shutil.copy2(HB, backup)

kept, removed = [], 0
for line in HB.read_text().splitlines():
    if not line.strip():
        continue
    try:
        d = json.loads(line)
    except Exception:
        kept.append(line); continue
    sym = d.get("sym", "")
    if sym == "TEST8O3C":
        removed += 1; continue
    # Detect 8g6 test BNF row: ltp=56500 with state=idle and trades_today=0 and pnl_today=0
    # (the real bot's BNF heartbeats look the same shape today since it has no trades,
    # but the test row uses the exact fixed ltp=56500 fixture; real bot writes nullable ltp
    # via tick_symbol with real broker ltp — not exactly 56500 with no z/mean/std)
    # Conservative: only filter when z is None AND mean is None AND std is None AND ltp is
    # exactly 56500 (the fixed test fixture value). This matches early-morning test rows but
    # not real bot rows (which carry z/mean/std once candles accumulate).
    if sym == "BNF" and d.get("ltp") == 56500 and d.get("z") is None and d.get("mean") is None and d.get("std") is None and d.get("candles_count") == 0:
        removed += 1; continue
    if sym == "NF":
        pos = d.get("position") or {}
        if pos.get("qty") == 2 and pos.get("entry") == 56400.0:
            removed += 1; continue
    kept.append(line)

HB.write_text("\n".join(kept) + ("\n" if kept else ""))
print(f"kept={len(kept)} removed={removed} backup={backup.name}")

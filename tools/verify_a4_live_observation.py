#!/usr/bin/env python3
"""Phase 9.8h.A.4 (v2 / Phase G): verify live bot observation against Sacred Rule #19.

Reads today's ou_mrs_<YYYYMMDD>_091401.log and produces a structured verdict:
- Did the bot start cleanly (Angel login, pfm init, runner init, startup line)?
- Did the Phase 9.8h.5 [config-sanity] line fire (Sacred Rule #41)?
- Did the 9.7Z window-prime skip phase fire?
- Did any vol_band BLOCKED line fire (Sacred Rule #19 specifically named BNF)?
- Any errors before 10:30 IST?

v2 changes (Phase G):
- ADDED config_sanity_line check (Sacred Rule #41 verification)
- REMOVED the wrong OC-7 OC caveat about C.2/C.3 needing to be mirrored into live
  (retracted in audit/phase_9_8h_A_4_live_observation.md)

Usage:
    ./venv/bin/python tools/verify_a4_live_observation.py [YYYY-MM-DD]

Writes verdict to audit/phase_9_8h_A_4_live_observation_<date>.md.
Exit 0 on PASS, 1 on FAIL.
"""
import argparse, datetime as dt, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
AUDIT = ROOT / "audit"


def find_log(date_str: str):
    pat = f"ou_mrs_{date_str.replace('-', '')}_*.log"
    candidates = sorted(LOGS.glob(pat))
    return candidates[0] if candidates else None


def classify(log_path: Path) -> dict:
    text = log_path.read_text(errors="replace")
    out = {
        "log": str(log_path),
        "startup": None,
        "runner_init": None,
        "angel_login": None,
        "pfm_init": None,
        "config_sanity": None,
        "window_skips": 0,
        "vol_band_blocks": 0,
        "errors": [],
        "warnings": 0,
        "first_trade": None,
        "heartbeats": 0,
    }
    for line in text.splitlines():
        if "OU-MRS started" in line:
            out["startup"] = line.strip()
        elif "[config-sanity]" in line and "DISABLED" not in line:
            out["config_sanity"] = line.strip()
        elif "[runners] init" in line:
            out["runner_init"] = line.strip()
        elif "Angel login OK" in line:
            out["angel_login"] = line.strip()
        elif "[pfm] init" in line:
            out["pfm_init"] = line.strip()
        elif "[skip]" in line and "window" in line:
            out["window_skips"] += 1
        elif "BLOCKED" in line and "vol_band" in line.lower():
            out["vol_band_blocks"] += 1
        elif "[heartbeat]" in line:
            out["heartbeats"] += 1
        elif "[ERROR]" in line or " ERROR " in line:
            out["errors"].append(line.strip())
        elif "[WARNING]" in line or " WARN " in line:
            out["warnings"] += 1
        elif "[entry]" in line and out["first_trade"] is None:
            out["first_trade"] = line.strip()
    return out


def verdict(c: dict) -> tuple[str, list[str]]:
    reasons = []
    ok = True
    if not c["angel_login"]:
        ok = False; reasons.append("FAIL: no Angel login OK line")
    if not c["startup"]:
        ok = False; reasons.append("FAIL: no 'OU-MRS started' line")
    if not c["config_sanity"]:
        ok = False; reasons.append("FAIL: no [config-sanity] line (Sacred Rule #41)")
    if not c["runner_init"]:
        ok = False; reasons.append("FAIL: no '[runners] init' line")
    if c["heartbeats"] < 5:
        ok = False; reasons.append(f"FAIL: only {c['heartbeats']} heartbeats (< 5)")
    if c["errors"]:
        ok = False; reasons.append(f"FAIL: {len(c['errors'])} [ERROR] lines")
    if ok:
        reasons.append("PASS: bot booted cleanly with all required artifacts including [config-sanity]")
    return ("PASS" if ok else "FAIL"), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=dt.date.today().isoformat())
    args = ap.parse_args()
    log = find_log(args.date)
    if not log:
        print(f"No log found for {args.date} under {LOGS}", file=sys.stderr)
        return 1
    c = classify(log)
    v, reasons = verdict(c)
    AUDIT.mkdir(exist_ok=True)
    md = AUDIT / f"phase_9_8h_A_4_live_observation_{args.date}.md"
    body = [f"# Phase 9.8h.A.4 live observation — {args.date}", ""]
    body.append(f"**Verdict:** {v}")
    body.append("")
    body.append(f"**Log:** `{c['log']}`")
    body.append("")
    body.append("## Findings")
    for k in ("angel_login", "pfm_init", "runner_init", "startup", "config_sanity", "first_trade"):
        body.append(f"- **{k}**: `{c[k]}`")
    body.append(f"- **heartbeats**: {c['heartbeats']}")
    body.append(f"- **window_skips**: {c['window_skips']}")
    body.append(f"- **vol_band_blocks**: {c['vol_band_blocks']}")
    body.append(f"- **warnings**: {c['warnings']}")
    body.append(f"- **errors**: {len(c['errors'])}")
    if c["errors"]:
        body.append("")
        body.append("### Error lines")
        for e in c["errors"][:20]:
            body.append(f"- `{e}`")
    body.append("")
    body.append("## Verdict reasons")
    for r in reasons:
        body.append(f"- {r}")
    md.write_text("\n".join(body) + "\n")
    print(f"Verdict: {v}")
    print(f"Audit doc: {md}")
    for r in reasons:
        print(f"  - {r}")
    return 0 if v == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

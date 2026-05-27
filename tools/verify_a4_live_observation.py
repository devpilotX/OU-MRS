#!/usr/bin/env python3
"""Phase 9.8h.A.4 (v3 / Phase H): verify live bot observation using journalctl as primary source.

v3 fix (Phase H, 27 May 2026):
- v2 bug: read logs/ou_mrs_<date>_*.log which is the ROTATED-previous file, not today's run.
  run_bot.sh moves ou_mrs.log -> logs/ou_mrs_<NOW>_<NOW>.log AT NEXT STARTUP, so the file
  named with today's timestamp contains YESTERDAY's content. v2 produced a PASS verdict
  that classified yesterday's run as today's.
- v3 fix: primary source is `journalctl -u ou-mrs.service --since <date> -o cat --no-pager`.
  Fall back to rotated log only if journal is empty.

Usage:
    ./venv/bin/python tools/verify_a4_live_observation.py [YYYY-MM-DD]

Writes verdict to audit/phase_9_8h_A_4_live_observation_<date>.md.
Exit 0 on PASS, 1 on FAIL.
"""
import argparse, datetime as dt, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
AUDIT = ROOT / "audit"


def read_journal(date_str: str) -> tuple[str, str]:
    """Return (text, source_label) from journalctl for the given date."""
    try:
        end = (dt.date.fromisoformat(date_str) + dt.timedelta(days=1)).isoformat()
        cmd = [
            "journalctl", "-u", "ou-mrs.service",
            "--since", date_str, "--until", end,
            "-o", "cat", "--no-pager",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout, f"journalctl ou-mrs.service {date_str}"
    except Exception:
        pass
    return "", ""


def find_rotated_log(date_str: str) -> Path | None:
    """NOTE: filename uses next-startup timestamp, not run date. Use only as fallback."""
    pat = f"ou_mrs_{date_str.replace('-', '')}_*.log"
    candidates = sorted(LOGS.glob(pat))
    return candidates[0] if candidates else None


def classify(text: str, source: str) -> dict:
    out = {
        "source": source,
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
        "raw_lines": 0,
    }
    for line in text.splitlines():
        out["raw_lines"] += 1
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
    text, source = read_journal(args.date)
    if not text:
        rotated = find_rotated_log(args.date)
        if not rotated:
            print(f"FAIL: no journal entries or rotated log for {args.date}", file=sys.stderr)
            return 1
        text = rotated.read_text(errors="replace")
        source = f"{rotated} (FALLBACK: rotated file may contain previous run's content)"
    c = classify(text, source)
    v, reasons = verdict(c)
    AUDIT.mkdir(exist_ok=True)
    md = AUDIT / f"phase_9_8h_A_4_live_observation_{args.date}.md"
    body = [f"# Phase 9.8h.A.4 live observation \u2014 {args.date}", ""]
    body.append(f"**Verdict:** {v}")
    body.append("")
    body.append(f"**Source:** `{c['source']}`")
    body.append(f"**Raw lines processed:** {c['raw_lines']}")
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
    print(f"Source: {c['source']}")
    for r in reasons:
        print(f"  - {r}")
    return 0 if v == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

"""Phase 9.7AB: skip-reason audit (compact)."""
import argparse, re, subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
SKIP_RE = re.compile(r"\[skip\] Phase 9\.7Z ([a-z_]+):")
REGIME_SKIP_RE = re.compile(r"\[regime\] skip: ([a-z_]+)")
LATENCY_RE = re.compile(r"latency\[compute_signal\]")
ENTRY_RE = re.compile(r"\[entry\]")
SYMBOL_RE = re.compile(r"\b(BNF|NF|MCN|FNF)\b")

def fetch(since):
    cmd = ["sudo", "journalctl", "-u", "ou-mrs.service", "-S", since, "--no-pager"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=datetime.now(IST).strftime("%Y-%m-%d 09:15:00"))
    ns = ap.parse_args()
    lines = fetch(ns.since)
    skip = Counter(); regime = Counter(); calls = 0; entries = 0
    by_sym = defaultdict(Counter)
    for ln in lines:
        m = SKIP_RE.search(ln)
        if m:
            skip[m.group(1)] += 1
            sm = SYMBOL_RE.search(ln)
            if sm: by_sym[sm.group(1)][m.group(1)] += 1
            continue
        m = REGIME_SKIP_RE.search(ln)
        if m: regime[m.group(1)] += 1; continue
        if LATENCY_RE.search(ln): calls += 1; continue
        if ENTRY_RE.search(ln): entries += 1
    total = sum(skip.values()) + sum(regime.values())
    passed = max(0, calls - total)
    print("=" * 60)
    print("Skip audit since " + ns.since)
    print("=" * 60)
    print("compute_signal evaluations: " + str(calls))
    print("total skip events:          " + str(total))
    print("signals passing gates:      " + str(passed))
    print("entries fired:              " + str(entries))
    if calls:
        print("funnel survival:            " + format(passed/calls*100, ".2f") + "%")
    print()
    print("-- Phase 9.7Z gate skips --")
    if not skip: print("  (none)")
    for g, n in sorted(skip.items(), key=lambda x: -x[1]):
        rate = n/calls*100 if calls else 0
        print("  " + g.ljust(20) + str(n).rjust(6) + "  (" + format(rate, "5.1f") + "%)")
    print()
    print("-- regime/ADX skips --")
    if not regime: print("  (none)")
    for k, n in sorted(regime.items(), key=lambda x: -x[1]):
        print("  " + k.ljust(20) + str(n).rjust(6))
    print()
    print("-- per-symbol --")
    if not by_sym: print("  (none)")
    for s in sorted(by_sym.keys()):
        print("  " + s + ":")
        for g, n in sorted(by_sym[s].items(), key=lambda x: -x[1]):
            print("    " + g.ljust(18) + str(n).rjust(6))

if __name__ == "__main__":
    main()

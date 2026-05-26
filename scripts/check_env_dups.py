#!/usr/bin/env python3
"""
check_env_dups.py — defensive linter for .env-style files.

Detects duplicate keys in any .env-style file. Under python-dotenv's default
override behavior, the last assignment wins, so a duplicate-key block is
silently dead code at best and a stealth-rollback risk at worst (if dotenv
override behavior ever changes, the bot could silently revert to the older
value without any code change or restart of intent).

Born from Phase 9.8h.9 RCA: the on-VPS .env had OU_Z_STOP_{BNF,NF,MCN}
declared twice — once at 3.5 (Phase 9.7N, 2026-05-15) and once at 2.5
(Phase 9.7AO, 2026-05-21). Live armor was 2.5 (last-wins), but the 3.5
block lingered for 6 days as confusing dead code that any reviewer would
flag as a stop-loosening regression at first glance.

Usage:
    python scripts/check_env_dups.py [PATH ...]

If no PATH is given, every tracked .env* file in the repo is checked
(except .env itself, which is gitignored and lives only on the deployment
target; check it manually with an explicit PATH argument if needed).

Exit codes:
    0  no duplicates
    1  one or more duplicates found
    2  invocation error
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
AUTO_APPEND_RE = re.compile(r"auto[-_ ]?appended", re.IGNORECASE)


def parse_keys(path: Path) -> list[tuple[int, str]]:
    """Return [(lineno, key)] for every key= assignment (1-indexed)."""
    out: list[tuple[int, str]] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            stripped = raw.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            m = KEY_RE.match(raw)
            if m:
                out.append((lineno, m.group(1)))
    return out


def find_duplicates(path: Path) -> list[tuple[str, list[int]]]:
    rows = parse_keys(path)
    seen: dict[str, list[int]] = {}
    for lineno, key in rows:
        seen.setdefault(key, []).append(lineno)
    return sorted([(k, v) for k, v in seen.items() if len(v) > 1])


def find_auto_appended(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            if AUTO_APPEND_RE.search(raw):
                out.append((lineno, raw.rstrip()))
    return out


def discover_targets() -> list[Path]:
    """Find tracked .env* files via git, excluding .env (gitignored)."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--", ".env*"],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return [Path(".env.example")] if Path(".env.example").exists() else []
    paths: list[Path] = []
    for raw in proc.stdout.split(b"\x00"):
        if not raw:
            continue
        name = raw.decode("utf-8", errors="replace").strip()
        if not name or name == ".env":
            continue
        p = Path(name)
        if p.exists():
            paths.append(p)
    return sorted(set(paths))


def main(argv: list[str]) -> int:
    if argv:
        targets = [Path(a) for a in argv]
    else:
        targets = discover_targets()

    if not targets:
        print("check_env_dups: no targets to check (no tracked .env* files).")
        return 0

    failed = False
    for path in targets:
        if not path.exists():
            print(f"check_env_dups: {path}: NOT FOUND", file=sys.stderr)
            failed = True
            continue
        dups = find_duplicates(path)
        if dups:
            failed = True
            print(f"check_env_dups: {path}: FAIL — duplicate keys")
            for key, lines in dups:
                print(f"  {key}: lines {', '.join(str(n) for n in lines)}")
        else:
            n_keys = len(parse_keys(path))
            print(f"check_env_dups: {path}: ok ({n_keys} keys, 0 dupes)")
        ap = find_auto_appended(path)
        if ap:
            print(f"  note: {path}: 'auto-appended' markers detected (review smell)")
            for lineno, text in ap:
                print(f"    L{lineno}: {text}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Phase 9.8h.M: auto-rollover to next monthly expiry.

Queries data/instruments.db (Angel scripmaster) for next-month FUT symbols+tokens
for BANKNIFTY, NIFTY, MIDCPNIFTY. Backs up .env, then patches the 6 keys:
  BANKNIFTY_FUT_SYMBOL/TOKEN, NIFTY_FUT_SYMBOL/TOKEN, MIDCPNIFTY_FUT_SYMBOL/TOKEN.

Refuses to run if any bot position is open (state/live_<SYM>.json).
Refuses to run if scripmaster is older than 24h (must re-sync first).

Usage:
    venv/bin/python scripts/rollover_to_next_expiry.py --dry-run
    venv/bin/python scripts/rollover_to_next_expiry.py --apply
"""
import argparse, json, os, sqlite3, sys, time, datetime, shutil, pathlib, re

ROOT = pathlib.Path('/home/ubuntu/bots/ou-mrs')
DB = ROOT/'data/instruments.db'
ENV = ROOT/'.env'

SYMBOLS = [
    ('BANKNIFTY',  'BANKNIFTY_FUT_SYMBOL',  'BANKNIFTY_FUT_TOKEN'),
    ('NIFTY',      'NIFTY_FUT_SYMBOL',      'NIFTY_FUT_TOKEN'),
    ('MIDCPNIFTY', 'MIDCPNIFTY_FUT_SYMBOL', 'MIDCPNIFTY_FUT_TOKEN'),
]

def check_positions_flat():
    open_syms = []
    for sym in ('BNF','NF','MCN'):
        p = ROOT/f'state/live_{sym}.json'
        if not p.exists(): continue
        try:
            d = json.loads(p.read_text())
            if d.get('position') and d['position'].get('qty',0) != 0:
                open_syms.append(sym)
        except Exception:
            pass
    return open_syms

def next_expiry_contracts():
    if not DB.exists():
        raise SystemExit(f'instruments.db missing: {DB}')
    age_h = (time.time() - DB.stat().st_mtime) / 3600
    if age_h > 36:
        raise SystemExit(f'instruments.db is {age_h:.1f}h old; sync first via scripts/sync_instruments.py')
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    out = {}
    today = datetime.date.today()
    for ul, env_sym, env_tok in SYMBOLS:
        rows = con.execute(
            "SELECT symbol, token, expiry FROM scripmaster "
            "WHERE underlying=? AND instrumenttype='FUTIDX' AND expiry > ? "
            "ORDER BY expiry ASC LIMIT 3",
            (ul, today.isoformat())
        ).fetchall()
        if len(rows) < 2:
            raise SystemExit(f'{ul}: scripmaster only has {len(rows)} future expiry rows (need >=2 for next-month rollover)')
        # rows[0] = current expiry (still in future), rows[1] = NEXT month
        out[ul] = {'env_sym':env_sym, 'env_tok':env_tok,
                   'current': dict(rows[0]), 'next': dict(rows[1])}
    return out

def patch_env(plan, dry):
    env_text = ENV.read_text() if ENV.exists() else ''
    lines = env_text.splitlines()
    changes = []
    for ul, data in plan.items():
        new_sym = data['next']['symbol']; new_tok = str(data['next']['token'])
        for key, val in ((data['env_sym'], new_sym),(data['env_tok'], new_tok)):
            pat = re.compile(rf'^{re.escape(key)}=')
            hit = False
            for i,l in enumerate(lines):
                if pat.match(l):
                    old = l.split('=',1)[1] if '=' in l else ''
                    if old != val:
                        changes.append((key, old, val))
                        lines[i] = f'{key}={val}'
                    hit = True; break
            if not hit:
                changes.append((key,'<MISSING>',val))
                lines.append(f'{key}={val}')
    if not dry and changes:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = ENV.with_suffix(ENV.suffix + f'.pre_rollover_{ts}.bak')
        shutil.copy2(ENV, backup)
        ENV.write_text('\n'.join(lines) + '\n')
        print(f'BACKUP: {backup.name}')
    return changes

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run', action='store_true')
    g.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    open_syms = check_positions_flat()
    if open_syms:
        raise SystemExit(f'REFUSE: open positions in {open_syms}; close manually before rollover')
    plan = next_expiry_contracts()
    print('=== ROLLOVER PLAN ===')
    for ul, d in plan.items():
        print(f'{ul}: {d["current"]["symbol"]} (tok {d["current"]["token"]}, exp {d["current"]["expiry"]}) -> {d["next"]["symbol"]} (tok {d["next"]["token"]}, exp {d["next"]["expiry"]})')
    changes = patch_env(plan, dry=a.dry_run)
    print('=== ENV CHANGES ===')
    for k,o,n in changes:
        print(f'{k}: {o} -> {n}')
    if a.dry_run:
        print('(dry-run; .env not modified)')
    else:
        print('APPLIED. Restart bot when flat: systemctl --user restart ou-mrs')

if __name__ == '__main__':
    main()

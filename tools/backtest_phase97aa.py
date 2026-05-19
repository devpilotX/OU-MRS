#!/usr/bin/env python3
"""Phase 9.7AA full backtest grid.
16 configs = OU_VOL_CONFIRM(2) x OU_ATR_PCT_FILTER(2) x HL_BOUNDS(2) x OU_DISABLE_Z_VEL_STALL(2)
Each combo runs in fresh subprocess for clean env. BNF FUT only (only parquet available).
Ranked by composite_score = win_rate * sharpe * min(trades_per_day, 3) / 3."""
import itertools, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bt_out" / "phase97aa"
OUT.mkdir(parents=True, exist_ok=True)

CONFIGS = []
for vc, ap, hl, zv in itertools.product(
    ['on', 'off'],            # OU_VOL_CONFIRM
    ['on', 'off'],            # OU_ATR_PCT_FILTER
    [(1.0, 15.0), (0.5, 20.0)],  # (HL_MIN, HL_MAX)
    ['off', 'on'],            # OU_DISABLE_Z_VEL_STALL
):
    CONFIGS.append({
        'OU_VOL_CONFIRM': vc,
        'OU_ATR_PCT_FILTER': ap,
        'OU_HL_MIN': str(hl[0]),
        'OU_HL_MAX': str(hl[1]),
        'OU_DISABLE_Z_VEL_STALL': zv,
        # parity with live .env
        'BT_ADX': '32',
        'BT_ZENTRY': '1.5',
        'BT_ZSTOP': '3.5',
        'BT_REGIME_FILTER': 'CHOP,RANGE',
    })

print(f"Running {len(CONFIGS)} configs on BNF FUT...")
print()
results = []
for i, cfg in enumerate(CONFIGS, 1):
    name = f"c{i:02d}_vc{cfg['OU_VOL_CONFIRM']}_ap{cfg['OU_ATR_PCT_FILTER']}_hl{cfg['OU_HL_MIN']}-{cfg['OU_HL_MAX']}_zvdis{cfg['OU_DISABLE_Z_VEL_STALL']}"
    env = os.environ.copy()
    env.update(cfg)
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, str(ROOT / "backtest.py")],
        env=env, cwd=str(ROOT),
        capture_output=True, text=True, timeout=300
    )
    elapsed = time.time() - t0
    if r.returncode != 0:
        err = (r.stderr or r.stdout)[-300:]
        print(f"[{i:>2}/16] FAILED  {name}  ({elapsed:.1f}s)\n      {err}")
        results.append({'name': name, 'config': cfg, 'error': err, 'elapsed_sec': elapsed})
        continue
    try:
        metrics = json.loads((ROOT / "bt_out" / "metrics.json").read_text())
    except Exception as e:
        print(f"[{i:>2}/16] PARSE_FAIL  {name}  {e}")
        results.append({'name': name, 'config': cfg, 'error': str(e)})
        continue
    metrics['name'] = name
    metrics['config'] = cfg
    metrics['elapsed_sec'] = round(elapsed, 1)
    results.append(metrics)
    print(f"[{i:>2}/16] {name[:64]:<64} trades={metrics.get('trades',0):>3} "
          f"win={metrics.get('win_rate',0)*100:>5.1f}% PF={metrics.get('profit_factor',0):>5.2f} "
          f"Sh={metrics.get('sharpe',0):>+6.2f} ret={metrics.get('return_pct',0):>+6.2f}% ({elapsed:.0f}s)")
    (OUT / f"{name}.json").write_text(json.dumps(metrics, indent=2, default=str))

# composite_score
for r in results:
    if 'error' in r or r.get('trades', 0) == 0:
        r['composite_score'] = -999.0
        continue
    tpd = min(float(r.get('trades_per_day', 0)), 3.0)
    sh = max(float(r.get('sharpe', -3)), -3.0)
    wr = float(r.get('win_rate', 0))
    r['composite_score'] = round(wr * sh * (tpd / 3.0), 4)

results_sorted = sorted(results, key=lambda r: r.get('composite_score', -999), reverse=True)
(OUT / "all_results.json").write_text(json.dumps(results_sorted, indent=2, default=str))

print()
print("=" * 120)
print(f"{'RANK':>4}  {'VC':>3} {'AP':>3} {'HL_MIN':>6} {'HL_MAX':>6} {'ZV_DIS':>6}  "
      f"{'TRD':>4} {'WIN%':>5} {'PF':>5} {'SHARPE':>7} {'RET%':>7} {'TPD':>4}  {'SCORE':>7}")
print("-" * 120)
for rank, r in enumerate(results_sorted, 1):
    c = r.get('config', {})
    if 'error' in r:
        print(f"{rank:>4}  ERR {r.get('name', '?')}")
        continue
    print(f"{rank:>4}  {c.get('OU_VOL_CONFIRM',''):>3} {c.get('OU_ATR_PCT_FILTER',''):>3} "
          f"{c.get('OU_HL_MIN',''):>6} {c.get('OU_HL_MAX',''):>6} {c.get('OU_DISABLE_Z_VEL_STALL',''):>6}  "
          f"{r.get('trades',0):>4} {r.get('win_rate',0)*100:>4.1f}% "
          f"{r.get('profit_factor',0):>5.2f} {r.get('sharpe',0):>+7.2f} "
          f"{r.get('return_pct',0):>+6.2f}% {r.get('trades_per_day',0):>4.2f}  "
          f"{r.get('composite_score',0):>+7.3f}")
print("=" * 120)
best = results_sorted[0]
if 'error' not in best and best.get('trades', 0) > 0:
    c = best['config']
    print()
    print(f"WINNER: {best['name']}")
    print(f"  trades={best['trades']}  win={best['win_rate']*100:.1f}%  PF={best['profit_factor']:.2f}  "
          f"Sharpe={best['sharpe']:+.2f}  return={best['return_pct']:+.2f}%  tpd={best['trades_per_day']:.2f}")
    print(f"  RECOMMENDED .env:")
    for k in ('OU_VOL_CONFIRM','OU_ATR_PCT_FILTER','OU_HL_MIN','OU_HL_MAX','OU_DISABLE_Z_VEL_STALL'):
        print(f"    {k}={c[k]}")
    # write a single-line summary for downstream parsers
    (OUT / "BEST.txt").write_text(
        " ".join(f"{k}={c[k]}" for k in ('OU_VOL_CONFIRM','OU_ATR_PCT_FILTER','OU_HL_MIN','OU_HL_MAX','OU_DISABLE_Z_VEL_STALL')) + "\n"
    )
    print(f"\nWrote {OUT/'BEST.txt'}")

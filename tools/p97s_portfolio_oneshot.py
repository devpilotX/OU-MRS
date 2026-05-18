#!/usr/bin/env python3
"""Phase 9.7S B4: weekend one-shot, populates state/portfolio.json from Angel."""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/ubuntu/bots/ou-mrs"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass
from angel_adapter import AngelBroker
from ou_mrs import _snapshot_portfolio, _write_portfolio_json_p97s
print("[p97s-oneshot] logging in to Angel...")
b = AngelBroker().login()
print("[p97s-oneshot] login OK, snapshotting...")
snap = _snapshot_portfolio(b)
if isinstance(snap, dict):
    rms = snap.get("rms"); pos = snap.get("position")
    print(f"[p97s-oneshot] rms keys: {list(rms.keys())[:8] if isinstance(rms, dict) else type(rms).__name__}")
    if isinstance(rms, dict):
        print(f"[p97s-oneshot] net={rms.get('net')} availablecash={rms.get('availablecash')} collateral={rms.get('collateral')}")
    print(f"[p97s-oneshot] position: {type(pos).__name__} len={len(pos) if hasattr(pos,'__len__') else 'n/a'}")
else:
    print(f"[p97s-oneshot] WARNING snap not dict: {type(snap).__name__} = {snap!r}")
_write_portfolio_json_p97s(snap)
print("[p97s-oneshot] state/portfolio.json written.")
print("----- file contents -----")
print(json.dumps(json.loads(open("state/portfolio.json").read()), indent=2, default=str)[:1500])

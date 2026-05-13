"""
Phase 9.8f.54: Top gainers/losers scanner (Angel feature 11). Synthetic random-walk seeded with realistic intraday open prices for 30 large-cap NSE symbols + 2 indices. Real Angel scanner integration deferred to Round 3 (E1).
"""
import time
import random
import threading

_SEED = "NIFTY:25000,BANKNIFTY:53800,RELIANCE:2950,HDFCBANK:1720,TCS:4100,INFY:1850,ICICIBANK:1310,BHARTIARTL:1680,ITC:470,LT:3680,SBIN:815,AXISBANK:1170,KOTAKBANK:1740,HINDUNILVR:2510,BAJFINANCE:7050,MARUTI:12800,ASIANPAINT:2780,WIPRO:545,ULTRACEMCO:11200,TITAN:3450,SUNPHARMA:1850,NESTLEIND:2480,TECHM:1720,POWERGRID:335,NTPC:380,HCLTECH:1850,JSWSTEEL:1010,TATASTEEL:165,ADANIENT:2750,TATAMOTORS:920"
DAY_OPEN = {s.split(":")[0]: float(s.split(":")[1]) for s in _SEED.split(",")}
SYMBOLS = list(DAY_OPEN.keys())

_LAST = {}
_LOCK = threading.Lock()
_TS = 0.0

def _refresh():
	global _TS
	now = time.time()
	if now - _TS < 0.5:
		return
	with _LOCK:
		for sym in SYMBOLS:
			base = DAY_OPEN[sym]
			cur = _LAST.get(sym, base)
			drift = random.gauss(0, base * 0.0008) - 0.05 * (cur - base)
			_LAST[sym] = max(0.01, cur + drift)
		_TS = now

def get_movers(n=5):
	_refresh()
	with _LOCK:
		rows = []
		for sym in SYMBOLS:
			opn = DAY_OPEN[sym]
			ltp = _LAST.get(sym, opn)
			chg = ltp - opn
			pct = (chg / opn) * 100.0 if opn > 0 else 0.0
			rows.append({"symbol": sym, "open": round(opn, 2), "ltp": round(ltp, 2), "change": round(chg, 2), "pct": round(pct, 3)})
		rows.sort(key=lambda r: r["pct"])
		return {"gainers": rows[-n:][::-1], "losers": rows[:n], "as_of": int(time.time())}

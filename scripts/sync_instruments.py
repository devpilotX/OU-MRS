#!/usr/bin/env python3
"""Phase 9.8g.65a v3: sync Angel scrip-master to SQLite."""
import urllib.request, json, sqlite3, os, sys, time

URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
DB_PATH = "data/instruments.db"
TMP_PATH = "data/scripmaster.tmp.json"

def safe_int(v, d=0):
	try: return int(float(v)) if v not in (None, "") else d
	except Exception: return d

def safe_float(v, d=0.0):
	try: return float(v) if v not in (None, "") else d
	except Exception: return d

def sync():
	print(f"[sync] downloading {URL}")
	t0 = time.time()
	urllib.request.urlretrieve(URL, TMP_PATH)
	print(f"[sync] downloaded {os.path.getsize(TMP_PATH):,} bytes in {time.time()-t0:.1f}s")
	with open(TMP_PATH) as f: rows = json.load(f)
	print(f"[sync] {len(rows):,} instruments")
	if rows: print(f"[sync] fields: {sorted(rows[0].keys())}")
	os.makedirs("data", exist_ok=True)
	conn = sqlite3.connect(DB_PATH)
	conn.execute("DROP TABLE IF EXISTS instruments")
	conn.execute("CREATE TABLE instruments (token TEXT, symbol TEXT, name TEXT, expiry TEXT, strike REAL, lot_size INTEGER, instrument_type TEXT, exchange TEXT, tick_size REAL)")
	batch = [(str(r.get("token","")), str(r.get("symbol","")), str(r.get("name","")), str(r.get("expiry","")), safe_float(r.get("strike",0)), safe_int(r.get("lotsize",0)), str(r.get("instrumenttype","")), str(r.get("exch_seg","")), safe_float(r.get("tick_size",0))) for r in rows]
	conn.executemany("INSERT INTO instruments VALUES (?,?,?,?,?,?,?,?,?)", batch)
	for stmt in ["CREATE INDEX idx_symbol ON instruments(symbol)", "CREATE INDEX idx_exch ON instruments(exchange)", "CREATE INDEX idx_token ON instruments(token)", "CREATE INDEX idx_name ON instruments(name)"]:
		conn.execute(stmt)
	conn.commit()
	n = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
	conn.close()
	try: os.remove(TMP_PATH)
	except Exception: pass
	print(f"[sync] DONE rows={n:,} db_size={os.path.getsize(DB_PATH):,}")

if __name__ == "__main__":
	sync()

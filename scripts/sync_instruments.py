#!/usr/bin/env python3
"""Phase 9.8g.65a: sync Angel scrip-master to SQLite instruments DB."""
import urllib.request, json, sqlite3, os, sys, time

URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPI_ScripMaster.json"
DB_PATH = "data/instruments.db"
TMP_PATH = "data/scripmaster.tmp.json"
CACHE_AGE_HOURS = 24
cd /home/ubuntu/bots/ou-mrs
set +H; export PAGER=cat GIT_PAGER=cat; unset LESS

echo "=== STEP 65a v2: write sync script via python parts (no bash heredoc) ==="
mkdir -p scripts data
rm -f scripts/sync_instruments.py

python3 << 'PYEOF'
p = []
p.append('#!/usr/bin/env python3')
p.append('"""Phase 9.8g.65a: sync Angel scrip-master to SQLite."""')
p.append('import urllib.request, json, sqlite3, os, sys, time')
p.append('')
p.append('URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPI_ScripMaster.json"')
p.append('DB_PATH = "data/instruments.db"')
p.append('TMP_PATH = "data/scripmaster.tmp.json"')
p.append('CACHE_AGE_HOURS = 24')
p.append('')
p.append('def fresh_enough():')
p.append('\tif not os.path.exists(DB_PATH): return False')
p.append('\treturn (time.time() - os.path.getmtime(DB_PATH)) / 3600 < CACHE_AGE_HOURS')
p.append('')
p.append('def safe_int(v, d=0):')
p.append('\ttry: return int(float(v)) if v not in (None, "") else d')
p.append('\texcept Exception: return d')
p.append('')
p.append('def safe_float(v, d=0.0):')
p.append('\ttry: return float(v) if v not in (None, "") else d')
p.append('\texcept Exception: return d')
p.append('')
p.append('def sync(force=False):')
p.append('\tif not force and fresh_enough():')
p.append('\t\tprint("[sync_instruments] cache fresh, skip"); return')
p.append('\tprint(f"[sync_instruments] downloading {URL}")')
p.append('\tt0 = time.time()')
p.append('\turllib.request.urlretrieve(URL, TMP_PATH)')
p.append('\tprint(f"[sync_instruments] downloaded {os.path.getsize(TMP_PATH):,} bytes in {time.time()-t0:.1f}s")')
p.append('\twith open(TMP_PATH) as f: rows = json.load(f)')
p.append('\tprint(f"[sync_instruments] {len(rows):,} instruments")')
p.append('\tif rows:')
p.append('\t\tprint(f"[sync_instruments] sample fields: {sorted(rows[0].keys())}")')
p.append('\t\tprint(f"[sync_instruments] sample row: {rows[0]}")')
p.append('\tconn = sqlite3.connect(DB_PATH)')
p.append('\tconn.execute("DROP TABLE IF EXISTS instruments")')
p.append('\tconn.execute("CREATE TABLE instruments (token TEXT, symbol TEXT, name TEXT, expiry TEXT, strike REAL, lot_size INTEGER, instrument_type TEXT, exchange TEXT, tick_size REAL)")')
p.append('\tbatch = [(str(r.get("token","")), str(r.get("symbol","")), str(r.get("name","")), str(r.get("expiry","")), safe_float(r.get("strike",0)), safe_int(r.get("lotsize",0)), str(r.get("instrumenttype","")), str(r.get("exch_seg","")), safe_float(r.get("tick_size",0))) for r in rows]')
p.append('\tconn.executemany("INSERT INTO instruments VALUES (?,?,?,?,?,?,?,?,?)", batch)')
p.append('\tfor stmt in ["CREATE INDEX idx_symbol ON instruments(symbol)", "CREATE INDEX idx_exch ON instruments(exchange)", "CREATE INDEX idx_token ON instruments(token)", "CREATE INDEX idx_name ON instruments(name)"]:')
p.append('\t\tconn.execute(stmt)')
p.append('\tconn.commit()')
p.append('\tn = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]')
p.append('\tby_exch = conn.execute("SELECT exchange, COUNT(*) FROM instruments GROUP BY exchange ORDER BY 2 DESC").fetchall()')
p.append('\tconn.close()')
p.append('\ttry: os.remove(TMP_PATH)')
p.append('\texcept Exception: pass')
p.append('\tprint(f"[sync_instruments] DONE rows={n:,} db_size={os.path.getsize(DB_PATH):,} bytes")')
p.append('\tfor ex, c in by_exch: print(f"  {ex}: {c:,}")')
p.append('')
p.append('if __name__ == "__main__":')
p.append('\tsync(force=("--force" in sys.argv))')
src = "\n".join(p) + "\n"
open("scripts/sync_instruments.py", "w").write(src)
print(f"WROTE scripts/sync_instruments.py: {len(src)} chars, {len(p)} lines")


import os, json, subprocess, time, secrets, sys
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, Form, Cookie, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import bcrypt
from itsdangerous import URLSafeSerializer, BadSignature
from dotenv import load_dotenv

APP_DIR = Path(__file__).parent
BOT_DIR = APP_DIR.parent
load_dotenv(BOT_DIR / ".env")
sys.path.insert(0, str(BOT_DIR))
import signal_publisher  # Phase 8f.5

SECRET_KEY = os.environ.get("DASHBOARD_SECRET") or secrets.token_hex(32)
ADMIN_USER = os.environ.get("DASHBOARD_USER", "admin")
_ph = os.environ.get("DASHBOARD_PASS_HASH", "")
ADMIN_PASS_HASH = _ph.encode() if _ph else None

signer = URLSafeSerializer(SECRET_KEY, salt="ou-mrs-session")

# Phase 9.6a: route named loggers (p96, ws_pump) to journald via uvicorn stderr
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    force=True,
)
app = FastAPI(title="OU-MRS Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

def is_authed(session):
    if not session or not ADMIN_PASS_HASH:
        return False
    try:
        data = signer.loads(session)
        return data.get("u") == ADMIN_USER and time.time() < data.get("e", 0)
    except BadSignature:
        return False

def need_auth(session: str = Cookie(default=None)):
    if not is_authed(session):
        raise HTTPException(status_code=401)
    return True

@app.get("/login", response_class=HTMLResponse)
def login_page():
    return (APP_DIR / "static" / "login.html").read_text()

@app.post("/login")
def do_login(username: str = Form(...), password: str = Form(...)):
    if not ADMIN_PASS_HASH or username != ADMIN_USER:
        return RedirectResponse("/login?err=1", status_code=303)
    try:
        if not bcrypt.checkpw(password.encode(), ADMIN_PASS_HASH):
            return RedirectResponse("/login?err=1", status_code=303)
    except Exception:
        return RedirectResponse("/login?err=1", status_code=303)
    token = signer.dumps({"u": ADMIN_USER, "e": time.time() + 7*86400})
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=7*86400)
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session")
    return resp

@app.get("/", response_class=HTMLResponse)
def dashboard(session: str = Cookie(default=None)):
    if not is_authed(session):
        return RedirectResponse("/login", status_code=303)
    return (APP_DIR / "static" / "index.html").read_text()

def sd_active(unit):
    try:
        r = subprocess.run(["systemctl","is-active",unit], capture_output=True, text=True, timeout=3)
        return r.stdout.strip()
    except Exception:
        return "unknown"

def sd_next(timer):
    try:
        r = subprocess.run(["systemctl","show",timer,"-p","NextElapseUSecRealtime","--value"],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip()
    except Exception:
        return ""


def _heartbeat_age_seconds(h):
    import re, datetime as d
    if not h: return None
    try:
        m = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', h)
        if not m: return None
        return (d.datetime.now() - d.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')).total_seconds()
    except Exception:
        return None

def _market_status_now():
    import datetime as d
    n = d.datetime.now()
    if n.weekday() >= 5: return 'closed'
    mn = n.hour*60 + n.minute
    if mn < 540: return 'closed'
    if mn < 555: return 'pre_open'
    if mn < 930: return 'open'
    return 'closed'

def _derive_bot_status(svc, tmr, hb_age, mkt):
    if tmr != 'active': return ('DISABLED', 'Timer '+str(tmr), 'err')
    if svc == 'active':
        if hb_age is not None and hb_age > 90: return ('STALLED', 'No heartbeat for '+str(int(hb_age))+'s', 'warn')
        return ('RUNNING', 'Live trading session', 'ok')
    if mkt == 'open': return ('STALLED', 'Market open, bot not running', 'err')
    if mkt == 'pre_open': return ('ARMING', 'Pre-market window', 'info')
    return ('ARMED', 'Standing by until 9:15 IST', 'info')

@app.get("/api/status", dependencies=[Depends(need_auth)])
def api_status():
    # Find most recent dated log in logs/, fall back to root ou_mrs.log
    _logs_dir = BOT_DIR / "logs"
    _candidates = sorted(_logs_dir.glob("ou_mrs_*.log"), key=lambda p: p.stat().st_mtime, reverse=True) if _logs_dir.exists() else []
    log_path = _candidates[0] if _candidates else (BOT_DIR / "ou_mrs.log")
    hb = None; hb_count = 0
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            if "heartbeat" in line:
                hb_count += 1; hb = line
    _hb_age_s = _heartbeat_age_seconds(hb)
    _market_status = _market_status_now()
    _bs_lbl, _bs_rsn, _bs_sev = _derive_bot_status(sd_active('ou-mrs.service'), sd_active('ou-mrs.timer'), _hb_age_s, _market_status)
    return {
        "bot_state": sd_active("ou-mrs.service"),
        "timer_state": sd_active("ou-mrs.timer"),
        "next_run_usec": sd_next("ou-mrs.timer"),
        "latest_heartbeat": hb,
        "heartbeat_count_today": hb_count,
        "server_time": datetime.now().isoformat(),
        "capital": int(os.environ.get("CAPITAL", 3750000)),
        "live_mode": os.environ.get("LIVE","false").lower() == "true",
        "bot_status": _bs_lbl,
        "bot_status_reason": _bs_rsn,
        "bot_status_severity": _bs_sev,
        "heartbeat_age_s": _hb_age_s,
        "market_status": _market_status,
    }

@app.get("/api/trades", dependencies=[Depends(need_auth)])
def api_trades():
    path = BOT_DIR / "trades.jsonl"
    trades = []
    if path.exists():
        for line in path.read_text().splitlines():
            try: trades.append(json.loads(line))
            except: pass
    cum = 0; wins = 0
    for t in trades:
        pnl = float(t.get("pnl") or 0)
        cum += pnl
        if pnl > 0: wins += 1
        t["cum_pnl"] = cum
        # Phase 9.8e B4: derive bars_held from entry_ts/exit_ts (3-min bars) when missing
        if not t.get('bars_held'):
            try:
                from datetime import datetime as _dt_b4
                _ets = (t.get('entry_ts') or '').strip().replace(' ', 'T', 1)
                _xts = (t.get('exit_ts') or '').strip().replace(' ', 'T', 1)
                if _ets and _xts:
                    _e = _dt_b4.fromisoformat(_ets)
                    _x = _dt_b4.fromisoformat(_xts)
                    t['bars_held'] = max(1, int((_x - _e).total_seconds() / 180))
            except Exception:
                pass
    return {"trades": trades[-200:], "count": len(trades),
            "total_pnl": cum, "win_rate": wins/len(trades) if trades else 0}

@app.get("/api/log", dependencies=[Depends(need_auth)])
def api_log(n: int = 200, q: str = "", level: str = "", symbol: str = "", file: str = ""):
    import re as _re
    logs_dir = BOT_DIR / "logs"
    log_path = None
    if file:
        safe = _re.sub(r"[^A-Za-z0-9_.-]", "", file)
        cand = logs_dir / safe
        if cand.exists() and cand.is_file():
            log_path = cand
    if log_path is None and logs_dir.exists():
        cands = sorted(logs_dir.glob("ou_mrs_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if cands:
            log_path = cands[0]
    if log_path is None:
        log_path = BOT_DIR / "ou_mrs.log"
    if not log_path.exists():
        return {"lines": [], "source": log_path.name, "total": 0, "filtered": 0, "sticky_errors": []}
    try:
        with log_path.open("rb") as f:
            f.seek(0, 2); size = f.tell()
            read = min(size, 256 * 1024)
            f.seek(size - read)
            data = f.read().decode("utf-8", errors="replace")
        all_lines = data.splitlines()
        lines = all_lines
        if level:
            lev_re = _re.compile(r"\[" + _re.escape(level.upper()) + r"\]")
            lines = [l for l in lines if lev_re.search(l)]
        if symbol:
            sym_re = _re.compile(r"\[" + _re.escape(symbol) + r"\]")
            lines = [l for l in lines if sym_re.search(l)]
        if q:
            try:
                q_re = _re.compile(q, _re.I)
                lines = [l for l in lines if q_re.search(l)]
            except _re.error:
                ql = q.lower()
                lines = [l for l in lines if ql in l.lower()]
        err_re = _re.compile(r"\[(ERROR|CRITICAL)\]|Traceback|Exception", _re.I)
        sticky = [l for l in all_lines if err_re.search(l)][-5:]
        return {
            "lines": lines[-n:],
            "source": log_path.name,
            "total": len(all_lines),
            "filtered": len(lines),
            "sticky_errors": sticky,
        }
    except Exception as e:
        return {"lines": [f"[log read error] {e}"], "source": log_path.name, "total": 0, "filtered": 0, "sticky_errors": []}

@app.get("/api/logs/list", dependencies=[Depends(need_auth)])
def api_logs_list():
    from datetime import datetime as _dt
    logs_dir = BOT_DIR / "logs"
    if not logs_dir.exists():
        return {"files": []}
    files = []
    for p in sorted(logs_dir.glob("ou_mrs_*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        st = p.stat()
        files.append({
            "name": p.name,
            "size": st.st_size,
            "mtime": st.st_mtime,
            "mtime_iso": _dt.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        })
    return {"files": files}

@app.get("/api/logs/download", dependencies=[Depends(need_auth)])
def api_logs_download(file: str):
    import re as _re
    safe = _re.sub(r"[^A-Za-z0-9_.-]", "", file)
    if not safe.startswith("ou_mrs_") or not safe.endswith(".log"):
        raise HTTPException(status_code=400, detail="invalid filename")
    p = (BOT_DIR / "logs" / safe)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return PlainTextResponse(content=p.read_text(errors="replace"), headers={"Content-Disposition": f'attachment; filename="{safe}"'})
@app.get("/api/metrics", dependencies=[Depends(need_auth)])
def api_metrics():
    path = BOT_DIR / "bt_out" / "metrics.json"
    if not path.exists(): return {}
    try: return json.loads(path.read_text())
    except: return {}

@app.get("/api/equity", dependencies=[Depends(need_auth)])
def api_equity():
    import csv
    path = BOT_DIR / "bt_out" / "equity.csv"
    if not path.exists(): return {"rows": []}
    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return {"rows": rows}

_portfolio_cache = {"ts": 0, "data": None}
@app.get("/api/portfolio", dependencies=[Depends(need_auth)])
def api_portfolio():
    # Phase 4a: read from state/live.json instead of re-logging into Angel.
    # The bot pushes fresh portfolio data via live_hook.tick(portfolio=...).
    # Eliminates the dashboard/bot Angel-session ping-pong.
    import time, json
    sp = BOT_DIR / "state" / "live.json"
    if not sp.exists():
        return {"ok": False, "reason": "waiting_for_bot",
                "message": "Bot is not running or has not pushed state yet."}
    try:
        data = json.loads(sp.read_text())
        age = time.time() - data.get("updated_ts", 0)
        portfolio = data.get("portfolio") or {}
        return {
            "ok": True,
            "rms": portfolio.get("rms") if portfolio else None,
            "position": portfolio.get("position") if portfolio else None,
            "portfolio_ts": portfolio.get("ts") if portfolio else None,
            "age_sec": round(age, 1),
            "stale": age > 120,
            "ts": data.get("updated_at"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# PREMIUM_API_v1
import os as _os_pv1
from datetime import datetime as _dt_pv1

@app.get("/api/health", dependencies=[Depends(need_auth)])
def api_health():
    try:
        import psutil, time as _t
        return {"cpu_percent": psutil.cpu_percent(interval=0.1), "memory_percent": psutil.virtual_memory().percent, "disk_percent": psutil.disk_usage("/").percent, "uptime_seconds": int(_t.time() - psutil.boot_time())}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/market-status", dependencies=[Depends(need_auth)])
def api_market_status():
    try:
        from zoneinfo import ZoneInfo
        now = _dt_pv1.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now = _dt_pv1.now()
    wd = now.weekday(); hm = now.hour * 60 + now.minute
    if wd >= 5: status, reason = "closed", "weekend"
    elif 540 <= hm < 555: status, reason = "pre_open", "pre-market"
    elif 555 <= hm < 930: status, reason = "open", "regular hours"
    else: status, reason = "closed", "after hours"
    return {"status": status, "reason": reason, "now_ist": now.isoformat()}

@app.get("/api/daily-pnl", dependencies=[Depends(need_auth)])
def api_daily_pnl():
    # Phase 8n.2: merge backtest history + live trades.jsonl for unified heatmap
    import csv, json
    from collections import defaultdict
    days = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0, "live": 0, "bt": 0})
    bt_path = BOT_DIR / "bt_out" / "trades.csv"
    if bt_path.exists():
        with bt_path.open() as f:
            for row in csv.DictReader(f):
                d = (row.get("exit_ts") or row.get("entry_ts") or "")[:10]
                if not d: continue
                try: p = float(row.get("pnl") or 0)
                except: p = 0
                days[d]["pnl"] += p; days[d]["trades"] += 1; days[d]["bt"] += 1
                if p > 0: days[d]["wins"] += 1
    live_path = BOT_DIR / "trades.jsonl"
    if live_path.exists():
        with live_path.open() as f:
            for line in f:
                try: row = json.loads(line)
                except: continue
                d = (row.get("exit_ts") or row.get("entry_ts") or "")[:10]
                if not d: continue
                try: p = float(row.get("pnl") or 0)
                except: p = 0
                days[d]["pnl"] += p; days[d]["trades"] += 1; days[d]["live"] += 1
                if p > 0: days[d]["wins"] += 1
    return {"rows": [{"date": d, **v, "pnl": round(v["pnl"], 2)} for d, v in sorted(days.items())]}

@app.get("/api/drawdown", dependencies=[Depends(need_auth)])
def api_drawdown():
    """Phase 9.8f.47: merge scaled backtest equity.csv with live trades.jsonl daily PnL for through-today curve."""
    import csv, json as _json
    bt_path = BOT_DIR / "bt_out" / "equity.csv"
    trades_path = BOT_DIR / "trades.jsonl"
    try: live_capital = float(_os_pv1.getenv("CAPITAL", 3750000))
    except: live_capital = 3750000.0
    rows = []
    bt_start_eq = None
    bt_end_eq = None
    bt_end_date = None
    if bt_path.exists():
        with bt_path.open() as fh:
            for r in csv.DictReader(fh):
                try: eq = float(r.get("equity") or 0)
                except: eq = 0
                if bt_start_eq is None and eq > 0: bt_start_eq = eq
                rows.append({"date": r.get("date"), "_raw": eq, "source": "bt"})
                bt_end_eq = eq
                bt_end_date = r.get("date")
    scale = (live_capital / bt_start_eq) if (bt_start_eq and bt_start_eq > 0) else 1.0
    for row in rows:
        row["equity"] = row.pop("_raw") * scale
    seed_eq = (bt_end_eq * scale) if bt_end_eq else live_capital
    daily_pnl = {}
    if trades_path.exists():
        with trades_path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line: continue
                try: t = _json.loads(line)
                except: continue
                exit_ts = t.get("exit_ts") or t.get("entry_ts") or ""
                date_part = exit_ts[:10] if exit_ts else None
                if not date_part: continue
                if bt_end_date and date_part <= bt_end_date: continue
                pnl = float(t.get("pnl") or 0)
                daily_pnl[date_part] = daily_pnl.get(date_part, 0.0) + pnl
    running_eq = seed_eq
    for date_str in sorted(daily_pnl.keys()):
        running_eq = running_eq + daily_pnl[date_str]
        rows.append({"date": date_str, "equity": running_eq, "source": "live", "pnl_day": daily_pnl[date_str]})
    peak = 0.0
    for rr in rows:
        eq = rr["equity"]
        if eq > peak: peak = eq
        dd = (eq - peak) / peak * 100 if peak > 0 else 0
        rr["dd_pct"] = round(dd, 3)
    return {"rows": rows, "live_capital": live_capital, "scale": round(scale, 3), "bt_end_date": bt_end_date, "live_days": len(daily_pnl)}

@app.get("/api/strategy", dependencies=[Depends(need_auth)])
def api_strategy():
    # 8o.3a: multi-symbol return (cfg duplicated locally to avoid ou_mrs import)
    _CFG = {
        "BNF": {"env": "BANKNIFTY_FUT_SYMBOL", "default": "BANKNIFTY26MAY26FUT", "lot_size": 30, "margin": 75000},
        "NF":  {"env": "NIFTY_FUT_SYMBOL",    "default": "NIFTY26MAY26FUT",    "lot_size": 65, "margin": 50000},
        "FNF": {"env": "FINNIFTY_FUT_SYMBOL", "default": "FINNIFTY26MAY26FUT", "lot_size": 60, "margin": 60000},
    }
    _capital = float(_os_pv1.getenv("CAPITAL", 3750000))
    _inst = [s.strip().upper() for s in _os_pv1.getenv("INSTRUMENTS", "BNF").split(",") if s.strip().upper() in _CFG] or ["BNF"]
    def _max_lots(cap, k): return max(1, min(50, int(cap) // _CFG[k]["margin"]))
    def _tier(cap):
        if cap < 200000: return "SEED"
        if cap < 1500000: return "GROWTH"
        if cap < 2500000: return "INSTITUTIONAL"
        if cap < 5000000: return "HEDGE_FUND"
        return "QUANT_ELITE"
    _symbols = [{"key": k, "symbol": _os_pv1.getenv(_CFG[k]["env"], _CFG[k]["default"]), "lot_size": _CFG[k]["lot_size"], "margin_per_lot": _CFG[k]["margin"], "max_lots": _max_lots(_capital, k)} for k in _inst]
    return {"symbols": _symbols, "capital": _capital, "capital_tier": _tier(_capital), "z_entry": float(_os_pv1.getenv("Z_ENTRY", 1.5)), "z_stop": float(_os_pv1.getenv("Z_STOP", 3.5)), "window": int(_os_pv1.getenv("WINDOW", 40)), "live_mode": _os_pv1.getenv("LIVE", "false").lower() == "true", "symbol": _symbols[0]["symbol"] if _symbols else "", "lot_size": _symbols[0]["lot_size"] if _symbols else 15}



# ========== LIVE_STATE_v1 ==========
@app.get("/api/live/state", dependencies=[Depends(need_auth)])
def api_live_state(symbol: str = "BNF"):
    # 8o.3b: per-symbol routing -- primary BNF reads rich legacy live.json,
    # NF/FNF read per-symbol lite live_<SYM>.json. Frontend shows banner when lite.
    import time, json
    sym = (symbol or "BNF").upper().strip()
    if sym not in ("BNF", "NF", "FNF"):
        sym = "BNF"
    if sym == "BNF":
        sp = BOT_DIR / "state" / "live.json"
    else:
        sp = BOT_DIR / "state" / f"live_{sym}.json"
    if not sp.exists():
        return {"ok": False, "reason": "waiting_for_bot",
                "active_symbol": sym, "is_lite": (sym != "BNF"),
                "message": "Add live_hook.tick(...) in ou_mrs.py main loop, then restart."}
    try:
        data = json.loads(sp.read_text())
        age = time.time() - data.get("updated_ts", 0)
        data["age_sec"] = round(age, 1)
        data["stale"] = age > 120
        data["ok"] = True
        data["active_symbol"] = sym
        data["is_lite"] = not bool(data.get("intraday_candles")) and not bool(data.get("depth"))
        data["source_file"] = sp.name
        return data
    except Exception as e:
        return {"ok": False, "reason": "parse_error", "error": str(e)[:200],
                "active_symbol": sym, "is_lite": (sym != "BNF")}


# Phase 8f.5: Tradetron-compatible signal feed

@app.get('/api/risk', dependencies=[Depends(need_auth)])
def api_risk():
    # Phase 9.8d: load PropFirmMonitor snapshot for flat-field overlay
    try:
        import json as _jp98d, pathlib as _pp98d
        _pfm_p98d = _jp98d.loads(_pp98d.Path('state/pfm.json').read_text())
    except Exception:
        _pfm_p98d = {}
    import sys, json as _json
    from datetime import datetime as _dt
    sys.path.insert(0, str(BOT_DIR))
    try:
        from tier_policy import get_policy as _gp
    except Exception:
        _gp = None
    base_capital = int(os.environ.get("CAPITAL", 3750000))
    total_pnl = 0.0
    csv_path = BOT_DIR / 'bt_out' / 'trades.csv'
    if csv_path.exists():
        try:
            for row in csv_path.read_text().splitlines()[1:]:
                parts = row.split(',')
                if len(parts) >= 7:
                    try: total_pnl += float(parts[6])
                    except Exception: pass
        except Exception: pass
    jsonl_path = BOT_DIR / 'trades.jsonl'
    if jsonl_path.exists():
        try:
            for line in jsonl_path.read_text().splitlines():
                try: total_pnl += float(_json.loads(line).get('pnl', 0))
                except Exception: pass
        except Exception: pass
    # Phase 9.5f: aggregate unrealized PnL from state/live_*.json
    import glob as _glob_p95f, time as _time_p95f
    _now_ts_p95f = int(_time_p95f.time())
    unrealized_pnl = 0.0
    unrealized_today = 0.0
    positions_open = 0
    freshness_stale_count = 0
    for _f in _glob_p95f.glob(str(BOT_DIR / "state" / "live_*.json")):
        try:
            d = _json.loads(open(_f).read())
            pos = d.get("position") or {}
            if not pos.get("side"): continue
            ltp = float(d.get("ltp") or 0)
            entry = float(pos.get("entry") or pos.get("entry_px") or 0)
            qty = int(pos.get("qty") or 0)
            lot = int(d.get("lot_size") or 1)
            if ltp <= 0 or entry <= 0 or qty <= 0: continue
            sign = 1 if pos.get("side") == "BUY" else -1
            u = (ltp - entry) * sign * qty * lot
            unrealized_pnl += u
            unrealized_today += u
            positions_open += 1
            upd = int(d.get("updated_ts") or 0)
            if upd and (_now_ts_p95f - upd) > 300: freshness_stale_count += 1
        except Exception:
            pass
    realized_pnl = total_pnl
    total_pnl = total_pnl + unrealized_pnl
    effective_capital = max(base_capital, int(base_capital + total_pnl))
    if _gp:
        tier, policy = _gp(effective_capital)
        daily_loss_pct = float(policy.get('daily_loss_cap_pct', 0.008))
    else:
        tier, daily_loss_pct = 'UNKNOWN', 0.008
    max_dd_pct = 0.06
    monthly_target_pct = 0.05
    consistency_max = 0.40
    min_days = 4
    daily_loss_lim = effective_capital * daily_loss_pct
    max_dd_lim = effective_capital * max_dd_pct
    daily = {}
    def _add(d, p):
        daily[d] = daily.get(d, 0.0) + float(p)
    if csv_path.exists():
        try:
            for row in csv_path.read_text().splitlines()[1:]:
                parts = row.split(',')
                if len(parts) >= 7:
                    dk = parts[1][:10] if len(parts[1]) >= 10 else parts[1]
                    try: _add(dk, float(parts[6]))
                    except Exception: pass
        except Exception: pass
    if jsonl_path.exists():
        try:
            for line in jsonl_path.read_text().splitlines():
                try:
                    rec = _json.loads(line)
                    ts = rec.get('exit_ts') or rec.get('ts') or ''
                    _add(ts[:10], float(rec.get('pnl', 0)))
                except Exception: pass
        except Exception: pass
    # Phase 9.5f: include today unrealized in daily aggregates
    if unrealized_today != 0:
        _today_dk_p95f = _dt.now().strftime("%Y-%m-%d")
        _add(_today_dk_p95f, unrealized_today)
    days_traded = sum(1 for v in daily.values() if v != 0)
    cum_pnl = sum(daily.values())
    sorted_days = sorted(daily.items())
    eq = float(base_capital); peak = eq; max_dd = 0.0
    today_loss = 0.0
    today = _dt.now().strftime('%Y-%m-%d')
    for d, pnl in sorted_days:
        eq += pnl
        if eq > peak: peak = eq
        dd = peak - eq
        if dd > max_dd: max_dd = dd
        if d == today and pnl < 0:
            today_loss = -pnl
    pos_days = [v for v in daily.values() if v > 0]
    best_day = max(pos_days) if pos_days else 0.0
    cons_frac = (best_day / sum(pos_days)) if pos_days else 0.0
    def _sev_u(p):
        if p >= 0.80: return 'err'
        if p >= 0.60: return 'warn'
        return 'ok'
    def _sev_p(p):
        if p >= 0.80: return 'ok'
        if p >= 0.40: return 'warn'
        return 'err'
    dl_pct = (today_loss / daily_loss_lim) if daily_loss_lim > 0 else 0.0
    dd_pct = (max_dd / max_dd_lim) if max_dd_lim > 0 else 0.0
    pt_pct = (cum_pnl / (effective_capital * monthly_target_pct)) if effective_capital > 0 else 0.0
    dt_pct = min(1.0, days_traded / float(min_days)) if min_days > 0 else 1.0
    cs_pct = cons_frac
    # Phase 8r.2: split breach (DL+DD only) from progress (monthly target only)
    breach_sevs = [_sev_u(dl_pct), _sev_u(dd_pct)]
    if 'err' in breach_sevs: status = 'BREACHED'
    elif 'warn' in breach_sevs: status = 'AT-RISK'
    else: status = 'HEALTHY'
    if pt_pct >= 1.0: progress_label = 'AHEAD'
    elif pt_pct >= 0.4: progress_label = 'ON-TRACK'
    else: progress_label = 'BEHIND'
    # Phase 9.8d: overlay flat PFM fields onto response
    _resp_p98d = {
        'tier': tier,
        'capital': effective_capital,
        'base_capital': base_capital,
        'cumulative_pnl': round(cum_pnl, 2),
        'status': status,
        'breach_status': status,
        'progress_label': progress_label,
        'daily_loss': {'used': round(today_loss, 2), 'limit': round(daily_loss_lim, 2), 'pct': round(dl_pct, 4), 'limit_pct': daily_loss_pct, 'sev': _sev_u(dl_pct)},
        'max_dd': {'used': round(max_dd, 2), 'limit': round(max_dd_lim, 2), 'pct': round(dd_pct, 4), 'limit_pct': max_dd_pct, 'sev': _sev_u(dd_pct)},
        'monthly_target': {'progress': round(cum_pnl, 2), 'target': round(effective_capital * monthly_target_pct, 2), 'pct': round(pt_pct, 4), 'target_pct': monthly_target_pct, 'sev': _sev_p(max(0.0, min(1.0, pt_pct)))},
        'days_traded': {'current': days_traded, 'min': min_days, 'pct': round(dt_pct, 4), 'sev': _sev_p(dt_pct)},
        'consistency': {'frac': round(cons_frac, 4), 'max_share': consistency_max, 'pct': round(cs_pct, 4), 'sev': _sev_u(cs_pct)},
    }
    try:
        if isinstance(_resp_p98d, dict):
            _resp_p98d['peak_equity']            = float(_pfm_p98d.get('peak_equity', 0) or 0)
            _resp_p98d['days_traded']            = int(_pfm_p98d.get('days_traded', 0) or 0)
            _resp_p98d['best_day_pnl']           = float(_pfm_p98d.get('best_day_pnl', 0) or 0)
            _resp_p98d['consistency_frac']       = float(_pfm_p98d.get('consistency_frac', 0) or 0)
            _resp_p98d['consistency_flag']       = bool(_pfm_p98d.get('consistency_flag', False))
            _resp_p98d['profit_target_progress'] = float(_pfm_p98d.get('profit_target_progress', 0) or 0)
    except Exception:
        pass
    return _resp_p98d

@app.get('/api/challenge', dependencies=[Depends(need_auth)])
def api_challenge_alias():
    return api_risk()

@app.get('/api/regime', dependencies=[Depends(need_auth)])
def api_regime():
    import sys, json as _json
    rm_path = BOT_DIR / 'bt_out' / 'regime_metrics.json'
    regimes = {}
    if rm_path.exists():
        try: regimes = _json.loads(rm_path.read_text())
        except Exception: pass
    current = 'UNKNOWN'
    current_adx = None
    try:
        sys.path.insert(0, str(BOT_DIR))
        from regime import classify_regime, wilder_adx
        import pandas as pd
        ppath = BOT_DIR / 'data' / 'BANKNIFTY_FUT_1min.parquet'
        if ppath.exists():
            df = pd.read_parquet(ppath).tail(200)
            current = str(classify_regime(df).iloc[-1])
            av = float(wilder_adx(df)['adx'].iloc[-1])
            if av == av: current_adx = round(av, 2)
    except Exception: pass
    return {'regimes': regimes, 'current': current, 'current_adx': current_adx}


@app.get('/api/regime/timeseries', dependencies=[Depends(need_auth)])
def api_regime_timeseries():
    # Phase 9.8x: per-day regime classification for equity curve overlay
    import sys, json as _json
    cache_path = BOT_DIR / 'bt_out' / 'regime_timeseries.json'
    parquet_path = BOT_DIR / 'data' / 'BANKNIFTY_FUT_1min.parquet'
    if not parquet_path.exists():
        return {'rows': []}
    if cache_path.exists():
        try:
            if cache_path.stat().st_mtime >= parquet_path.stat().st_mtime:
                return _json.loads(cache_path.read_text())
        except Exception:
            pass
    try:
        sys.path.insert(0, str(BOT_DIR))
        from regime import classify_regime, wilder_adx
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        for col in ['date', 'datetime', 'timestamp', 'time']:
            if col in df.columns:
                df = df.set_index(col)
                break
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass
        regime_series = classify_regime(df)
        adx_series = wilder_adx(df)['adx']
        df_agg = pd.DataFrame({'regime': regime_series, 'adx': adx_series}, index=df.index)
        if isinstance(df_agg.index, pd.DatetimeIndex):
            daily = df_agg.groupby(df_agg.index.date).agg({'regime':'last', 'adx':'last'})
        else:
            return {'rows': [], 'error': 'index not datetime'}
        rows = []
        for d, r in daily.iterrows():
            rg = str(r['regime']) if r['regime'] is not None else 'UNKNOWN'
            ax = float(r['adx']) if r['adx'] == r['adx'] else None
            rows.append({'date': str(d), 'regime': rg, 'adx': round(ax,2) if ax is not None else None})
        out = {'rows': rows}
        try: cache_path.write_text(_json.dumps(out))
        except Exception: pass
        return out
    except Exception as e:
        return {'rows': [], 'error': str(e)}

@app.get("/api/signals.json")
def api_signals_json(token: str = ""):
    expected = os.environ.get("SIGNAL_API_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(status_code=401, detail="invalid token")
    return signal_publisher.read_signal()


# Phase 8g.6: per-symbol state for dashboard cards
@app.get("/api/symbols", dependencies=[Depends(need_auth)])
def api_symbols():
    """Returns {symbols: {BNF,NF,FNF: {...}}, aggregate: {...}}."""
    state_dir = BOT_DIR / "state"
    out = {"symbols": {}, "aggregate": {"trades_today": 0, "pnl_today": 0.0, "live_positions": 0, "any_kill": False, "ts": int(time.time())}}
    if not state_dir.exists():
        return out
    for sym_file in sorted(state_dir.glob("live_*.json")):
        sym = sym_file.stem.replace("live_", "")
        try:
            data = json.loads(sym_file.read_text())
            out["symbols"][sym] = data
            out["aggregate"]["trades_today"] += int(data.get("trades_today") or 0)
            out["aggregate"]["pnl_today"] += float(data.get("pnl_today") or 0.0)
            if data.get("position"):
                out["aggregate"]["live_positions"] += 1
            if data.get("kill"):
                out["aggregate"]["any_kill"] = True
        except Exception:
            pass
    out["aggregate"]["pnl_today"] = round(out["aggregate"]["pnl_today"], 2)
    return out


# ============================================================
# Phase 9.6: WebSocket tick pump + Server-Sent Events endpoint
# ============================================================
import asyncio as _p96_asyncio
import json as _p96_json
import logging as _p96_logging
from fastapi.responses import StreamingResponse as _P96StreamingResponse

from dashboard.tick_broker import broker as _p96_broker
from dashboard.ws_tick_pump import pump as _p96_pump

_p96_log = _p96_logging.getLogger("p96")


@app.on_event("startup")
async def _p96_startup():
    try:
        _p96_broker.attach_loop(_p96_asyncio.get_running_loop())
        _p96_pump.start()
        _p96_log.info("[p96] tick pump scheduled")
    except Exception:
        _p96_log.exception("[p96] startup failed (dashboard continues)")


@app.on_event("shutdown")
async def _p96_shutdown():
    try:
        _p96_pump.stop()
    except Exception:
        pass


@app.get("/sse/ticks")
async def sse_ticks(session: str = Cookie(default=None)):
    if not is_authed(session):
        raise HTTPException(status_code=401)
    q = _p96_broker.subscribe()

    async def event_gen():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    tick = await _p96_asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {_p96_json.dumps(tick)}\n\n"
                except _p96_asyncio.TimeoutError:
                    yield ": ka\n\n"
        finally:
            _p96_broker.unsubscribe(q)

    return _P96StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/ticks/stats", dependencies=[Depends(need_auth)])
def api_ticks_stats():
    return _p96_broker.stats()


@app.get("/api/export/trades", dependencies=[Depends(need_auth)])
def api_export_trades():
    import json, csv, io
    from fastapi.responses import Response
    sp = BOT_DIR / "trades.jsonl"
    if not sp.exists(): return {"error":"no live trades"}
    rows = [json.loads(l) for l in sp.read_text().splitlines() if l.strip()]
    buf = io.StringIO(); w = csv.writer(buf)
    cols = ["entry_ts","exit_ts","side","qty","entry","exit","pnl","reason"]
    w.writerow(cols)
    for r in rows: w.writerow([r.get(k,"") for k in cols])
    return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=trades_live.csv"})


# ===== Phase 9.8f Bloomberg-grade endpoints =====
import math as _p98f_math
import json as _p98f_json
import pathlib as _p98f_path

def _p98f_read_daily():
    candidates = [_p98f_path.Path("data/daily_pnl.json"), _p98f_path.Path("bt_out/daily_pnl.json"), _p98f_path.Path("data/pfm.json")]
    for c in candidates:
        if c.exists():
            try:
                d = _p98f_json.loads(c.read_text())
                rows = d.get("rows") if isinstance(d, dict) else d
                if isinstance(rows, list):
                    return rows
            except Exception:
                continue
    return []

@app.get("/api/option-chain", dependencies=[Depends(need_auth)])
async def p98f_option_chain(symbol: str = "BNF", expiry: str = ""):
    """Phase 9.8f.48a: synthetic options chain preview using REAL live spot from state/live_<SYM>.json + Black-Scholes Greeks.
    OI/Volume/IV are synthetic gradients peaked at ATM (deterministic from spot). Drop-in swap with Angel One data in Phase E1."""
    import math, json as _oj, time as _ot
    cfg = {"BNF": (100, "live_BNF.json", "BANKNIFTY"), "NF": (50, "live_NF.json", "NIFTY"), "FNF": (100, "live_FNF.json", "FINNIFTY")}
    key = symbol.upper()
    if key not in cfg: key = "BNF"
    step, state_file, idx_name = cfg[key]
    spot = 0.0
    ts = 0
    sp = BOT_DIR / "state" / state_file
    if sp.exists():
        try:
            d = _oj.loads(sp.read_text())
            spot = float(d.get("ltp") or d.get("mean") or 0)
            ts = int(d.get("ts") or _ot.time())
        except:
            pass
    if spot <= 0:
        spot = {"BNF": 54000.0, "NF": 23500.0, "FNF": 24000.0}[key]
    atm = round(spot / step) * step
    strikes_list = [atm + (i - 5) * step for i in range(11)]
    T = 7.0 / 365.0
    r = 0.06
    base_iv = 0.16
    from math import erf, exp, log, pi, sqrt
    def N(x): return 0.5 * (1.0 + erf(x / sqrt(2.0)))
    def n_pdf(x): return exp(-x * x / 2.0) / sqrt(2.0 * pi)
    def _bs(S, K, T, r, iv, is_call):
        if T <= 0 or iv <= 0 or K <= 0 or S <= 0:
            intrinsic = max(S - K, 0.0) if is_call else max(K - S, 0.0)
            return (intrinsic, 0.0, 0.0, 0.0, 0.0)
        sT = sqrt(T)
        d1 = (log(S / K) + (r + iv * iv / 2.0) * T) / (iv * sT)
        d2 = d1 - iv * sT
        if is_call:
            price = S * N(d1) - K * exp(-r * T) * N(d2)
            delta = N(d1)
            theta = (-S * n_pdf(d1) * iv / (2.0 * sT) - r * K * exp(-r * T) * N(d2)) / 365.0
        else:
            price = K * exp(-r * T) * N(-d2) - S * N(-d1)
            delta = N(d1) - 1.0
            theta = (-S * n_pdf(d1) * iv / (2.0 * sT) + r * K * exp(-r * T) * N(-d2)) / 365.0
        gamma = n_pdf(d1) / (S * iv * sT)
        vega = S * n_pdf(d1) * sT / 100.0
        return (price, delta, gamma, theta, vega)
    strikes = []
    total_ce_oi = 0
    total_pe_oi = 0
    for K in strikes_list:
        moneyness = abs(K - atm) / max(atm, 1)
        iv = base_iv + 0.10 * moneyness
        dist = (K - atm) / step
        decay = exp(-(dist * dist) / 6.0)
        ce_oi = int(80000 * decay * (1.0 if K >= atm else 0.6))
        pe_oi = int(80000 * decay * (1.0 if K <= atm else 0.6))
        ce_vol = int(ce_oi * 0.35)
        pe_vol = int(pe_oi * 0.35)
        cp, cd, cg, ct, cv = _bs(spot, K, T, r, iv, True)
        pp, pd, pg, pt, pv = _bs(spot, K, T, r, iv, False)
        strikes.append({
            "strike": int(K),
            "ce": {"ltp": round(cp, 2), "oi": ce_oi, "chgOi": int(ce_oi * 0.05), "volume": ce_vol, "iv": round(iv * 100, 2), "delta": round(cd, 3), "gamma": round(cg, 5), "theta": round(ct, 2), "vega": round(cv, 2)},
            "pe": {"ltp": round(pp, 2), "oi": pe_oi, "chgOi": int(pe_oi * 0.05), "volume": pe_vol, "iv": round(iv * 100, 2), "delta": round(pd, 3), "gamma": round(pg, 5), "theta": round(pt, 2), "vega": round(pv, 2)}
        })
        total_ce_oi += ce_oi
        total_pe_oi += pe_oi
    pcr = round(total_pe_oi / max(total_ce_oi, 1), 3)
    return {
        "ok": True,
        "mode": "synthetic_preview",
        "symbol": key,
        "underlying": idx_name,
        "spot": round(spot, 2),
        "atm": int(atm),
        "step": step,
        "expiry_days": 7,
        "strikes": strikes,
        "totals": {"call_oi": total_ce_oi, "put_oi": total_pe_oi, "pcr": pcr, "max_pain": int(atm)},
        "ts": ts,
        "note": "Synthetic preview: BS Greeks accurate from REAL spot. OI/Vol/IV are gradients pending Angel One wiring (Phase E1)."
    }
async def p98f_option_chain(symbol: str = "BANKNIFTY", expiry: str = ""):
    return {
        "ok": False,
        "status": "not_wired",
        "symbol": symbol,
        "expiry": expiry,
        "message": "Angel One option chain pending - Phase 9.8f task E1",
        "schema": {
            "strikes": "[{strike, ce:{ltp,oi,chgOi,iv,delta,gamma,theta,vega,volume}, pe:{...}}]",
            "underlying": "{spot, atm, futPrem}",
            "totals": "{call_oi, put_oi, pcr}"
        }
    }

@app.get("/api/rolling-metrics", dependencies=[Depends(need_auth)])
async def p98f_rolling_metrics(window: int = 20):
    daily = _p98f_read_daily()
    if not daily:
        return {"ok": True, "rows": [], "window": window, "message": "no daily P&L data found"}
    pnls = [(r.get("pnl") or 0) for r in daily]
    dates = [r.get("date") for r in daily]
    out = []
    for i in range(len(pnls)):
        lo = max(0, i - window + 1)
        win = pnls[lo:i+1]
        n = len(win)
        if n < 2:
            out.append({"date": dates[i], "sharpe": None, "sortino": None, "calmar": None, "n": n})
            continue
        mean = sum(win) / n
        var = sum((x - mean) * (x - mean) for x in win) / max(1, n - 1)
        sd = _p98f_math.sqrt(var) if var > 0 else 0
        neg = [x for x in win if x < 0]
        downvar = (sum(x * x for x in neg) / max(1, len(neg))) if neg else 0
        downsd = _p98f_math.sqrt(downvar) if downvar > 0 else 0
        sharpe = (mean / sd * _p98f_math.sqrt(252)) if sd > 0 else None
        sortino = (mean / downsd * _p98f_math.sqrt(252)) if downsd > 0 else None
        cum = 0; peak = 0; mdd = 0
        for x in win:
            cum += x
            peak = max(peak, cum)
            mdd = min(mdd, cum - peak)
        calmar = (mean * 252 / abs(mdd)) if mdd < 0 else None
        out.append({"date": dates[i], "sharpe": round(sharpe, 3) if sharpe is not None else None, "sortino": round(sortino, 3) if sortino is not None else None, "calmar": round(calmar, 3) if calmar is not None else None, "n": n})
    return {"ok": True, "rows": out, "window": window}

@app.get("/api/regime-transitions", dependencies=[Depends(need_auth)])
async def p98f_regime_transitions():
    rm_file = _p98f_path.Path("bt_out/regime_timeseries.json")
    if not rm_file.exists():
        return {"ok": False, "message": "bt_out/regime_timeseries.json not found"}
    try:
        rm = _p98f_json.loads(rm_file.read_text())
    except Exception as e:
        return {"ok": False, "message": str(e)}
    seq = [r.get("regime") for r in rm.get("rows", [])]
    regimes = ["TREND", "RANGE", "CHOP"]
    counts = {a: {b: 0 for b in regimes} for a in regimes}
    totals = {a: 0 for a in regimes}
    for i in range(len(seq) - 1):
        a = seq[i]; b = seq[i+1]
        if a in counts and b in counts[a]:
            counts[a][b] += 1
            totals[a] += 1
    probs = {a: {b: (round(counts[a][b] / totals[a], 4) if totals[a] else 0) for b in regimes} for a in regimes}
    return {"ok": True, "regimes": regimes, "counts": counts, "probs": probs, "n_obs": len(seq)}

# ===== Phase 9.8f.29: re-bind _p98f_read_daily to real trade sources =====
def _p98f_read_daily():
    import csv as _csv
    from collections import defaultdict as _dd
    days = _dd(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    bt_path = _p98f_path.Path("bt_out/trades.csv")
    if bt_path.exists():
        try:
            with bt_path.open() as f:
                for row in _csv.DictReader(f):
                    d = (row.get("exit_ts") or row.get("entry_ts") or "")[:10]
                    if not d: continue
                    try: p = float(row.get("pnl") or 0)
                    except: p = 0
                    days[d]["pnl"] += p; days[d]["trades"] += 1
                    if p > 0: days[d]["wins"] += 1
        except Exception: pass
    live_path = _p98f_path.Path("trades.jsonl")
    if live_path.exists():
        try:
            with live_path.open() as f:
                for line in f:
                    try: row = _p98f_json.loads(line)
                    except: continue
                    d = (row.get("exit_ts") or row.get("entry_ts") or "")[:10]
                    if not d: continue
                    try: p = float(row.get("pnl") or 0)
                    except: p = 0
                    days[d]["pnl"] += p; days[d]["trades"] += 1
                    if p > 0: days[d]["wins"] += 1
        except Exception: pass
    return [dict(date=d, pnl=round(v["pnl"], 2), trades=v["trades"], wins=v["wins"]) for d, v in sorted(days.items())]

@app.get("/api/monte-carlo", dependencies=[Depends(need_auth)])
def api_monte_carlo():
    import json as _json_mc
    path = BOT_DIR / "bt_out" / "monte_carlo.json"
    if not path.exists():
        return {"ok": False, "error": "monte_carlo.json not found"}
    try:
        return {"ok": True, "data": _json_mc.loads(path.read_text())}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ===== Phase 9.8f.51: SQLite Activity Log - HTTP endpoints + auto-init =====
import os as _os_alog
import sys as _sys_alog
_alog_dir = _os_alog.path.dirname(_os_alog.path.abspath(__file__))
if _alog_dir not in _sys_alog.path:
    _sys_alog.path.insert(0, _alog_dir)
import activity_log as _p98f_alog

@app.on_event("startup")
def _p98f_activity_log_init():
    try:
        _path = _p98f_alog.init_db()
        print("[p98f.51] activity_log.db initialized at " + str(_path))
    except Exception as _e_alog:
        print("[p98f.51] activity_log init failed: " + str(_e_alog))

@app.get("/api/activity/recent", dependencies=[Depends(need_auth)])
def api_activity_recent(limit: int = 50, status: str = None, phase: str = None):
    try:
        rows = _p98f_alog.recent(limit=max(1, min(int(limit), 500)), status=status, phase_tag=phase)
        return {"ok": True, "rows": rows, "count": len(rows)}
    except Exception as _e_alog:
        return {"ok": False, "error": str(_e_alog)}

@app.get("/api/activity/stats", dependencies=[Depends(need_auth)])
def api_activity_stats():
    try:
        return {"ok": True, "stats": _p98f_alog.stats()}
    except Exception as _e_alog:
        return {"ok": False, "error": str(_e_alog)}

@app.post("/api/activity/log", dependencies=[Depends(need_auth)])
def api_activity_log_post(payload: dict):
    """Insert one activity row from JSON body. For client-side or external log calls."""
    try:
        if not isinstance(payload, dict) or not payload.get("activity"):
            return {"ok": False, "error": "missing 'activity' field"}
        rid = _p98f_alog.log_activity(
            activity=payload.get("activity"),
            status=payload.get("status", "Done"),
            phase_tag=payload.get("phase_tag"),
            git_sha=payload.get("git_sha"),
            files_touched=payload.get("files_touched"),
            notes=payload.get("notes"),
            command=payload.get("command"),
            output_snippet=payload.get("output_snippet"),
            verification=payload.get("verification"),
            rating=payload.get("rating"),
            pnl_impact=payload.get("pnl_impact"),
            area=payload.get("area"),
            notion_url=payload.get("notion_url"),
        )
        return {"ok": True, "id": rid}
    except Exception as _e_alog:
        return {"ok": False, "error": str(_e_alog)}

# ===== Phase 9.8f.52: rate limiter monitoring endpoint =====
import rate_limit as p98f_rl

@app.get("/api/ratelimit/stats", dependencies=[Depends(need_auth)])
def api_ratelimit_stats():
    try:
        return {"ok": True, "stats": p98f_rl.all_stats()}
    except Exception as e_rl:
        return {"ok": False, "error": str(e_rl)}

# ===== Phase 9.8f.52: rate limiter monitoring endpoint =====
import rate_limit as p98f_rl

@app.get("/api/ratelimit/stats", dependencies=[Depends(need_auth)])
def api_ratelimit_stats():
    try:
        return {"ok": True, "stats": p98f_rl.all_stats()}
    except Exception as e_rl:
        return {"ok": False, "error": str(e_rl)}

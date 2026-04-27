
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
        "capital": int(os.environ.get("CAPITAL", 150000)),
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
    import csv
    path = BOT_DIR / "bt_out" / "equity.csv"
    if not path.exists(): return {"rows": []}
    rows = []; peak = 0.0
    with path.open() as f:
        for row in csv.DictReader(f):
            try: eq = float(row.get("equity") or 0)
            except: eq = 0
            peak = max(peak, eq)
            dd = (eq - peak) / peak * 100 if peak > 0 else 0
            rows.append({"date": row.get("date"), "equity": eq, "dd_pct": round(dd, 3)})
    return {"rows": rows}

@app.get("/api/strategy", dependencies=[Depends(need_auth)])
def api_strategy():
    # 8o.3a: multi-symbol return (cfg duplicated locally to avoid ou_mrs import)
    _CFG = {
        "BNF": {"env": "BANKNIFTY_FUT_SYMBOL", "default": "BANKNIFTY26MAY26FUT", "lot_size": 30, "margin": 75000},
        "NF":  {"env": "NIFTY_FUT_SYMBOL",    "default": "NIFTY26MAY26FUT",    "lot_size": 65, "margin": 50000},
        "FNF": {"env": "FINNIFTY_FUT_SYMBOL", "default": "FINNIFTY26MAY26FUT", "lot_size": 60, "margin": 60000},
    }
    _capital = float(_os_pv1.getenv("CAPITAL", 150000))
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

@app.get("/api/export/trades", dependencies=[Depends(need_auth)])
def api_export_trades():
    from fastapi.responses import FileResponse
    path = BOT_DIR / "bt_out" / "trades.csv"
    if not path.exists(): return {"error": "no trades"}
    return FileResponse(path, filename="trades.csv", media_type="text/csv")


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
    import sys, json as _json
    from datetime import datetime as _dt
    sys.path.insert(0, str(BOT_DIR))
    try:
        from tier_policy import get_policy as _gp
    except Exception:
        _gp = None
    base_capital = int(os.environ.get('CAPITAL', 150000))
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
    return {
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

@app.get('/api/challenge', dependencies=[Depends(need_auth)])
def api_challenge_alias():
    return api_risk()
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

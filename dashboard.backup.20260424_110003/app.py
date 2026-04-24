
import os, json, subprocess, time, secrets, sys
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, Form, Cookie, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import bcrypt
from itsdangerous import URLSafeSerializer, BadSignature
from dotenv import load_dotenv

APP_DIR = Path(__file__).parent
BOT_DIR = APP_DIR.parent
load_dotenv(BOT_DIR / ".env")
sys.path.insert(0, str(BOT_DIR))

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
    return {
        "bot_state": sd_active("ou-mrs.service"),
        "timer_state": sd_active("ou-mrs.timer"),
        "next_run_usec": sd_next("ou-mrs.timer"),
        "latest_heartbeat": hb,
        "heartbeat_count_today": hb_count,
        "server_time": datetime.now().isoformat(),
        "capital": int(os.environ.get("CAPITAL", 150000)),
        "live_mode": os.environ.get("LIVE","false").lower() == "true",
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
def api_log(n: int = 100):
    path = BOT_DIR / "ou_mrs.log"
    if not path.exists(): return {"lines": []}
    return {"lines": path.read_text().splitlines()[-n:]}

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
    # cache 25s to avoid hammering Angel
    if _portfolio_cache["data"] and time.time() - _portfolio_cache["ts"] < 25:
        return _portfolio_cache["data"]
    try:
        from angel_adapter import AngelBroker
        b = AngelBroker().login()
        rms = None; pos = None
        try: rms = b.smart.rmsLimit().get("data")
        except Exception as e: rms = {"error": str(e)}
        try: pos = b.smart.position().get("data")
        except Exception as e: pos = {"error": str(e)}
        data = {"ok": True, "rms": rms, "position": pos, "ts": datetime.now().isoformat()}
    except Exception as e:
        data = {"ok": False, "error": str(e)}
    _portfolio_cache["ts"] = time.time()
    _portfolio_cache["data"] = data
    return data

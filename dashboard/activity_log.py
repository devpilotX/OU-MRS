"""
Phase 9.8f.51: SQLite Activity Log - local mirror of Notion Activity DB.
Provides offline persistence, CLI logging, and HTTP API access.
Stdlib only (sqlite3), no extra deps. WAL mode for concurrent reads.
"""
import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

_DB_PATH = Path(__file__).parent.parent / "data" / "activity_log.db"
_LOCK = threading.RLock()

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notion_url TEXT,
    activity TEXT NOT NULL,
    status TEXT,
    phase_tag TEXT,
    git_sha TEXT,
    files_touched TEXT,
    notes TEXT,
    command TEXT,
    output_snippet TEXT,
    verification TEXT,
    rating INTEGER,
    when_date TEXT,
    pnl_impact REAL,
    area TEXT,
    backup_path TEXT,
    created_at REAL NOT NULL,
    edited_at REAL
);
CREATE INDEX IF NOT EXISTS idx_status ON activities(status);
CREATE INDEX IF NOT EXISTS idx_git_sha ON activities(git_sha);
CREATE INDEX IF NOT EXISTS idx_when ON activities(when_date);
CREATE INDEX IF NOT EXISTS idx_phase ON activities(phase_tag);
CREATE INDEX IF NOT EXISTS idx_created ON activities(created_at DESC);
"""

def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), timeout=10.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c

def init_db():
    with _LOCK:
        c = _conn()
        try:
            c.executescript(SCHEMA_V1)
            c.commit()
        finally:
            c.close()
    return str(_DB_PATH)

def log_activity(activity, status="Done", phase_tag=None, git_sha=None,
                 files_touched=None, notes=None, command=None,
                 output_snippet=None, verification=None, rating=None,
                 when_date=None, pnl_impact=None, area=None,
                 backup_path=None, notion_url=None):
    """Insert one activity row. Returns the auto-incremented row id."""
    init_db()
    now = time.time()
    if when_date is None:
        when_date = time.strftime("%Y-%m-%d")
    with _LOCK:
        c = _conn()
        try:
            cur = c.execute(
                "INSERT INTO activities (notion_url, activity, status, phase_tag, git_sha, "
                "files_touched, notes, command, output_snippet, verification, rating, "
                "when_date, pnl_impact, area, backup_path, created_at, edited_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (notion_url, activity, status, phase_tag, git_sha, files_touched, notes,
                 command, output_snippet, verification, rating, when_date,
                 pnl_impact, area, backup_path, now, now),
            )
            rid = cur.lastrowid
            c.commit()
            return rid
        finally:
            c.close()

def recent(limit=50, status=None, phase_tag=None):
    init_db()
    with _LOCK:
        c = _conn()
        try:
            where = []
            params = []
            if status:
                where.append("status=?")
                params.append(status)
            if phase_tag:
                where.append("phase_tag=?")
                params.append(phase_tag)
            sql = "SELECT * FROM activities"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = c.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()

def stats():
    init_db()
    with _LOCK:
        c = _conn()
        try:
            total = c.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
            done = c.execute("SELECT COUNT(*) FROM activities WHERE status='Done'").fetchone()[0]
            blocked = c.execute("SELECT COUNT(*) FROM activities WHERE status='Blocked'").fetchone()[0]
            in_prog = c.execute("SELECT COUNT(*) FROM activities WHERE status='In progress'").fetchone()[0]
            last = c.execute("SELECT activity, status, when_date, git_sha FROM activities ORDER BY created_at DESC LIMIT 1").fetchone()
            avg_rating = c.execute("SELECT AVG(rating) FROM activities WHERE rating IS NOT NULL").fetchone()[0]
            return {
                "total": total,
                "done": done,
                "blocked": blocked,
                "in_progress": in_prog,
                "avg_rating": round(avg_rating, 2) if avg_rating else None,
                "db_path": str(_DB_PATH),
                "db_size_bytes": _DB_PATH.stat().st_size if _DB_PATH.exists() else 0,
                "last_activity": dict(last) if last else None,
            }
        finally:
            c.close()

def cli_main():
    import argparse
    p = argparse.ArgumentParser(description="Activity log CLI")
    sub = p.add_subparsers(dest="cmd")
    s_log = sub.add_parser("log", help="insert one activity")
    s_log.add_argument("activity")
    s_log.add_argument("--status", default="Done")
    s_log.add_argument("--sha", dest="git_sha")
    s_log.add_argument("--phase", dest="phase_tag")
    s_log.add_argument("--files", dest="files_touched")
    s_log.add_argument("--notes", default=None)
    s_log.add_argument("--rating", type=int, default=None)
    s_log.add_argument("--notion", dest="notion_url")
    s_log.add_argument("--area", default=None)
    s_recent = sub.add_parser("recent", help="show recent activities")
    s_recent.add_argument("--limit", type=int, default=20)
    s_recent.add_argument("--status", default=None)
    s_recent.add_argument("--phase", dest="phase_tag", default=None)
    sub.add_parser("stats", help="show DB stats")
    sub.add_parser("init", help="initialize DB schema")
    args = p.parse_args()
    if args.cmd == "log":
        rid = log_activity(
            activity=args.activity, status=args.status, git_sha=args.git_sha,
            phase_tag=args.phase_tag, files_touched=args.files_touched,
            notes=args.notes, rating=args.rating, notion_url=args.notion_url,
            area=args.area,
        )
        print(json.dumps({"id": rid, "ok": True}))
    elif args.cmd == "recent":
        for r in recent(limit=args.limit, status=args.status, phase_tag=args.phase_tag):
            print(json.dumps(r, default=str))
    elif args.cmd == "stats":
        print(json.dumps(stats(), default=str, indent=2))
    elif args.cmd == "init":
        path = init_db()
        print(json.dumps({"ok": True, "db_path": path}))
    else:
        p.print_help()

if __name__ == "__main__":
    cli_main()

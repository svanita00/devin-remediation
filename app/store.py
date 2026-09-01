"""SQLite persistence for scan runs, findings, and remediation sessions.

Every row is something an engineering leader can point at:
  scan run -> findings by severity -> Devin remediation session -> PR -> ACU cost.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any, Optional

from app.config import settings

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS scan_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id      TEXT,
                repo         TEXT,
                scan_type    TEXT,
                trigger      TEXT,            -- manual | scheduled
                status       TEXT NOT NULL,   -- pending|running|completed|failed|cancelled
                findings_total    INTEGER DEFAULT 0,
                remediations_started INTEGER DEFAULT 0,
                created_at   REAL NOT NULL,
                updated_at   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS remediations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_run_id   INTEGER NOT NULL,
                finding_id    TEXT,
                issue_number  INTEGER,
                title         TEXT,
                severity      TEXT,
                category      TEXT,
                file_path     TEXT,
                session_id    TEXT,
                session_url   TEXT,
                status        TEXT NOT NULL,  -- pending|running|success|needs_attention|failed
                pr_url        TEXT,
                reviewed      INTEGER DEFAULT 0,   -- 1 once a Devin Review has been triggered
                acus_consumed REAL,
                created_at    REAL NOT NULL,
                updated_at    REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL NOT NULL,
                message     TEXT NOT NULL
            );
            """
        )


def log(message: str) -> None:
    with _lock, _conn() as c:
        c.execute("INSERT INTO events (ts, message) VALUES (?, ?)", (time.time(), message))


# --- scan runs ---
def create_scan_run(repo: str, scan_type: str, trigger: str) -> int:
    now = time.time()
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO scan_runs (repo, scan_type, trigger, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (repo, scan_type, trigger, now, now),
        )
        return cur.lastrowid


def update_scan_run(run_id: int, **fields: Any) -> None:
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE scan_runs SET {cols} WHERE id=?", (*fields.values(), run_id))


def list_scan_runs() -> list[dict[str, Any]]:
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM scan_runs ORDER BY id DESC").fetchall()]


# --- remediations ---
def create_remediation(scan_run_id: int, finding: dict[str, Any]) -> int:
    now = time.time()
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO remediations (scan_run_id, finding_id, title, severity, category, "
            "file_path, status, created_at, updated_at) VALUES (?,?,?,?,?,?,'pending',?,?)",
            (scan_run_id, finding.get("finding_id"), finding.get("title"), finding.get("severity"),
             finding.get("category"), finding.get("file_path"), now, now),
        )
        return cur.lastrowid


def update_remediation(rem_id: int, **fields: Any) -> None:
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE remediations SET {cols} WHERE id=?", (*fields.values(), rem_id))


def list_remediations() -> list[dict[str, Any]]:
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM remediations ORDER BY id DESC").fetchall()]


def get_remediation_by_session(session_id: str) -> Optional[dict[str, Any]]:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM remediations WHERE session_id=?", (session_id,)).fetchone()
    return dict(row) if row else None


def get_or_create_live_run(repo: str) -> int:
    """A single scan_run bucket that live-synced remediations attach to."""
    with _lock, _conn() as c:
        row = c.execute("SELECT id FROM scan_runs WHERE trigger='live' LIMIT 1").fetchone()
        if row:
            return row["id"]
        now = time.time()
        cur = c.execute(
            "INSERT INTO scan_runs (repo, scan_type, trigger, status, created_at, updated_at) "
            "VALUES (?, 'security', 'live', 'completed', ?, ?)", (repo, now, now))
        return cur.lastrowid


def upsert_remediation_by_session(scan_run_id: int, session_id: str, **fields: Any) -> None:
    """Insert or update a remediation keyed by devin session id (for live API sync)."""
    now = time.time()
    with _lock, _conn() as c:
        row = c.execute("SELECT id FROM remediations WHERE session_id=?", (session_id,)).fetchone()
        if row:
            fields["updated_at"] = now
            cols = ", ".join(f"{k}=?" for k in fields)
            c.execute(f"UPDATE remediations SET {cols} WHERE id=?", (*fields.values(), row["id"]))
        else:
            fields.update(scan_run_id=scan_run_id, session_id=session_id, created_at=now, updated_at=now)
            cols = ", ".join(fields.keys()); ph = ", ".join("?" for _ in fields)
            c.execute(f"INSERT INTO remediations ({cols}) VALUES ({ph})", tuple(fields.values()))


def list_events(limit: int = 50) -> list[dict[str, Any]]:
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

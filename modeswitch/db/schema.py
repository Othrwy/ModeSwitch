"""
Database schema creation and initial seed data.
Call init_db() once at application startup.
"""
import os
import sqlite3
from pathlib import Path


# MODESWITCH_DB lets tests and experiments run against a throwaway file.
DB_PATH = Path(os.environ.get("MODESWITCH_DB") or
               Path.home() / "AppData" / "Local" / "ModeSwitch" / "modeswitch.db")

SCHEMA_VERSION = 2


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _set_aside_v1_db() -> None:
    """A v1 database has a different shape; keep it as a backup and start fresh."""
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(str(DB_PATH))
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        has_tables = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='time_blocks'"
        ).fetchone()
    finally:
        conn.close()
    if has_tables and version < SCHEMA_VERSION:
        DB_PATH.replace(DB_PATH.with_suffix(".v1.bak"))


def init_db() -> None:
    _set_aside_v1_db()
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                code       TEXT NOT NULL UNIQUE,
                name       TEXT NOT NULL,
                color      TEXT NOT NULL DEFAULT '#888888',
                last_used  TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                counts_as_work INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS days (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL UNIQUE,
                in_time     TEXT,
                out_time    TEXT,
                in_source   TEXT NOT NULL DEFAULT 'manual',
                out_source  TEXT NOT NULL DEFAULT 'computed',
                wfh         INTEGER NOT NULL DEFAULT 1,
                last_seen   TEXT,
                is_holiday  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS time_blocks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                day_id       INTEGER NOT NULL REFERENCES days(id) ON DELETE CASCADE,
                project_id   INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                kind         TEXT NOT NULL DEFAULT 'work',
                start_time   TEXT NOT NULL,
                end_time     TEXT NOT NULL,
                category     TEXT NOT NULL DEFAULT 'A',
                title        TEXT,
                title_manual INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS meetings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                outlook_id  TEXT,
                title       TEXT NOT NULL,
                start_time  TEXT NOT NULL,
                end_time    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date);

            CREATE TABLE IF NOT EXISTS title_rules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern     TEXT NOT NULL UNIQUE,
                project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                category    TEXT NOT NULL DEFAULT 'A'
            );
        """)
        _seed_settings(conn)
        _seed_builtin_projects(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _seed_settings(conn: sqlite3.Connection) -> None:
    defaults = {
        "working_days": "1,2,3,4",   # Mon=1 … Thu=4
        "wfh_days": "1,2,4",         # Mon, Tue, Thu at home; Wed commute
        "target_minutes": "480",
        "lunch_minutes": "60",
        "commute_minutes": "60",
        "day_floor": "05:00",        # power-on events before this are ignored
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def _seed_builtin_projects(conn: sqlite3.Connection) -> None:
    builtins = [
        # code, name, color, counts_as_work, sort_order
        ("OW",   "Other Way","#4A90D9", 1, 1002),
    ]
    for code, name, color, caw, order in builtins:
        conn.execute(
            """INSERT OR IGNORE INTO projects
               (code, name, color, sort_order, is_builtin, counts_as_work)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (code, name, color, order, caw),
        )

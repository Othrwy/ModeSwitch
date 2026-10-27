"""
CRUD helpers for settings, Project, Subtask, Day, TimeBlock, Meeting and TitleRule.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from modeswitch.db.schema import get_connection


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Project:
    id: int
    code: str
    name: str
    color: str
    last_used: Optional[str]
    sort_order: int
    is_builtin: bool
    counts_as_work: bool


@dataclass
class Subtask:
    id: int
    project_id: int
    name: str


@dataclass
class Day:
    id: int
    date: str                # YYYY-MM-DD
    in_time: Optional[str]   # HH:MM — start of work (after any commute)
    out_time: Optional[str]  # HH:MM — end of work (before any commute)
    in_source: str           # manual | detected
    out_source: str          # manual | detected | computed
    wfh: bool
    last_seen: Optional[str]  # HH:MM — last heartbeat while the app was running
    is_holiday: bool


@dataclass
class TimeBlock:
    id: Optional[int]
    day_id: int
    project_id: Optional[int]
    kind: str                # work | lunch | commute
    start_time: str          # HH:MM
    end_time: str            # HH:MM
    subtask_id: Optional[int] = None
    title: Optional[str] = None
    title_manual: bool = False


@dataclass
class Meeting:
    id: Optional[int]
    date: str
    outlook_id: Optional[str]
    title: str
    start_time: str
    end_time: str


@dataclass
class TitleRule:
    id: int
    pattern: str             # lower-case text matched anywhere in a title
    project_id: int
    subtask_id: Optional[int]


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )


def get_int_setting(key: str, default: int) -> int:
    try:
        return int(get_setting(key, str(default)))
    except ValueError:
        return default


def get_day_list_setting(key: str) -> list[int]:
    """Comma-separated ISO weekdays (Mon=1)."""
    return [int(x) for x in get_setting(key).split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        color=row["color"],
        last_used=row["last_used"],
        sort_order=row["sort_order"],
        is_builtin=bool(row["is_builtin"]),
        counts_as_work=bool(row["counts_as_work"]),
    )


def get_all_projects() -> list[Project]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY code ASC").fetchall()
    return [_row_to_project(r) for r in rows]


def get_recent_projects() -> list[Project]:
    """All projects, most recently used first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY last_used DESC NULLS LAST, code ASC"
        ).fetchall()
    return [_row_to_project(r) for r in rows]


def get_project_by_id(project_id: int) -> Optional[Project]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    return _row_to_project(row) if row else None


def create_project(code: str, name: str, color: str) -> Project:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO projects (code, name, color) VALUES (?, ?, ?)",
            (code.upper(), name, color),
        )
    return get_project_by_id(cur.lastrowid)


def update_project(project_id: int, *, code: str = None, name: str = None,
                   color: str = None, last_used: str = None) -> None:
    fields, values = [], []
    if code is not None:
        fields.append("code = ?"); values.append(code.upper())
    if name is not None:
        fields.append("name = ?"); values.append(name)
    if color is not None:
        fields.append("color = ?"); values.append(color)
    if last_used is not None:
        fields.append("last_used = ?"); values.append(last_used)
    if not fields:
        return
    values.append(project_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)


def touch_project(project_id: int) -> None:
    update_project(project_id, last_used=datetime.now().isoformat(timespec="seconds"))


def delete_project(project_id: int) -> None:
    """Sections logged against the project are kept, and become unassigned."""
    with get_connection() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


# ---------------------------------------------------------------------------
# Subtask helpers. A subtask belongs to one project; deleting it leaves the
# sections it was on with just the project.
# ---------------------------------------------------------------------------

def _row_to_subtask(row: sqlite3.Row) -> Subtask:
    return Subtask(id=row["id"], project_id=row["project_id"], name=row["name"])


def get_subtasks(project_id: Optional[int] = None) -> list[Subtask]:
    with get_connection() as conn:
        if project_id is None:
            rows = conn.execute("SELECT * FROM subtasks ORDER BY name COLLATE NOCASE").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM subtasks WHERE project_id = ? ORDER BY name COLLATE NOCASE",
                (project_id,)).fetchall()
    return [_row_to_subtask(r) for r in rows]


def get_or_create_subtask(project_id: int, name: str) -> Subtask:
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO subtasks (project_id, name) VALUES (?, ?)",
                     (project_id, name))
        row = conn.execute("SELECT * FROM subtasks WHERE project_id = ? AND name = ?",
                           (project_id, name)).fetchone()
    return _row_to_subtask(row)


def rename_subtask(subtask_id: int, name: str) -> bool:
    """False if the project already has a subtask by that name."""
    try:
        with get_connection() as conn:
            conn.execute("UPDATE subtasks SET name = ? WHERE id = ?", (name, subtask_id))
    except sqlite3.IntegrityError:
        return False
    return True


def delete_subtask(subtask_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))


# ---------------------------------------------------------------------------
# Day helpers
# ---------------------------------------------------------------------------

def _row_to_day(row: sqlite3.Row) -> Day:
    return Day(
        id=row["id"],
        date=row["date"],
        in_time=row["in_time"],
        out_time=row["out_time"],
        in_source=row["in_source"],
        out_source=row["out_source"],
        wfh=bool(row["wfh"]),
        last_seen=row["last_seen"],
        is_holiday=bool(row["is_holiday"]),
    )


def get_day(date_str: str) -> Optional[Day]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM days WHERE date = ?", (date_str,)
        ).fetchone()
    return _row_to_day(row) if row else None


def get_or_create_day(date_str: str, wfh: bool = True) -> Day:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO days (date, wfh) VALUES (?, ?)", (date_str, int(wfh))
        )
    return get_day(date_str)


def get_unfinished_days(before_date: str) -> list[Day]:
    """Earlier days whose end time was never set by hand or detected."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM days
               WHERE date < ? AND out_source = 'computed' AND last_seen IS NOT NULL""",
            (before_date,),
        ).fetchall()
    return [_row_to_day(r) for r in rows]


def update_day(day_id: int, *, in_time: str = None, out_time: str = None,
               in_source: str = None, out_source: str = None, wfh: bool = None,
               last_seen: str = None, is_holiday: bool = None) -> None:
    fields, values = [], []
    if in_time is not None:
        fields.append("in_time = ?"); values.append(in_time)
    if out_time is not None:
        fields.append("out_time = ?"); values.append(out_time)
    if in_source is not None:
        fields.append("in_source = ?"); values.append(in_source)
    if out_source is not None:
        fields.append("out_source = ?"); values.append(out_source)
    if wfh is not None:
        fields.append("wfh = ?"); values.append(int(wfh))
    if last_seen is not None:
        fields.append("last_seen = ?"); values.append(last_seen)
    if is_holiday is not None:
        fields.append("is_holiday = ?"); values.append(int(is_holiday))
    if not fields:
        return
    values.append(day_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE days SET {', '.join(fields)} WHERE id = ?", values)


# ---------------------------------------------------------------------------
# TimeBlock helpers
# ---------------------------------------------------------------------------

def _row_to_block(row: sqlite3.Row) -> TimeBlock:
    return TimeBlock(
        id=row["id"],
        day_id=row["day_id"],
        project_id=row["project_id"],
        kind=row["kind"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        subtask_id=row["subtask_id"],
        title=row["title"],
        title_manual=bool(row["title_manual"]),
    )


def get_blocks_for_day(day_id: int) -> list[TimeBlock]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM time_blocks WHERE day_id = ? ORDER BY start_time ASC, id ASC",
            (day_id,),
        ).fetchall()
    return [_row_to_block(r) for r in rows]


def replace_blocks(day_id: int, blocks: list[TimeBlock]) -> None:
    """Swap a day's whole set of sections in one transaction."""
    with get_connection() as conn:
        conn.execute("DELETE FROM time_blocks WHERE day_id = ?", (day_id,))
        conn.executemany(
            """INSERT INTO time_blocks
               (day_id, project_id, kind, start_time, end_time, subtask_id, title, title_manual)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(day_id, b.project_id, b.kind, b.start_time, b.end_time,
              b.subtask_id, b.title, int(b.title_manual)) for b in blocks],
        )


# ---------------------------------------------------------------------------
# Meeting helpers (calendar cache — background layer of the timeline)
# ---------------------------------------------------------------------------

def get_meetings(date_str: str) -> list[Meeting]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM meetings WHERE date = ? ORDER BY start_time ASC", (date_str,)
        ).fetchall()
    return [Meeting(id=r["id"], date=r["date"], outlook_id=r["outlook_id"],
                    title=r["title"], start_time=r["start_time"], end_time=r["end_time"])
            for r in rows]


def replace_meetings(date_str: str, meetings: list[Meeting]) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM meetings WHERE date = ?", (date_str,))
        conn.executemany(
            """INSERT INTO meetings (date, outlook_id, title, start_time, end_time)
               VALUES (?, ?, ?, ?, ?)""",
            [(date_str, m.outlook_id, m.title, m.start_time, m.end_time) for m in meetings],
        )


# ---------------------------------------------------------------------------
# Title rule helpers
# ---------------------------------------------------------------------------

def get_rules() -> list[TitleRule]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM title_rules ORDER BY pattern ASC").fetchall()
    return [TitleRule(id=r["id"], pattern=r["pattern"], project_id=r["project_id"],
                      subtask_id=r["subtask_id"]) for r in rows]


def upsert_rule(pattern: str, project_id: int, subtask_id: Optional[int] = None) -> None:
    pattern = pattern.strip().lower()
    if not pattern:
        return
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO title_rules (pattern, project_id, subtask_id) VALUES (?, ?, ?)
               ON CONFLICT(pattern) DO UPDATE SET
                   project_id = excluded.project_id, subtask_id = excluded.subtask_id""",
            (pattern, project_id, subtask_id),
        )


def delete_rule(rule_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM title_rules WHERE id = ?", (rule_id,))

"""
Loading, creating and saving whole days — the glue between DayModel and the database.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from modeswitch.db import models
from modeswitch.db.models import Day, TimeBlock, Meeting
from modeswitch.day_model import (
    DayModel, Section, build_default_day, refresh_titles, apply_rules,
)
from modeswitch.timeutil import to_min, to_hhmm

DEFAULT_START = "08:30"   # used when a past day is added by hand


def default_wfh(day_date: date) -> bool:
    return day_date.isoweekday() in models.get_day_list_setting("wfh_days")


DEFAULT_KIND_COLORS = {"lunch": "#FFA500", "commute": "#808080"}


def target_minutes(day_date: Optional[date] = None) -> int:
    """The nominal working day: one length for every day, or set per weekday."""
    default = models.get_int_setting("target_minutes", 480)
    if day_date is None or models.get_setting("target_same", "1") == "1":
        return default
    return target_by_weekday().get(day_date.isoweekday(), default)


def target_by_weekday() -> dict[int, int]:
    """{isoweekday: minutes} from the 'target_by_day' setting, e.g. '1:480,2:450'."""
    out = {}
    for part in models.get_setting("target_by_day", "").split(","):
        if ":" in part:
            day, mins = part.split(":", 1)
            if day.strip().isdigit() and mins.strip().isdigit():
                out[int(day)] = int(mins)
    return out


def kind_colors() -> dict[str, str]:
    """Colours for lunch and commute sections, editable like a project's."""
    return {kind: models.get_setting(f"{kind}_color", default)
            for kind, default in DEFAULT_KIND_COLORS.items()}


def load_model(day: Day) -> DayModel:
    blocks = models.get_blocks_for_day(day.id)
    return DayModel([
        Section(kind=b.kind, start=to_min(b.start_time), end=to_min(b.end_time),
                project_id=b.project_id, subtask_id=b.subtask_id,
                title=b.title, title_manual=b.title_manual)
        for b in blocks
    ])


def load_meetings(date_str: str) -> list[tuple[int, int, str]]:
    return [(to_min(m.start_time), to_min(m.end_time), m.title)
            for m in models.get_meetings(date_str)]


def load_rules() -> list[tuple[str, int, Optional[int]]]:
    return [(r.pattern, r.project_id, r.subtask_id) for r in models.get_rules()]


def save_model(day: Day, model: DayModel) -> None:
    """Write the sections back, along with the start and end of work they imply."""
    refresh_titles(model, load_meetings(day.date))
    apply_rules(model, load_rules())
    models.replace_blocks(day.id, [
        TimeBlock(id=None, day_id=day.id, project_id=s.project_id, kind=s.kind,
                  start_time=to_hhmm(s.start), end_time=to_hhmm(s.end),
                  subtask_id=s.subtask_id, title=s.title, title_manual=s.title_manual)
        for s in model.sections
    ])
    day.in_time, day.out_time = to_hhmm(model.work_start), to_hhmm(model.work_end)
    models.update_day(day.id, in_time=day.in_time, out_time=day.out_time,
                      in_source=day.in_source, out_source=day.out_source, wfh=day.wfh)


def ensure_day(date_str: str, start: Optional[str] = None,
               in_source: str = "manual") -> Day:
    """Return the day, creating it with the default sections if it has none."""
    day_date = date.fromisoformat(date_str)
    day = models.get_day(date_str)
    if day is None:
        day = models.get_or_create_day(date_str, wfh=default_wfh(day_date))
    if models.get_blocks_for_day(day.id):
        return day

    start = start or day.in_time or DEFAULT_START
    day.in_source, day.out_source = in_source, "computed"
    model = DayModel(build_default_day(
        to_min(start), day.wfh,
        lunch_mins=models.get_int_setting("lunch_minutes", 60),
        commute_mins=models.get_int_setting("commute_minutes", 60),
        target_mins=target_minutes(day_date),
    ))
    save_model(day, model)
    return day


def finalise_past_days(today_str: str) -> None:
    """Fill in forgotten end times from when the laptop was last seen running."""
    for day in models.get_unfinished_days(today_str):
        model = load_model(day)
        if not model.sections:
            continue
        model.set_work_end(to_min(day.last_seen))
        day.out_source = "detected"
        save_model(day, model)


def store_meetings(by_date: dict[str, list[Meeting]]) -> list[str]:
    """Replace the cached meetings for each day given; returns the days that changed.

    Past days with sections are re-saved so their titles and smart defaults follow the
    new meetings. Today is left to the ribbon's timeline, which may be mid-edit.
    """
    today = date.today().isoformat()
    changed = []
    for date_str, meetings in by_date.items():
        new = sorted((to_min(m.start_time), to_min(m.end_time), m.title) for m in meetings)
        if new == sorted(load_meetings(date_str)):
            continue
        models.replace_meetings(date_str, meetings)
        changed.append(date_str)
        day = models.get_day(date_str)
        if date_str != today and day and models.get_blocks_for_day(day.id):
            save_model(day, load_model(day))
    return changed

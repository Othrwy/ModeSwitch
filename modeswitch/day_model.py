"""
DayModel — the sections of one day and the rules for editing them.

A day is an ordered list of sections with no gaps and no overlaps, so
neighbouring sections share a node. Node k is the start of section k; the
last node (k == len(sections)) is the end of the last section.

No Qt and no database in here, so the rules can be tested on their own.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from modeswitch.timeutil import DAY_MAX

MIN_LEN = 5   # shortest a section can be, in minutes

WORK, LUNCH, COMMUTE = "work", "lunch", "commute"


@dataclass
class Section:
    kind: str
    start: int                       # minutes since midnight
    end: int
    project_id: Optional[int] = None
    category: str = "A"
    title: Optional[str] = None
    title_manual: bool = False

    @property
    def duration(self) -> int:
        return self.end - self.start


def build_default_day(start: int, wfh: bool, lunch_mins: int = 60,
                      commute_mins: int = 60, target_mins: int = 480) -> list[Section]:
    """(commute,) blank, lunch, blank (, commute) — an 8h day plus lunch."""
    start = max(0, min(start, DAY_MAX - 4 * MIN_LEN))
    end = min(DAY_MAX, start + target_mins + lunch_mins)
    lunch_start = 12 * 60 if start <= 11 * 60 else start + 60
    lunch_start = min(lunch_start, end - 2 * MIN_LEN)
    lunch_end = min(lunch_start + lunch_mins, end - MIN_LEN)
    sections = [
        Section(WORK, start, lunch_start),
        Section(LUNCH, lunch_start, lunch_end),
        Section(WORK, lunch_end, end),
    ]
    model = DayModel(sections)
    if not wfh:
        model.set_wfh(False, commute_mins)
    return model.sections


class DayModel:
    def __init__(self, sections: list[Section]):
        self.sections = sections

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def node_count(self) -> int:
        return len(self.sections) + 1 if self.sections else 0

    def node_time(self, k: int) -> int:
        if k < len(self.sections):
            return self.sections[k].start
        return self.sections[-1].end

    def _has_morning_commute(self) -> bool:
        return len(self.sections) > 1 and self.sections[0].kind == COMMUTE

    def _has_evening_commute(self) -> bool:
        return len(self.sections) > 1 and self.sections[-1].kind == COMMUTE

    def work_start_node(self) -> int:
        return 1 if self._has_morning_commute() else 0

    def work_end_node(self) -> int:
        n = len(self.sections)
        return n - 1 if self._has_evening_commute() else n

    @property
    def work_start(self) -> int:
        return self.node_time(self.work_start_node())

    @property
    def work_end(self) -> int:
        return self.node_time(self.work_end_node())

    def lunch_minutes(self) -> int:
        return sum(s.duration for s in self.sections if s.kind == LUNCH)

    def worked_minutes(self) -> int:
        return self.work_end - self.work_start - self.lunch_minutes()

    def credit(self, target_mins: int) -> int:
        return self.worked_minutes() - target_mins

    def summary(self) -> list[tuple[Optional[int], str, int]]:
        """(project_id, category, minutes) per project-and-letter pair, longest first."""
        totals: dict[tuple[Optional[int], str], int] = {}
        for s in self.sections:
            if s.kind == WORK:
                key = (s.project_id, s.category)
                totals[key] = totals.get(key, 0) + s.duration
        rows = [(pid, cat, mins) for (pid, cat), mins in totals.items()]
        rows.sort(key=lambda r: (r[0] is None, -r[2]))
        return rows

    # ------------------------------------------------------------------
    # Node and section moves
    # ------------------------------------------------------------------
    def node_bounds(self, k: int) -> tuple[int, int]:
        n = len(self.sections)
        lo = self.sections[k - 1].start + MIN_LEN if k > 0 else 0
        hi = self.sections[k].end - MIN_LEN if k < n else DAY_MAX
        return lo, hi

    def move_node(self, k: int, t: int) -> None:
        """Move one node; the sections either side change length.

        The start-of-work and end-of-work nodes carry their commute section
        along with them instead of squeezing it.
        """
        n = len(self.sections)
        if k == 1 and self._has_morning_commute():
            self._set_work_start(t)
            return
        if k == n - 1 and self._has_evening_commute():
            self.set_work_end(t)
            return
        lo, hi = self.node_bounds(k)
        t = max(lo, min(hi, t))
        if k > 0:
            self.sections[k - 1].end = t
        if k < n:
            self.sections[k].start = t

    def _set_work_start(self, t: int) -> None:
        commute, first = self.sections[0], self.sections[1]
        t = max(commute.duration, min(first.end - MIN_LEN, t))
        dur = commute.duration
        first.start = t
        commute.end = t
        commute.start = t - dur

    def set_work_end(self, t: int) -> None:
        k = self.work_end_node()
        last = self.sections[k - 1]
        if self._has_evening_commute():
            commute = self.sections[-1]
            dur = commute.duration
            t = max(last.start + MIN_LEN, min(DAY_MAX - dur, t))
            last.end = t
            commute.start = t
            commute.end = t + dur
        else:
            last.end = max(last.start + MIN_LEN, min(DAY_MAX, t))

    def move_section(self, i: int, new_start: int) -> None:
        """Slide a section, keeping its length; neighbours stretch or shrink."""
        n = len(self.sections)
        s = self.sections[i]
        dur = s.duration
        lo = self.sections[i - 1].start + MIN_LEN if i > 0 else 0
        hi = (self.sections[i + 1].end - MIN_LEN if i < n - 1 else DAY_MAX) - dur
        if hi < lo:
            return
        new_start = max(lo, min(hi, new_start))
        s.start, s.end = new_start, new_start + dur
        if i > 0:
            self.sections[i - 1].end = s.start
        if i < n - 1:
            self.sections[i + 1].start = s.end

    def apply_computed_end(self, target_mins: int) -> None:
        """End of work = start + target + lunch, for days with no real end time yet."""
        if self.sections[self.work_end_node() - 1].kind != WORK:
            return
        self.set_work_end(self.work_start + target_mins + self.lunch_minutes())

    # ------------------------------------------------------------------
    # Split and delete
    # ------------------------------------------------------------------
    def can_split(self, i: int, t: int) -> bool:
        s = self.sections[i]
        return s.kind == WORK and s.start + MIN_LEN <= t <= s.end - MIN_LEN

    def split(self, i: int, t: int) -> bool:
        """Cut a section in two at t. The top half keeps the project."""
        if not self.can_split(i, t):
            return False
        s = self.sections[i]
        self.sections.insert(i + 1, Section(WORK, t, s.end))
        s.end = t
        return True

    def can_delete(self, i: int) -> bool:
        if self.sections[i].kind != WORK:
            return False
        return sum(1 for s in self.sections if s.kind == WORK) > 1

    def delete(self, i: int) -> bool:
        """Remove a section; the one above grows into the space."""
        if not self.can_delete(i):
            return False
        s = self.sections.pop(i)
        if i > 0 and self.sections[i - 1].kind != COMMUTE:
            self.sections[i - 1].end = s.end
        else:
            self.sections[i].start = s.start
        return True

    # ------------------------------------------------------------------
    # Commute
    # ------------------------------------------------------------------
    def set_wfh(self, wfh: bool, commute_mins: int = 60) -> None:
        self.sections = [s for s in self.sections if s.kind != COMMUTE]
        if wfh or not self.sections:
            return
        start, end = self.sections[0].start, self.sections[-1].end
        self.sections.insert(0, Section(COMMUTE, max(0, start - commute_mins), start))
        self.sections.append(Section(COMMUTE, end, min(1439, end + commute_mins)))


# ---------------------------------------------------------------------------
# Titles and smart project defaults
# ---------------------------------------------------------------------------

def derive_title(section: Section, meetings: list[tuple[int, int, str]]) -> Optional[str]:
    """Title of the meeting a section lines up with: same times, or covering most of it."""
    best_title, best_overlap = None, 0
    for m_start, m_end, title in meetings:
        if m_start == section.start and m_end == section.end:
            return title
        overlap = min(section.end, m_end) - max(section.start, m_start)
        if overlap * 2 > section.duration and overlap > best_overlap:
            best_title, best_overlap = title, overlap
    return best_title


def refresh_titles(model: DayModel, meetings: list[tuple[int, int, str]]) -> None:
    for s in model.sections:
        if s.kind != WORK or s.title_manual:
            continue
        s.title = derive_title(s, meetings)


def match_rule(title: str, rules: list[tuple[str, int, str]]) -> Optional[tuple[int, str]]:
    """rules are (pattern, project_id, category). Longest matching pattern wins."""
    lowered = title.lower()
    hits = [r for r in rules if r[0] and r[0] in lowered]
    if not hits:
        return None
    best = max(hits, key=lambda r: len(r[0]))
    return best[1], best[2]


def apply_rules(model: DayModel, rules: list[tuple[str, int, str]]) -> None:
    """Give titled, unassigned sections the project their title is known by."""
    for s in model.sections:
        if s.kind == WORK and s.project_id is None and s.title:
            hit = match_rule(s.title, rules)
            if hit:
                s.project_id, s.category = hit

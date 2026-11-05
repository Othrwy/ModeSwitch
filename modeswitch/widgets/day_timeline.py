"""
DayTimeline — one day drawn as a vertical slider, top (start) to bottom (end).

Two layers:
  • background — calendar meetings, read-only, drawn muted. Overlapping meetings
                 stack their transparency, so a double-booked spell reads deeper; a
                 hairline marks each one's start and end inside the overlap, and their
                 edge strips sit side by side. Hovering lists every meeting under the
                 mouse with its times and outlines each one, so none hides another.
  • foreground — the sections of the day, with a node at each boundary

Interactions:
  • drag a node            → resize; snaps to 5 min and to nearby meeting edges
                             (hold Alt to snap only to meeting starts and ends)
  • drag a section         → slide it, length fixed; snaps to 15 min
  • click a node           → type its time
  • double-click a section → split it there
  • right-click a section  → assign subtask / split / delete
  • click the code box     → pick a project from a dropdown

The end of the day is locked to the target mark (8h of work after the start, plus
lunch and breaks) until unlocked from the right-click menu. When the end is anywhere
else, a hollow node marks where the target falls; dropping the end on it locks it again.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt, QRect, QRectF, QPoint, QPointF, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QFont, QFontMetrics, QPen
from PyQt6.QtWidgets import QWidget, QMenu, QLineEdit, QToolTip, QInputDialog

from modeswitch import days, theme as theme_mod
from modeswitch.theme import current as theme
from modeswitch.db import models
from modeswitch.db.models import Day, Project, Subtask
from modeswitch.day_model import DayModel, WORK, LUNCH, COMMUTE, refresh_titles
from modeswitch.timeutil import (
    to_hhmm, snap, fmt_duration, now_min, contrasting_text,
)
from modeswitch.widgets.time_input import parse_time_input

RIBBON_WIDTH = 160
NARROW_WIDTH = 100  # times and code boxes only (older weeks in the review panel)
COMPACT_WIDTH = 24  # just the slider: the collapsed ribbon, and the oldest review weeks
NARROW_TRACK_X = 44

PAD = 14            # space above the first node and below the last
TRACK_X = 104       # centre of the slider line
TRACK_W = 6
TEXT_X = 4
TEXT_W = TRACK_X - 10 - TEXT_X
BOX_X = TRACK_X + 10
CODE_W, BOX_H = 42, 15
NODE_R = 4
NODE_HIT = 5        # px above or below a node that still grabs it
DRAG_THRESHOLD = 3

SECTION_SNAP = 15
END_BUFFER = 30     # room below the end of today (or the current time, if later)
ALERT_MINS = 30     # meetings starting this soon pulse
# Node snapping is set in Settings: the grid step ("node_snap") and how close a dragged
# node must come to a meeting edge to jump to it ("meeting_snap"). Both default to 5 min.

LUNCH_DEFAULT_START = 12 * 60   # where lunch goes when it is put back on a day

KIND_LABEL = {LUNCH: "Lunch", COMMUTE: "Commute"}
LANE_STEP = 4       # edge strips of overlapping meetings sit this far apart


def meeting_lanes(meetings: list[tuple[int, int, str]]) -> tuple[list[int], list[bool]]:
    """For each meeting, its lane (the first free one, like a calendar's columns when
    meetings clash) and whether it overlaps any other meeting."""
    lanes = [0] * len(meetings)
    lane_ends: list[int] = []
    for i in sorted(range(len(meetings)), key=lambda i: (meetings[i][0], -meetings[i][1])):
        start, end, _ = meetings[i]
        free = next((k for k, e in enumerate(lane_ends) if e <= start), len(lane_ends))
        if free == len(lane_ends):
            lane_ends.append(end)
        lane_ends[free] = end
        lanes[i] = free
    overlaps = [any(j != i and s2 < e1 and e2 > s1 for j, (s2, e2, _) in enumerate(meetings))
                for i, (s1, e1, _) in enumerate(meetings)]
    return lanes, overlaps


class DayTimeline(QWidget):
    changed = pyqtSignal()   # the day was edited and saved
    clicked_compact = pyqtSignal()   # clicked while collapsed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.day: Optional[Day] = None
        self.model: Optional[DayModel] = None
        self.meetings: list[tuple[int, int, str]] = []
        self.projects: dict[int, Project] = {}
        self.subtasks: dict[int, Subtask] = {}
        self.kind_colors: dict[str, str] = days.DEFAULT_KIND_COLORS
        self.meeting_edges = True      # the coloured strip down a meeting's left side
        self.node_snap = 5             # grid step for nodes, minutes
        self.meeting_snap = 5          # a dragged node jumps to a meeting edge this close

        self._fixed_range: Optional[tuple[int, int]] = None
        self._frozen_range: Optional[tuple[int, int]] = None
        self._drag: Optional[dict] = None
        self._editor: Optional[QLineEdit] = None
        self._editor_node: Optional[int] = None
        self._pulse_phase = 0.0
        self._compact = False
        self._narrow = False
        self._edge = "right"           # the screen edge this timeline sits against
        self._hover: Optional[QPoint] = None
        self._track_x = TRACK_X
        self._text_w = TEXT_W
        self._box_x = BOX_X

        self._font = QFont("Segoe UI", 8)
        self._bold = QFont("Segoe UI", 8, QFont.Weight.DemiBold)

        self.setFixedWidth(RIBBON_WIDTH)
        self.setMinimumHeight(200)
        self.setMouseTracking(True)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(60)
        self._pulse_timer.timeout.connect(self._on_pulse)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._on_clock)
        self._clock_timer.start(20_000)

    # ------------------------------------------------------------------
    # Loading and saving
    # ------------------------------------------------------------------
    def load(self, day: Day) -> None:
        self._close_editor(commit=False)
        self._drag = None
        self._frozen_range = None
        self.day = day
        self.model = days.load_model(day)
        self.meetings = days.load_meetings(day.date)
        self._load_projects()
        self.kind_colors = days.kind_colors()
        self.node_snap = max(1, models.get_int_setting("node_snap", 5))
        self.meeting_snap = max(0, models.get_int_setting("meeting_snap", 5))
        if self._is_today():
            end = self.model.work_end
            self._apply_lock()   # breaks or the day's length may have changed
            if self.model.work_end != end:
                days.save_model(self.day, self.model)
        self._on_clock()
        self.update()

    def _load_projects(self) -> None:
        self.projects = {p.id: p for p in models.get_all_projects()}
        self.subtasks = {s.id: s for s in models.get_subtasks()}

    def target(self) -> int:
        """This day's nominal working minutes."""
        return days.target_minutes(date.fromisoformat(self.day.date))

    def reload(self) -> None:
        if self.day:
            fresh = models.get_day(self.day.date)
            if fresh:
                self.load(fresh)

    def refresh_meetings(self) -> None:
        """Pick up meetings a calendar sync stored, and the titles they give sections."""
        if not self.day or self._drag or self._editor:
            return
        fresh = days.load_meetings(self.day.date)
        if fresh == self.meetings:
            return
        self.meetings = fresh
        refresh_titles(self.model, self.meetings)
        self._on_clock()
        self._commit()

    def set_range(self, start: Optional[int], end: Optional[int]) -> None:
        """Fix the time span shown, so several days can share one scale."""
        self._fixed_range = (start, end) if start is not None else None
        self.update()

    def set_edge(self, edge: str) -> None:
        """Hover titles only show on the half away from the screen edge."""
        self._edge = edge
        self.update()

    def _inner_side(self, x: float) -> bool:
        half = self.width() / 2
        return x < half if self._edge == "right" else x >= half

    def set_compact(self, compact: bool) -> None:
        """Collapsed: just the slider, no text or boxes, and a click asks to expand."""
        self.set_density("compact" if compact else "full")

    def set_density(self, density: str) -> None:
        """"full": everything. "narrow": node times and code boxes, no durations; titles
        go in the tooltip. "compact": just the slider, read-only, tooltips only."""
        self._close_editor(commit=False)
        self._drag = None
        self._compact = density == "compact"
        self._narrow = density == "narrow"
        self._track_x = {"compact": COMPACT_WIDTH // 2, "narrow": NARROW_TRACK_X}.get(density, TRACK_X)
        self._text_w = self._track_x - 10 - TEXT_X
        self._box_x = self._track_x + 10
        self.setFixedWidth({"compact": COMPACT_WIDTH, "narrow": NARROW_WIDTH}.get(density, RIBBON_WIDTH))
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._compact
                       else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_lunch(self, on: bool) -> None:
        """Take lunch off the day, or put it back at the usual time."""
        if not self.model or self.model.has_lunch() == on:
            return
        if on:
            length = models.get_int_setting("lunch_minutes", 60)
            self._user_edit(lambda: self.model.add_lunch(LUNCH_DEFAULT_START, length))
        else:
            self._user_edit(self.model.remove_lunch)
        self._commit()

    def set_wfh(self, wfh: bool) -> None:
        if not self.model or self.day.wfh == wfh:
            return
        self.day.wfh = wfh
        self.model.set_wfh(wfh, models.get_int_setting("commute_minutes", 60))
        self._commit()

    def set_end_now(self) -> None:
        """Record leaving now as the end of the day."""
        if not self.model:
            return
        self.model.set_work_end(now_min())
        self.day.out_source = "held"
        self._commit()

    def end_locked(self) -> bool:
        """The end sits on the target mark, or on the clock once that has passed."""
        return bool(self.day) and self.day.out_source == "computed"

    def can_lock_end(self) -> bool:
        return (self._is_today() and bool(self.model and self.model.sections)
                and self.model.sections[self.model.work_end_node() - 1].kind == WORK)

    def set_end_locked(self, locked: bool) -> None:
        """Lock the end to the target mark, or free it to be dragged."""
        if locked:
            self.day.out_source = "computed"
        else:
            held = self._is_today() and self.model.work_end < now_min()
            self.day.out_source = "held" if held else "manual"
        self._commit()

    def target_mark(self) -> Optional[int]:
        """Where the target is reached, when the end is somewhere else; otherwise None."""
        if not self.model or not self.model.sections:
            return None
        if self.model.sections[self.model.work_end_node() - 1].kind != WORK:
            return None
        mark = self.model.target_end(self.target())
        return None if mark == self.model.work_end else mark

    def _relock_if_on_mark(self, k: int) -> None:
        """An end dropped back on the target mark locks to it again, unless the mark
        has already passed (then it records stopping work at the mark)."""
        if (k == self.model.work_end_node() and self.can_lock_end()
                and self.model.work_end == self.model.target_end(self.target())
                and self.model.work_end >= now_min()):
            self.day.out_source = "computed"

    def _commit(self) -> None:
        if self.end_locked():
            self._apply_lock()   # e.g. a section was just given the Break project
        days.save_model(self.day, self.model)
        self.update()
        self.changed.emit()

    def _user_edit(self, edit) -> None:
        """Run an edit, then note whether it moved the start or end of the day."""
        start, end = self.model.work_start, self.model.work_end
        edit()
        if self.model.work_start != start:
            self.day.in_source = "manual"
        if self.end_locked():
            self._apply_lock()   # nothing moves a locked end
        elif self.model.work_end != end:
            # Set earlier than now: that is when work stopped, so it stays put.
            # Set now or later: still working, so it follows the clock once passed.
            held = self._is_today() and self.model.work_end < now_min()
            self.day.out_source = "held" if held else "manual"
        refresh_titles(self.model, self.meetings)

    def _apply_lock(self) -> None:
        if self.end_locked():
            self.model.apply_computed_end(self.target())
        self._follow_clock()

    def _follow_clock(self) -> bool:
        """On today, once the clock passes the end node, the end follows the current
        time: still at the computer means still working. Not when the end was set by
        hand to a time already past ("held"). Returns True if the end moved."""
        if (not self._is_today() or self.day.out_source not in ("computed", "manual")
                or self.model.sections[self.model.work_end_node() - 1].kind != WORK):
            return False
        now = now_min()
        if now <= self.model.work_end:
            return False
        self.model.set_work_end(now)
        return True

    # ------------------------------------------------------------------
    # Coordinates
    # ------------------------------------------------------------------
    def _range(self) -> tuple[int, int]:
        if self._frozen_range:
            return self._frozen_range
        if self._fixed_range:
            return self._fixed_range
        s = self.model.sections
        end = s[-1].end
        if self._is_today():
            end = max(end, now_min(), self.target_mark() or 0)
        return s[0].start, min(24 * 60, end + END_BUFFER)

    def _ppm(self) -> float:
        r0, r1 = self._range()
        return (self.height() - 2 * PAD) / max(1, r1 - r0)

    def _y(self, t: int) -> int:
        return int(round(PAD + (t - self._range()[0]) * self._ppm()))

    def _t(self, y: float) -> float:
        return self._range()[0] + (y - PAD) / self._ppm()

    def _is_today(self) -> bool:
        return bool(self.day) and self.day.date == date.today().isoformat()

    # ------------------------------------------------------------------
    # Layout of the code box, and the subtask name under it, right of a section
    # ------------------------------------------------------------------
    def _code_rect(self, i: int) -> Optional[QRect]:
        s = self.model.sections[i]
        if s.kind != WORK:
            return None
        y1, y2 = self._y(s.start), self._y(s.end)
        if y2 - y1 < 12:
            return None
        h = min(BOX_H, y2 - y1 - 4)
        return QRect(self._box_x, y1 + 2, CODE_W, h)

    def _subtask_rect(self, i: int) -> Optional[QRect]:
        code = self._code_rect(i)
        if code is None:
            return None
        top = code.bottom() + 2
        if top + 12 > self._y(self.model.sections[i].end):
            return None
        return QRect(self._box_x, top, self.width() - self._box_x - 2, 12)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        # No background fill: whatever is behind shows through (week shading in review)
        p = QPainter(self)
        if not self.model or not self.model.sections:
            p.end()
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        self._paint_meetings(p)
        self._paint_sections(p)
        self._paint_now_line(p)
        self._paint_target_mark(p)
        self._paint_nodes(p)
        self._paint_hover_title(p)
        p.end()

    def _meeting_colors(self, start: int, end: int) -> tuple[QColor, QColor]:
        """(fill, edge) for a meeting: grey once over, red later, pulsing when soon."""
        now = now_min()
        today = date.today().isoformat()
        if self.day.date < today or (self.day.date == today and end <= now):
            return theme.q("meeting_past", 45), theme.q("meeting_past", 130)
        if self.day.date == today and 0 < start - now <= ALERT_MINS:
            glow = 0.5 + 0.5 * math.sin(self._pulse_phase)
            return (theme.q("meeting_soon", int(50 + 70 * glow)),
                    theme.q("meeting_soon", int(160 + 95 * glow)))
        if self.day.date == today and start <= now:
            return theme.q("meeting_now", 80), theme.q("meeting_now", 220)
        return theme.q("meeting_later", 65), theme.q("meeting_later", 190)

    def _paint_meetings(self, p: QPainter) -> None:
        r0, r1 = self._range()
        lanes, overlaps = meeting_lanes(self.meetings)
        for (start, end, _title), lane, overlapping in zip(self.meetings, lanes, overlaps):
            if end <= r0 or start >= r1:
                continue
            y1, y2 = self._y(max(start, r0)), self._y(min(end, r1))
            fill, edge = self._meeting_colors(start, end)
            # Overlaps stack their transparency, so a double-booked spell reads deeper
            p.fillRect(QRect(0, y1, self.width(), max(2, y2 - y1)), fill)
            strip_x = lane * LANE_STEP if self.meeting_edges and not self._compact else 0
            if self.meeting_edges:
                p.fillRect(QRect(strip_x, y1, 2, max(2, y2 - y1)), edge)
            if overlapping and not self._compact:
                # Hairlines where it starts and ends, which would otherwise be lost
                # inside the deeper band of the meeting it overlaps
                line = QColor(edge)
                line.setAlpha(edge.alpha() // 2)
                for y in (y1, y2 - 1):
                    p.fillRect(QRect(strip_x + 2, y, self.width() - strip_x - 2, 1), line)

    def _paint_sections(self, p: QPainter) -> None:
        fm = QFontMetrics(self._font)
        line_h = fm.lineSpacing()
        for i, s in enumerate(self.model.sections):
            y1, y2 = self._y(s.start), self._y(s.end)
            proj = self.projects.get(s.project_id) if s.project_id else None
            if s.kind in self.kind_colors:
                color = QColor(self.kind_colors[s.kind])
            else:
                color = QColor(proj.color) if proj else theme.q("track")

            p.fillRect(QRect(self._track_x - TRACK_W // 2, y1, TRACK_W, y2 - y1), color)
            if self._compact:
                continue

            # Duration (and Lunch / Commute), wrapped, cropped to whole lines.
            # Titles only appear on hover, see _paint_hover_title.
            lines = (y2 - y1 - 14) // line_h
            if lines >= 1 and not self._narrow:
                label = KIND_LABEL.get(s.kind)
                text = fmt_duration(s.duration) + (f" {label}" if label else "")
                rect = QRect(TEXT_X, y1 + 8, TEXT_W, lines * line_h)
                p.save()
                p.setClipRect(rect)
                p.setFont(self._font)
                p.setPen(theme.q("muted"))
                p.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
                                     | Qt.TextFlag.TextWordWrap), text)
                p.restore()

            code_rect = self._code_rect(i)
            if code_rect:
                bg = QColor(proj.color) if proj else theme.q("surface")
                fg = QColor(contrasting_text(proj.color)) if proj else theme.q("faint")
                p.setPen(QPen(theme.q("border"), 1))
                p.setBrush(bg)
                p.drawRoundedRect(QRectF(code_rect), 2, 2)
                p.setFont(self._bold)
                p.setPen(fg)
                p.drawText(code_rect, int(Qt.AlignmentFlag.AlignCenter),
                           proj.code if proj else "----")
            sub = self.subtasks.get(s.subtask_id) if s.subtask_id else None
            sub_rect = self._subtask_rect(i) if sub else None
            if sub_rect:
                p.setFont(self._font)
                p.setPen(theme.q("muted"))
                p.drawText(sub_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                           QFontMetrics(self._font).elidedText(
                               sub.name, Qt.TextElideMode.ElideRight, sub_rect.width()))

    def _paint_now_line(self, p: QPainter) -> None:
        if not self._is_today():
            return
        r0, r1 = self._range()
        now = now_min()
        if r0 <= now <= r1:
            y = self._y(now)
            p.setPen(QPen(theme.q("now_line"), 1))
            p.drawLine(self._track_x - 12, y, self._track_x + 12, y)

    def _hover_meetings(self) -> list[int]:
        """Every meeting under the mouse, earliest first. Picked by time, not by which
        is drawn on top, so an overlapped meeting is never hidden. Inner half only."""
        if (self._hover is None or not self.model or self._drag or self._compact or self._narrow
                or not self._inner_side(self._hover.x())):
            return []
        t = self._t(self._hover.y())
        hits = [i for i, (start, end, _) in enumerate(self.meetings) if start <= t < end]
        return sorted(hits, key=lambda i: self.meetings[i][:2])

    def _hover_titles(self) -> tuple[list[tuple[str, str]], int]:
        """(times, title) under the mouse, and the y to draw them from. Only on the
        inner half. Times are only given where meetings overlap, to tell them apart."""
        hits = self._hover_meetings()
        if hits:
            _, overlaps = meeting_lanes(self.meetings)
            timed = any(overlaps[i] for i in hits)
            titles = [(f"{to_hhmm(start)}–{to_hhmm(end)}" if timed else "", title)
                      for start, end, title in (self.meetings[i] for i in hits)]
            return titles, self._y(self.meetings[hits[0]][0])
        if (self._hover is None or not self.model or self._drag or self._compact or self._narrow
                or not self._inner_side(self._hover.x())):
            return [], 0
        y = self._hover.y()
        i = self._section_at(y)
        if i is not None and self.model.sections[i].title:
            s = self.model.sections[i]
            return [("", s.title)], self._y(s.start)
        return [], 0

    def _paint_hover_outlines(self, p: QPainter) -> None:
        """Outline each hovered meeting that overlaps another, so its full extent shows
        through the stack. Nested a step in per lane so the outlines do not coincide."""
        hits = self._hover_meetings()
        lanes, overlaps = meeting_lanes(self.meetings)
        if not any(overlaps[i] for i in hits):
            return
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in hits:
            start, end, _ = self.meetings[i]
            _, edge = self._meeting_colors(start, end)
            edge.setAlpha(255)
            inset = 1 + 2 * lanes[i]
            p.setPen(QPen(edge, 1))
            p.drawRect(QRectF(inset + 0.5, self._y(start) + 0.5,
                              self.width() - 2 * inset - 1, self._y(end) - self._y(start) - 1))

    def _paint_hover_title(self, p: QPainter) -> None:
        self._paint_hover_outlines(p)
        titles, top = self._hover_titles()
        if not titles:
            return
        rect = QRect(TEXT_X, 0, self._track_x - 8 - TEXT_X, 0)
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap)
        fm = QFontMetrics(self._font)
        # Each entry: its times on a muted line of their own (where meetings overlap),
        # then the title, wrapped. A small gap between entries.
        entries = []
        for times, title in titles:
            height = fm.boundingRect(QRect(0, 0, rect.width() - 6, 1000), flags, title).height()
            entries.append((times, title, height + (fm.lineSpacing() if times else 0)))
        rect.setHeight(sum(h for *_, h in entries) + 3 * (len(entries) - 1) + 6)
        rect.moveTop(max(0, min(self.height() - rect.height(), top + 1)))
        p.setPen(QPen(theme.q("border"), 1))
        p.setBrush(theme.q("surface", 240))
        p.drawRoundedRect(QRectF(rect), 3, 3)
        p.setFont(self._font)
        y = rect.top() + 3
        for times, title, height in entries:
            line = QRect(rect.left() + 3, y, rect.width() - 6, height)
            if times:
                p.setPen(theme.q("muted"))
                p.drawText(line, flags, times)
                line.setTop(line.top() + fm.lineSpacing())
            p.setPen(theme.q("text"))
            p.drawText(line, flags, title)
            y += height + 3

    def _paint_target_mark(self, p: QPainter) -> None:
        """A hollow node where the target is reached, when the end is elsewhere."""
        mark = self.target_mark()
        r0, r1 = self._range()
        if mark is None or not r0 <= mark <= r1:
            return
        y = self._y(mark)
        if not self._compact and all(abs(y - self._y(self.model.node_time(k))) >= 11
                                     for k in range(self.model.node_count())):
            p.setFont(self._font)
            p.setPen(theme.q("faint"))
            p.drawText(QRect(TEXT_X, y - 7, self._text_w, 14),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                       to_hhmm(mark))
        p.setPen(QPen(theme.q("node"), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(self._track_x, y), NODE_R, NODE_R)

    def _paint_lock(self, p: QPainter, y: int) -> None:
        """A small padlock beside the end node while it is locked."""
        x = self._track_x + 14   # clear of the now-line
        p.setPen(QPen(theme.q("muted"), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(x + 1.5, y - 5, 4, 6), 0, 180 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.q("muted"))
        p.drawRect(QRectF(x, y - 2, 7, 5))

    def _paint_nodes(self, p: QPainter) -> None:
        dragged = self._drag["k"] if self._drag and self._drag["what"] == "node" else None
        last_label_y = -100
        p.setFont(self._font)
        for k in range(self.model.node_count()):
            t = self.model.node_time(k)
            y = self._y(t)
            # Skip a time label that would sit on top of the one above
            if not self._compact and (k == dragged or y - last_label_y >= 11):
                p.setPen(theme.q("text"))
                p.drawText(QRect(TEXT_X, y - 7, self._text_w, 14),
                           int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                           to_hhmm(t))
                last_label_y = y
            p.setPen(QPen(theme.q("bg"), 1))
            p.setBrush(theme.q("node"))
            r = NODE_R + 1 if k == dragged else NODE_R
            p.drawEllipse(QPointF(self._track_x, y), r, r)
        if self.end_locked() and self.can_lock_end() and not self._compact:
            self._paint_lock(p, self._y(self.model.work_end))

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------
    def _hit(self, x: float, y: float) -> Optional[tuple[str, int]]:
        if not self.model or not self.model.sections:
            return None
        for i in range(len(self.model.sections)):
            rect = self._code_rect(i)
            if rect and rect.adjusted(-1, -1, 1, 1).contains(int(x), int(y)):
                return "code", i
        if x < self._box_x:
            best, best_d = None, NODE_HIT + 1
            for k in range(self.model.node_count()):
                d = abs(y - self._y(self.model.node_time(k)))
                if d < best_d:
                    best, best_d = k, d
            if best is not None:
                return "node", best
        i = self._section_at(y)
        return ("section", i) if i is not None else None

    def _section_at(self, y: float) -> Optional[int]:
        for i, s in enumerate(self.model.sections):
            if self._y(s.start) <= y <= self._y(s.end):
                return i
        return None

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if self._compact:
            self.clicked_compact.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._close_editor(commit=True)
        hit = self._hit(event.position().x(), event.position().y())
        if not hit:
            return
        what, idx = hit
        if what == "code":
            self._open_code_menu(idx)
        elif what == "node":
            if self._is_locked_end(idx):
                QToolTip.showText(event.globalPosition().toPoint(), self._lock_tip(), self)
                return
            self._drag = {"what": "node", "k": idx, "y0": event.position().y(), "moved": False}
        else:
            self._drag = {"what": "section", "i": idx, "y0": event.position().y(),
                          "start0": self.model.sections[idx].start, "moved": False}

    def mouseMoveEvent(self, event):
        if self._compact:
            return
        y = event.position().y()
        if not self._drag:
            self._update_cursor(event.position().x(), y)
            self._set_hover(event.position().toPoint())
            return
        d = self._drag
        if not d["moved"]:
            if abs(y - d["y0"]) < DRAG_THRESHOLD:
                return
            d["moved"] = True
            self._frozen_range = self._range()   # keep the scale still while dragging

        if d["what"] == "node":
            meetings_only = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            t = self._snap_node_time(self._t(y), meetings_only, d["k"])
            self._user_edit(lambda: self.model.move_node(d["k"], t))
        else:
            delta = (y - d["y0"]) / self._ppm()
            t = snap(d["start0"] + delta, SECTION_SNAP)
            self._user_edit(lambda: self.model.move_section(d["i"], t))
        self.update()

    def mouseReleaseEvent(self, event):
        d, self._drag = self._drag, None
        self._frozen_range = None
        if not d:
            return
        if d["moved"]:
            if d["what"] == "node":
                self._relock_if_on_mark(d["k"])
            self._commit()
        elif d["what"] == "node":
            self._open_editor(d["k"])

    def mouseDoubleClickEvent(self, event):
        if self._compact:
            return
        if event.button() != Qt.MouseButton.LeftButton or not self.model:
            return
        hit = self._hit(event.position().x(), event.position().y())
        if hit and hit[0] == "section":
            self._split(hit[1], event.position().y())

    def contextMenuEvent(self, event):
        if self._compact or not self.model:
            return
        hit = self._hit(event.pos().x(), event.pos().y())
        i = hit[1] if hit and hit[0] in ("section", "code") else self._section_at(event.pos().y())
        if i is None and not self.can_lock_end():
            return
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        subtask_actions, split, delete, lock = {}, None, None, None
        if i is not None:
            s = self.model.sections[i]
            t = snap(self._t(event.pos().y()), self.node_snap)
            subtask_actions = self._add_subtask_menu(menu, s)
            menu.addSeparator()
            split = menu.addAction("Split here")
            split.setEnabled(self.model.can_split(i, t))
            menu.addSeparator()
            delete = menu.addAction("Delete")
            delete.setEnabled(self.model.can_delete(i))
        if self.can_lock_end():
            menu.addSeparator()
            lock = menu.addAction(f"Lock end of day to {fmt_duration(self.target())} mark")
            lock.setCheckable(True)
            lock.setChecked(self.end_locked())
            lock.setToolTip("Locked, the end of day stays on the target mark and moves with "
                            "lunch and breaks. Untick to drag it, e.g. to leave early.")
        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen == lock:
            self.set_end_locked(lock.isChecked())
        elif chosen in subtask_actions:
            self._assign_subtask(s, subtask_actions[chosen])
        elif chosen == split:
            self._split(i, event.pos().y())
        elif chosen == delete:
            self._user_edit(lambda: self.model.delete(i))
            self._commit()

    def _update_cursor(self, x: float, y: float) -> None:
        hit = self._hit(x, y)
        if not hit:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif hit[0] == "code":
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif hit[0] == "node":
            self.setCursor(Qt.CursorShape.ArrowCursor if self._is_locked_end(hit[1])
                           else Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _is_locked_end(self, k: int) -> bool:
        return self.end_locked() and self.can_lock_end() and k == self.model.work_end_node()

    def _lock_tip(self) -> str:
        return (f"End of day is locked to the {fmt_duration(self.target())} mark. "
                "Once that has passed it follows the clock.\n"
                "Right-click and untick the lock to move it.")

    def _snap_node_time(self, raw: float, meetings_only: bool = False,
                        k: Optional[int] = None) -> int:
        """Where a dragged node lands. The end of day jumps to the target mark when
        it comes within a snap step of it. Otherwise a meeting edge within
        `meeting_snap` wins, then the nearer of the grid mark and, on today, the
        current time. Holding Alt (meetings_only) jumps to the nearest meeting start
        or end however far away, or the grid if the day has no meetings."""
        if k is not None and k == self.model.work_end_node() and not meetings_only:
            mark = self.model.target_end(self.target())
            if abs(mark - raw) <= max(self.meeting_snap, self.node_snap):
                return mark
        edges = [e for start, end, _ in self.meetings for e in (start, end)]
        if meetings_only and edges:
            return min(edges, key=lambda e: abs(e - raw))
        near = [e for e in edges if abs(e - raw) <= self.meeting_snap]
        if near:
            return min(near, key=lambda e: abs(e - raw))
        grid = snap(raw, self.node_snap)
        if self._is_today():
            now = now_min()
            if abs(now - raw) < abs(grid - raw):
                return now
        return grid

    # ------------------------------------------------------------------
    # Section actions
    # ------------------------------------------------------------------
    def _split(self, i: int, y: float) -> None:
        t = snap(self._t(y), self.node_snap)
        if self.model.can_split(i, t):
            self._user_edit(lambda: self.model.split(i, t))
            self._commit()

    def _open_code_menu(self, i: int) -> None:
        s = self.model.sections[i]
        menu = QMenu(self)
        for proj in models.get_recent_projects():
            action = menu.addAction(f"{proj.code}  {proj.name}")
            action.setData(proj.id)
            action.setCheckable(True)
            action.setChecked(proj.id == s.project_id)
        menu.addSeparator()
        clear = menu.addAction("Unassigned")
        new = menu.addAction("New project…")
        rect = self._code_rect(i)
        chosen = menu.exec(self.mapToGlobal(rect.bottomLeft()))
        if chosen is None:
            return
        if chosen == new:
            from modeswitch.dialogs.add_project import AddProjectDialog
            dlg = AddProjectDialog(self)
            if not dlg.exec():
                return
            s.project_id = dlg.created_project.id
        elif chosen == clear:
            s.project_id = None
        else:
            s.project_id = chosen.data()
        if s.project_id:
            models.touch_project(s.project_id)
        sub = self.subtasks.get(s.subtask_id) if s.subtask_id else None
        if sub is None or sub.project_id != s.project_id:
            s.subtask_id = None   # a subtask belongs to one project
        self._load_projects()
        if chosen == new:
            theme_mod.hub().projects_changed.emit()
        self._remember_title(s)
        self._commit()

    def _add_subtask_menu(self, menu: QMenu, s) -> dict:
        """'Assign subtask' submenu: None, the project's subtasks, New subtask….
        Returns {action: subtask id, None for none, or "new"}."""
        sub_menu = menu.addMenu("Assign subtask")
        if s.kind != WORK or not s.project_id:
            sub_menu.setEnabled(False)
            return {}
        actions = {}
        none = sub_menu.addAction("None")
        none.setCheckable(True)
        none.setChecked(s.subtask_id is None)
        actions[none] = None
        subs = models.get_subtasks(s.project_id)
        if subs:
            sub_menu.addSeparator()
        for sub in subs:
            action = sub_menu.addAction(sub.name)
            action.setCheckable(True)
            action.setChecked(sub.id == s.subtask_id)
            actions[action] = sub.id
        sub_menu.addSeparator()
        actions[sub_menu.addAction("New subtask…")] = "new"
        return actions

    def _assign_subtask(self, s, choice) -> None:
        if choice == "new":
            proj = self.projects.get(s.project_id)
            name, ok = QInputDialog.getText(self, "New subtask",
                                            f"Subtask of {proj.code} {proj.name}:")
            name = name.strip()
            if not ok or not name:
                return
            choice = models.get_or_create_subtask(s.project_id, name).id
            self._load_projects()
            theme_mod.hub().projects_changed.emit()
        s.subtask_id = choice
        self._remember_title(s)
        self._commit()

    @staticmethod
    def _remember_title(s) -> None:
        """Learn that sections with this title belong to this project and subtask."""
        if s.title and s.project_id:
            models.upsert_rule(s.title, s.project_id, s.subtask_id)

    # ------------------------------------------------------------------
    # Typing a node's time
    # ------------------------------------------------------------------
    def _open_editor(self, k: int) -> None:
        y = self._y(self.model.node_time(k))
        ed = QLineEdit(self)
        ed.setText(to_hhmm(self.model.node_time(k)))
        ed.setMaxLength(5)
        ed.setAlignment(Qt.AlignmentFlag.AlignRight)
        ed.setGeometry(max(0, TEXT_X + self._text_w - 46), max(0, min(self.height() - 18, y - 9)),
                       48, 18)
        ed.setStyleSheet("background: #fff; color: #000; border: none; padding: 0 2px;")
        ed.editingFinished.connect(lambda: self._close_editor(commit=True))
        self._editor, self._editor_node = ed, k
        ed.show()
        ed.setFocus()
        ed.selectAll()

    def _close_editor(self, commit: bool) -> None:
        if self._editor is None:
            return
        ed, k = self._editor, self._editor_node
        self._editor, self._editor_node = None, None
        parsed = parse_time_input(ed.text()) if commit else None
        ed.hide()
        ed.deleteLater()
        if parsed and k < self.model.node_count():
            h, m = map(int, parsed.split(":"))
            t = h * 60 + m
            if t != self.model.node_time(k):
                self._user_edit(lambda: self.model.move_node(k, t))
                self._relock_if_on_mark(k)
                self._commit()

    # ------------------------------------------------------------------
    # Hover text
    # ------------------------------------------------------------------
    def _set_hover(self, pos: Optional[QPoint]) -> None:
        before = self._hover_titles()
        self._hover = pos
        if self._hover_titles() != before:
            self.update()

    def leaveEvent(self, event):
        self._set_hover(None)
        super().leaveEvent(event)

    def event(self, e):
        if e.type() == QEvent.Type.ToolTip and self.model and self.model.sections:
            text = self._tooltip_at(e.pos().x(), e.pos().y())
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def _tooltip_at(self, x: int, y: int) -> str:
        """Times, project and subtask. Titles only on the inner half, and only when
        compact or narrow; at full width they are drawn in place by _paint_hover_title.
        Over the end node or the target mark, what they are."""
        if self._is_locked_end(self.model.work_end_node()) \
                and abs(y - self._y(self.model.work_end)) <= NODE_HIT:
            return self._lock_tip()
        mark = self.target_mark()
        if mark is not None and abs(y - self._y(mark)) <= NODE_HIT:
            return (f"{fmt_duration(self.target())} mark: {to_hhmm(mark)}\n"
                    "Drag the end of day here to lock it to the mark again")
        i = self._section_at(y)
        if i is None:
            return ""
        show_titles = (self._compact or self._narrow) and self._inner_side(x)
        s = self.model.sections[i]
        lines = [f"{to_hhmm(s.start)} – {to_hhmm(s.end)}  ({fmt_duration(s.duration)})"]
        title = KIND_LABEL.get(s.kind) or (s.title if show_titles else None)
        if title:
            lines.append(title)
        if s.kind == WORK:
            proj = self.projects.get(s.project_id) if s.project_id else None
            lines.append(f"{proj.code} {proj.name}" if proj else "Unassigned")
            sub = self.subtasks.get(s.subtask_id) if s.subtask_id else None
            if sub:
                lines.append(f"⤷ {sub.name}")
        if show_titles:
            t = self._t(y)
            for start, end, m_title in self.meetings:
                if start <= t <= end:
                    lines.append(f"Calendar: {m_title} ({to_hhmm(start)} – {to_hhmm(end)})")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Clock: the now-line and the upcoming-meeting pulse
    # ------------------------------------------------------------------
    def _on_clock(self) -> None:
        if self.model and self.model.sections and not self._drag and not self._editor                 and self._follow_clock():
            self._commit()
        now = now_min()
        soon = self._is_today() and any(0 < start - now <= ALERT_MINS
                                        for start, _, _ in self.meetings)
        if soon and not self._pulse_timer.isActive():
            self._pulse_timer.start()
        elif not soon and self._pulse_timer.isActive():
            self._pulse_timer.stop()
        self.update()

    def _on_pulse(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.2) % (2 * math.pi)
        self.update()

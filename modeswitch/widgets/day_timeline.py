"""
DayTimeline — one day drawn as a vertical slider, top (start) to bottom (end).

Two layers:
  • background — calendar meetings, read-only, drawn muted
  • foreground — the sections of the day, with a node at each boundary

Interactions:
  • drag a node            → resize; snaps to 5 min and to nearby meeting edges
                             (hold Alt to switch the meeting snap off)
  • drag a section         → slide it, length fixed; snaps to 15 min
  • click a node           → type its time
  • double-click a section → split it there
  • right-click a section  → split / set title / delete
  • click the code box or the letter box → pick from a dropdown
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt, QRect, QRectF, QPointF, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QFont, QFontMetrics, QPen
from PyQt6.QtWidgets import QWidget, QMenu, QLineEdit, QToolTip, QInputDialog

from modeswitch import days
from modeswitch.db import models
from modeswitch.db.models import Day, Project
from modeswitch.day_model import DayModel, WORK, LUNCH, COMMUTE, refresh_titles
from modeswitch.timeutil import (
    to_hhmm, snap, fmt_duration, now_min, contrasting_text,
)
from modeswitch.widgets.time_input import parse_time_input

RIBBON_WIDTH = 160
COMPACT_WIDTH = 24  # the collapsed ribbon: just the slider

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

NODE_SNAP = 5
SECTION_SNAP = 15
MEETING_SNAP = 15   # a dragged node jumps to a meeting edge within this many minutes
ALERT_MINS = 30     # meetings starting this soon pulse

LETTERS = ["A", "B", "C", "D"]

KIND_COLOR = {LUNCH: "#FFA500", COMMUTE: "#808080"}
KIND_LABEL = {LUNCH: "Lunch", COMMUTE: "Commute"}
UNASSIGNED_COLOR = "#4a4a4a"


class DayTimeline(QWidget):
    changed = pyqtSignal()   # the day was edited and saved
    clicked_compact = pyqtSignal()   # clicked while collapsed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.day: Optional[Day] = None
        self.model: Optional[DayModel] = None
        self.meetings: list[tuple[int, int, str]] = []
        self.projects: dict[int, Project] = {}

        self._fixed_range: Optional[tuple[int, int]] = None
        self._frozen_range: Optional[tuple[int, int]] = None
        self._drag: Optional[dict] = None
        self._editor: Optional[QLineEdit] = None
        self._editor_node: Optional[int] = None
        self._pulse_phase = 0.0
        self._compact = False
        self._track_x = TRACK_X

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
        self.projects = {p.id: p for p in models.get_all_projects()}
        self._on_clock()
        self.update()

    def reload(self) -> None:
        if self.day:
            fresh = models.get_day(self.day.date)
            if fresh:
                self.load(fresh)

    def set_range(self, start: Optional[int], end: Optional[int]) -> None:
        """Fix the time span shown, so several days can share one scale."""
        self._fixed_range = (start, end) if start is not None else None
        self.update()

    def set_compact(self, compact: bool) -> None:
        """Collapsed: just the slider, no text or boxes, and a click asks to expand."""
        self._close_editor(commit=False)
        self._drag = None
        self._compact = compact
        self._track_x = COMPACT_WIDTH // 2 if compact else TRACK_X
        self.setFixedWidth(COMPACT_WIDTH if compact else RIBBON_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor if compact
                       else Qt.CursorShape.ArrowCursor)
        self.update()

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
        self.day.out_source = "manual"
        self._commit()

    def _commit(self) -> None:
        days.save_model(self.day, self.model)
        self.update()
        self.changed.emit()

    def _user_edit(self, edit) -> None:
        """Run an edit, then note whether it moved the start or end of the day."""
        start, end = self.model.work_start, self.model.work_end
        edit()
        if self.model.work_start != start:
            self.day.in_source = "manual"
        if self.model.work_end != end:
            self.day.out_source = "manual"
        elif self.day.out_source == "computed":
            self.model.apply_computed_end(days.target_minutes())
        refresh_titles(self.model, self.meetings)

    # ------------------------------------------------------------------
    # Coordinates
    # ------------------------------------------------------------------
    def _range(self) -> tuple[int, int]:
        if self._frozen_range:
            return self._frozen_range
        if self._fixed_range:
            return self._fixed_range
        s = self.model.sections
        return s[0].start, s[-1].end

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
    # Layout of the two boxes to the right of a section
    # ------------------------------------------------------------------
    def _code_rect(self, i: int) -> Optional[QRect]:
        s = self.model.sections[i]
        if s.kind != WORK:
            return None
        y1, y2 = self._y(s.start), self._y(s.end)
        if y2 - y1 < 12:
            return None
        h = min(BOX_H, y2 - y1 - 4)
        return QRect(BOX_X, y1 + 2, CODE_W, h)

    def _letter_rect(self, i: int) -> Optional[QRect]:
        code = self._code_rect(i)
        if code is None:
            return None
        s = self.model.sections[i]
        top = code.bottom() + 3
        if top + BOX_H + 2 > self._y(s.end):
            return None
        return QRect(BOX_X, top, BOX_H, BOX_H)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1e1e1e"))
        if not self.model or not self.model.sections:
            p.end()
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        self._paint_meetings(p)
        self._paint_sections(p)
        self._paint_now_line(p)
        self._paint_nodes(p)
        p.end()

    def _paint_meetings(self, p: QPainter) -> None:
        r0, r1 = self._range()
        now = now_min()
        for start, end, _title in self.meetings:
            if end <= r0 or start >= r1:
                continue
            y1, y2 = self._y(max(start, r0)), self._y(min(end, r1))
            soon = self._is_today() and 0 < start - now <= ALERT_MINS
            if soon:
                glow = 0.5 + 0.5 * math.sin(self._pulse_phase)
                fill = QColor(90, 150, 255, int(50 + 70 * glow))
                edge = QColor(130, 180, 255, int(160 + 95 * glow))
            else:
                fill = QColor(120, 140, 170, 38)
                edge = QColor(120, 140, 170, 110)
            p.fillRect(QRect(0, y1, self.width(), max(2, y2 - y1)), fill)
            p.fillRect(QRect(0, y1, 2, max(2, y2 - y1)), edge)

    def _paint_sections(self, p: QPainter) -> None:
        fm = QFontMetrics(self._font)
        line_h = fm.lineSpacing()
        for i, s in enumerate(self.model.sections):
            y1, y2 = self._y(s.start), self._y(s.end)
            proj = self.projects.get(s.project_id) if s.project_id else None
            color = QColor(KIND_COLOR.get(s.kind) or (proj.color if proj else UNASSIGNED_COLOR))

            p.fillRect(QRect(self._track_x - TRACK_W // 2, y1, TRACK_W, y2 - y1), color)
            if self._compact:
                continue

            # Duration then title, wrapped, cropped to whole lines
            lines = (y2 - y1 - 14) // line_h
            if lines >= 1:
                title = KIND_LABEL.get(s.kind) or s.title
                text = fmt_duration(s.duration) + (f" {title}" if title else "")
                rect = QRect(TEXT_X, y1 + 8, TEXT_W, lines * line_h)
                p.save()
                p.setClipRect(rect)
                p.setFont(self._font)
                p.setPen(QColor("#b8b8b8"))
                p.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
                                     | Qt.TextFlag.TextWordWrap), text)
                p.restore()

            code_rect = self._code_rect(i)
            if code_rect:
                bg = QColor(proj.color) if proj else QColor("#2d2d2d")
                fg = QColor(contrasting_text(proj.color)) if proj else QColor("#888")
                p.setPen(QPen(QColor("#666"), 1))
                p.setBrush(bg)
                p.drawRoundedRect(QRectF(code_rect), 2, 2)
                p.setFont(self._bold)
                p.setPen(fg)
                p.drawText(code_rect, int(Qt.AlignmentFlag.AlignCenter),
                           proj.code if proj else "----")
            letter_rect = self._letter_rect(i)
            if letter_rect:
                p.setPen(QPen(QColor("#666"), 1))
                p.setBrush(QColor("#2d2d2d"))
                p.drawRoundedRect(QRectF(letter_rect), 2, 2)
                p.setFont(self._font)
                p.setPen(QColor("#ddd"))
                p.drawText(letter_rect, int(Qt.AlignmentFlag.AlignCenter), s.category)

    def _paint_now_line(self, p: QPainter) -> None:
        if not self._is_today():
            return
        r0, r1 = self._range()
        now = now_min()
        if r0 <= now <= r1:
            y = self._y(now)
            p.setPen(QPen(QColor("#e05555"), 1))
            p.drawLine(self._track_x - 12, y, self._track_x + 12, y)

    def _paint_nodes(self, p: QPainter) -> None:
        dragged = self._drag["k"] if self._drag and self._drag["what"] == "node" else None
        last_label_y = -100
        p.setFont(self._font)
        for k in range(self.model.node_count()):
            t = self.model.node_time(k)
            y = self._y(t)
            # Skip a time label that would sit on top of the one above
            if not self._compact and (k == dragged or y - last_label_y >= 11):
                p.setPen(QColor("#ffffff") if k == dragged else QColor("#e0e0e0"))
                p.drawText(QRect(TEXT_X, y - 7, TEXT_W, 14),
                           int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                           to_hhmm(t))
                last_label_y = y
            p.setPen(QPen(QColor("#1e1e1e"), 1))
            p.setBrush(QColor("#ffffff"))
            r = NODE_R + 1 if k == dragged else NODE_R
            p.drawEllipse(QPointF(self._track_x, y), r, r)

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------
    def _hit(self, x: float, y: float) -> Optional[tuple[str, int]]:
        if not self.model or not self.model.sections:
            return None
        for i in range(len(self.model.sections)):
            for name, rect in (("code", self._code_rect(i)), ("letter", self._letter_rect(i))):
                if rect and rect.adjusted(-1, -1, 1, 1).contains(int(x), int(y)):
                    return name, i
        if x < BOX_X:
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
        elif what == "letter":
            self._open_letter_menu(idx)
        elif what == "node":
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
            return
        d = self._drag
        if not d["moved"]:
            if abs(y - d["y0"]) < DRAG_THRESHOLD:
                return
            d["moved"] = True
            self._frozen_range = self._range()   # keep the scale still while dragging

        if d["what"] == "node":
            free = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            t = self._snap_node_time(self._t(y), use_meetings=not free)
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
        i = hit[1] if hit and hit[0] in ("section", "code", "letter") else self._section_at(event.pos().y())
        if i is None:
            return
        s = self.model.sections[i]
        t = snap(self._t(event.pos().y()), NODE_SNAP)
        menu = QMenu(self)
        split = menu.addAction("Split here")
        split.setEnabled(self.model.can_split(i, t))
        title = menu.addAction("Set title…")
        title.setEnabled(s.kind == WORK)
        menu.addSeparator()
        delete = menu.addAction("Delete")
        delete.setEnabled(self.model.can_delete(i))
        chosen = menu.exec(event.globalPos())
        if chosen == split:
            self._split(i, event.pos().y())
        elif chosen == title:
            self._set_title(i)
        elif chosen == delete:
            self._user_edit(lambda: self.model.delete(i))
            self._commit()

    def _update_cursor(self, x: float, y: float) -> None:
        hit = self._hit(x, y)
        if not hit:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif hit[0] in ("code", "letter"):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif hit[0] == "node":
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _snap_node_time(self, raw: float, use_meetings: bool) -> int:
        if use_meetings:
            edges = [e for start, end, _ in self.meetings for e in (start, end)]
            near = [e for e in edges if abs(e - raw) <= MEETING_SNAP]
            if near:
                return min(near, key=lambda e: abs(e - raw))
        return snap(raw, NODE_SNAP)

    # ------------------------------------------------------------------
    # Section actions
    # ------------------------------------------------------------------
    def _split(self, i: int, y: float) -> None:
        t = snap(self._t(y), NODE_SNAP)
        if self.model.can_split(i, t):
            self._user_edit(lambda: self.model.split(i, t))
            self._commit()

    def _set_title(self, i: int) -> None:
        s = self.model.sections[i]
        text, ok = QInputDialog.getText(self, "Section title", "Title:", text=s.title or "")
        if not ok:
            return
        s.title = text.strip() or None
        s.title_manual = s.title is not None
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
        self.projects = {p.id: p for p in models.get_all_projects()}
        self._remember_title(s)
        self._commit()

    def _open_letter_menu(self, i: int) -> None:
        s = self.model.sections[i]
        menu = QMenu(self)
        for letter in LETTERS:
            action = menu.addAction(letter)
            action.setCheckable(True)
            action.setChecked(letter == s.category)
        chosen = menu.exec(self.mapToGlobal(self._letter_rect(i).bottomLeft()))
        if chosen is None:
            return
        s.category = chosen.text()
        self._remember_title(s)
        self._commit()

    @staticmethod
    def _remember_title(s) -> None:
        """Learn that sections with this title belong to this project and letter."""
        if s.title and s.project_id:
            models.upsert_rule(s.title, s.project_id, s.category)

    # ------------------------------------------------------------------
    # Typing a node's time
    # ------------------------------------------------------------------
    def _open_editor(self, k: int) -> None:
        y = self._y(self.model.node_time(k))
        ed = QLineEdit(self)
        ed.setText(to_hhmm(self.model.node_time(k)))
        ed.setMaxLength(5)
        ed.setAlignment(Qt.AlignmentFlag.AlignRight)
        ed.setGeometry(TEXT_X + TEXT_W - 46, max(0, min(self.height() - 18, y - 9)), 48, 18)
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
                self._commit()

    # ------------------------------------------------------------------
    # Hover text
    # ------------------------------------------------------------------
    def event(self, e):
        if e.type() == QEvent.Type.ToolTip and self.model and self.model.sections:
            text = self._tooltip_at(e.pos().y())
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def _tooltip_at(self, y: int) -> str:
        i = self._section_at(y)
        if i is None:
            return ""
        s = self.model.sections[i]
        lines = [f"{to_hhmm(s.start)} – {to_hhmm(s.end)}  ({fmt_duration(s.duration)})"]
        title = KIND_LABEL.get(s.kind) or s.title
        if title:
            lines.append(title)
        if s.kind == WORK:
            proj = self.projects.get(s.project_id) if s.project_id else None
            lines.append(f"{proj.code} {proj.name} · {s.category}" if proj
                         else f"Unassigned · {s.category}")
        t = self._t(y)
        for start, end, m_title in self.meetings:
            if start <= t <= end:
                lines.append(f"Calendar: {m_title} ({to_hhmm(start)} – {to_hhmm(end)})")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Clock: the now-line and the upcoming-meeting pulse
    # ------------------------------------------------------------------
    def _on_clock(self) -> None:
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

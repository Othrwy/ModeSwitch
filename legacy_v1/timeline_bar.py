"""
TimelineBar — a custom QWidget that draws a horizontal stacked bar of
time blocks and supports:
  • Drag on dividers between blocks (snaps to 5-min grid)
  • Click on a block to show an inline start-time editor
  • read_only=True for compact history rows (no editing)
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QFont, QPen, QCursor
from PyQt6.QtWidgets import QWidget, QLineEdit, QApplication

from modeswitch.db.models import TimeBlock, Project, get_project_by_id
from modeswitch.widgets.time_input import parse_time_input


def _hhmm_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _minutes_to_hhmm(mins: int) -> str:
    mins = max(0, min(1439, mins))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _snap(minutes: int, step: int = 5) -> int:
    return round(minutes / step) * step


class TimelineBar(QWidget):
    block_edited = pyqtSignal(int, str, str)   # block_id, new_start, new_end

    HANDLE_HIT = 8   # px either side of a divider counts as a drag target

    def __init__(self, parent=None, read_only: bool = False):
        super().__init__(parent)
        self.read_only = read_only
        self.blocks: list[TimeBlock] = []
        self.projects: dict[int, Project] = {}
        self.day_start: int = 480    # 08:00 in minutes
        self.day_end: int = 1020     # 17:00 in minutes

        self._drag_idx: Optional[int] = None   # index into self.blocks divider being dragged
        self._drag_orig_x: int = 0
        self._inline_editor: Optional[QLineEdit] = None
        self._inline_block_idx: Optional[int] = None

        self.setMinimumHeight(28)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    def load(self, blocks: list[TimeBlock], projects: dict[int, Project],
             day_start: str, day_end: str) -> None:
        self.blocks = sorted(blocks, key=lambda b: b.start_time)
        self.projects = projects
        self.day_start = _hhmm_to_minutes(day_start)
        self.day_end = _hhmm_to_minutes(day_end) if day_end else self.day_start + 480
        # Ensure end > start to avoid zero-width bar
        if self.day_end <= self.day_start:
            self.day_end = self.day_start + 480
        self._close_inline_editor(commit=False)
        self.update()

    def resizeEvent(self, event):
        """Repaint on resize so blocks render at the correct width."""
        super().resizeEvent(event)
        self.update()

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------
    def _total_mins(self) -> int:
        return max(1, self.day_end - self.day_start)

    def _x_for_time(self, mins: int) -> int:
        ratio = (mins - self.day_start) / self._total_mins()
        return int(ratio * self.width())

    def _time_for_x(self, x: int) -> int:
        ratio = x / max(1, self.width())
        return int(self.day_start + ratio * self._total_mins())

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        w, h = self.width(), self.height()

        # Background
        p.fillRect(0, 0, w, h, QColor("#2b2b2b"))

        if not self.blocks:
            # Draw subtle diagonal stripe pattern to indicate no logged activity
            p.setPen(QPen(QColor("#383838"), 1))
            step = 8
            for i in range(-h, w + h, step):
                p.drawLine(i, h, i + h, 0)
            p.end()
            return

        font = QFont()
        font.setPointSize(8)
        p.setFont(font)

        for i, block in enumerate(self.blocks):
            start_m = _hhmm_to_minutes(block.start_time)
            if block.end_time:
                end_m = _hhmm_to_minutes(block.end_time)
            else:
                end_m = self.day_end

            x1 = self._x_for_time(start_m)
            x2 = self._x_for_time(end_m)
            rect_w = max(2, x2 - x1)

            proj = self.projects.get(block.project_id)
            color = QColor(proj.color if proj else "#555555")

            p.fillRect(x1, 0, rect_w, h, color)

            # Label
            if rect_w > 28:
                label = proj.code if proj else "?"
                p.setPen(Qt.GlobalColor.white)
                p.drawText(QRect(x1 + 2, 0, rect_w - 4, h),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           label)

        # Divider lines
        if not self.read_only:
            p.setPen(QPen(QColor("#1a1a1a"), 2))
            for block in self.blocks[1:]:
                x = self._x_for_time(_hhmm_to_minutes(block.start_time))
                p.drawLine(x, 0, x, h)

        p.end()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if self.read_only or event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()

        # Check for divider drag (between block i and i+1 → drag index = i)
        for i in range(1, len(self.blocks)):
            div_x = self._x_for_time(_hhmm_to_minutes(self.blocks[i].start_time))
            if abs(x - div_x) <= self.HANDLE_HIT:
                self._drag_idx = i
                self._drag_orig_x = int(x)
                QApplication.setOverrideCursor(QCursor(Qt.CursorShape.SizeHorCursor))
                return

        # Click on a block — open inline editor
        for i, block in enumerate(self.blocks):
            start_m = _hhmm_to_minutes(block.start_time)
            end_m = _hhmm_to_minutes(block.end_time) if block.end_time else self.day_end
            x1, x2 = self._x_for_time(start_m), self._x_for_time(end_m)
            if x1 <= x <= x2:
                self._open_inline_editor(i)
                return

    def mouseMoveEvent(self, event):
        if self.read_only:
            return
        x = int(event.position().x())

        if self._drag_idx is not None:
            new_mins = _snap(self._time_for_x(x))
            i = self._drag_idx
            # Clamp between previous block start + 5 and next block end - 5
            prev_start = _hhmm_to_minutes(self.blocks[i - 1].start_time) + 5
            if i < len(self.blocks) - 1 and self.blocks[i + 1].start_time:
                next_start = _hhmm_to_minutes(self.blocks[i].end_time or
                                               self.blocks[i + 1].start_time) - 5
            else:
                next_start = self.day_end - 5
            new_mins = max(prev_start, min(next_start, new_mins))
            self.blocks[i].start_time = _minutes_to_hhmm(new_mins)
            self.blocks[i - 1].end_time = _minutes_to_hhmm(new_mins)
            self.update()
            return

        # Cursor hint
        for i in range(1, len(self.blocks)):
            div_x = self._x_for_time(_hhmm_to_minutes(self.blocks[i].start_time))
            if abs(x - div_x) <= self.HANDLE_HIT:
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
                return
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseReleaseEvent(self, event):
        if self._drag_idx is not None:
            i = self._drag_idx
            self._drag_idx = None
            QApplication.restoreOverrideCursor()

            # Persist both the moved block and the one before it
            b_prev = self.blocks[i - 1]
            b_curr = self.blocks[i]
            if b_prev.end_time:
                self.block_edited.emit(b_prev.id, b_prev.start_time, b_prev.end_time)
            self.block_edited.emit(b_curr.id, b_curr.start_time,
                                   b_curr.end_time or "")

    # ------------------------------------------------------------------
    # Inline editor
    # ------------------------------------------------------------------
    def _open_inline_editor(self, block_idx: int) -> None:
        self._close_inline_editor(commit=False)
        block = self.blocks[block_idx]
        self._inline_block_idx = block_idx

        ed = QLineEdit(self)
        ed.setText(block.start_time)
        ed.setMaxLength(5)
        start_m = _hhmm_to_minutes(block.start_time)
        end_m = _hhmm_to_minutes(block.end_time) if block.end_time else self.day_end
        x1 = self._x_for_time(start_m)
        w = min(60, max(50, self._x_for_time(end_m) - x1))
        ed.setGeometry(x1 + 2, 4, w, self.height() - 8)
        ed.setStyleSheet("background: #fff; color: #000; border: none; font-size: 9px;")
        ed.returnPressed.connect(lambda: self._close_inline_editor(commit=True))
        ed.focusOutEvent = lambda e: (self._close_inline_editor(commit=True),
                                       QLineEdit.focusOutEvent(ed, e))
        self._inline_editor = ed
        ed.show()
        ed.setFocus()
        ed.selectAll()

    def _close_inline_editor(self, commit: bool = True) -> None:
        if self._inline_editor is None:
            return
        ed = self._inline_editor
        idx = self._inline_block_idx
        self._inline_editor = None
        self._inline_block_idx = None

        if commit and idx is not None and idx < len(self.blocks):
            text = ed.text().strip()
            parsed = parse_time_input(text)
            if parsed:
                block = self.blocks[idx]
                old_end = block.end_time or ""
                block.start_time = parsed
                # Also update previous block's end_time
                if idx > 0:
                    self.blocks[idx - 1].end_time = parsed
                    b_prev = self.blocks[idx - 1]
                    self.block_edited.emit(b_prev.id, b_prev.start_time, b_prev.end_time or "")
                self.block_edited.emit(block.id, parsed, old_end)
                self.update()

        ed.deleteLater()

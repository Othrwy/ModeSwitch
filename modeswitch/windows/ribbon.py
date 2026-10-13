"""
RibbonWindow — the narrow always-on-top strip down the right edge of the screen:
  • house button (working from home) and today's date
  • today's timeline
  • time left / credit
  • time per project
  • Review button
"""
from __future__ import annotations

from datetime import date, datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)

from modeswitch import days
from modeswitch.db import models
from modeswitch.system_times import first_on_time
from modeswitch.timeutil import fmt_duration, fmt_signed, now_min, to_hhmm
from modeswitch.widgets.day_timeline import DayTimeline, RIBBON_WIDTH
from modeswitch.widgets.house_button import HouseButton


def summary_text(timeline: DayTimeline) -> str:
    """One line per project and letter: '0000 | 2h 35m | A'."""
    lines = []
    for project_id, category, minutes in timeline.model.summary():
        proj = timeline.projects.get(project_id) if project_id else None
        code = proj.code if proj else "----"
        lines.append(f"{code:<4} | {fmt_duration(minutes):>6} | {category}")
    return "\n".join(lines)


class RibbonWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ModeSwitch")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self._today = ""
        self._review = None

        self._build_ui()
        self.place()
        self.open_today()

        # Heartbeat: last-seen time, day rollover, and the time-left readout
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60_000)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(0, 6, 0, 6)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 0)
        self._house = HouseButton()
        self._house.toggled.connect(self._on_house_toggled)
        header.addWidget(self._house)
        self._date_label = QLabel()
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._date_label.setStyleSheet("font-size: 11px; color: #aaa;")
        header.addWidget(self._date_label, stretch=1)
        root.addLayout(header)

        self.timeline = DayTimeline()
        self.timeline.changed.connect(self._on_timeline_changed)
        root.addWidget(self.timeline, stretch=1)

        root.addWidget(self._divider())

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status_label)

        self._summary_label = QLabel("")
        self._summary_label.setFont(QFont("Consolas", 8))
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._summary_label.setStyleSheet("color: #ccc;")
        root.addWidget(self._summary_label)

        self._review_btn = QPushButton("Review")
        self._review_btn.setCheckable(True)
        self._review_btn.clicked.connect(self._toggle_review)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(6, 2, 6, 0)
        btn_row.addWidget(self._review_btn)
        root.addLayout(btn_row)

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        return line

    def place(self) -> None:
        """Dock to the right edge of the primary screen, full height."""
        area = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(area.right() - RIBBON_WIDTH + 1, area.top(),
                         RIBBON_WIDTH, area.height())

    # ------------------------------------------------------------------
    # Day initialisation
    # ------------------------------------------------------------------
    def open_today(self) -> None:
        today = date.today()
        self._today = today.isoformat()
        days.finalise_past_days(self._today)

        start = first_on_time(today, models.get_setting("day_floor", "05:00")) \
            or to_hhmm(now_min())
        day = days.ensure_day(self._today, start=start, in_source="detected")

        self._date_label.setText(today.strftime("%a %d %b"))
        self._house.blockSignals(True)
        self._house.setChecked(day.wfh)
        self._house.blockSignals(False)
        self.timeline.load(day)
        self._refresh_readouts()

    def _tick(self) -> None:
        if date.today().isoformat() != self._today:
            self.open_today()
            return
        models.update_day(self.timeline.day.id, last_seen=datetime.now().strftime("%H:%M"))
        self._refresh_readouts()

    # ------------------------------------------------------------------
    # Readouts
    # ------------------------------------------------------------------
    def _refresh_readouts(self) -> None:
        self._summary_label.setText(summary_text(self.timeline))
        day, model = self.timeline.day, self.timeline.model

        if day.out_source == "computed":
            left = model.work_end - now_min()
            if left > 0:
                text, color = f"time left: {fmt_duration(left)}", "#aaa"
            else:
                text, color = f"overtime: +{fmt_duration(-left)}", "#f4a261"
        else:
            credit = model.credit(days.target_minutes())
            text = f"credit: {fmt_signed(credit)}"
            color = "#f4a261" if credit >= 0 else "#e07070"
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"font-size: 11px; color: {color};")

    def _on_timeline_changed(self) -> None:
        self._refresh_readouts()
        if self._review and self._review.isVisible():
            self._review.reload_day(self._today)

    def _on_house_toggled(self, checked: bool) -> None:
        self.timeline.set_wfh(checked)

    # ------------------------------------------------------------------
    # Review panel
    # ------------------------------------------------------------------
    def _toggle_review(self) -> None:
        if self._review and self._review.isVisible():
            self._review.hide()
        else:
            self.show_review()
        self._review_btn.setChecked(bool(self._review and self._review.isVisible()))

    def show_review(self) -> None:
        from modeswitch.windows.review_panel import ReviewPanel
        if self._review is None:
            self._review = ReviewPanel()
            self._review.data_changed.connect(self._on_review_changed)
        self._review.place_beside(self.geometry())
        self._review.refresh()
        self._review.show()
        self._review.raise_()
        self._review_btn.setChecked(True)

    def _on_review_changed(self) -> None:
        """Something was edited in the review panel; pick up today's changes."""
        self.timeline.reload()
        self._house.blockSignals(True)
        self._house.setChecked(self.timeline.day.wfh)
        self._house.blockSignals(False)
        self._refresh_readouts()

    # ------------------------------------------------------------------
    # Leaving for the day
    # ------------------------------------------------------------------
    def end_time_is_set(self) -> bool:
        return self.timeline.day.out_source == "manual"

    def save_out_time(self) -> None:
        self.timeline.set_end_now()

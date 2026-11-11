"""
HistoryWindow - last 7 days displayed as rows.

Layout per row:
  [DD MMM]  [Day]  [timeline bar]  [total time]  [credit]
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QMainWindow
)

from modeswitch.db import models
from modeswitch.db.models import Day, TimeBlock, get_project_by_id
from modeswitch.widgets.timeline_bar import TimelineBar

TARGET_MINUTES = 480


def _hhmm_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _format_duration(minutes: int) -> str:
    minutes = max(0, minutes)
    h = minutes // 60
    m = minutes % 60
    if h and m:
        return f"{h}h {m}m"
    elif h:
        return f"{h}h"
    return f"{m}m"


def _compute_day_credit(day: Day) -> int:
    if not day.in_time or not day.out_time:
        return 0
    total = _hhmm_to_minutes(day.out_time) - _hhmm_to_minutes(day.in_time)
    working = total - day.lunch_mins
    return working - TARGET_MINUTES


class HistoryWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ModeSwitch - History")
        self.resize(720, 340)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)

        self._container = QWidget()
        self._vbox = QVBoxLayout(self._container)
        self._vbox.setSpacing(4)
        self._vbox.setContentsMargins(12, 10, 12, 10)
        scroll.setWidget(self._container)

    def refresh(self) -> None:
        while self._vbox.count():
            item = self._vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today = date.today()
        self._vbox.addWidget(self._build_header())
        self._vbox.addWidget(self._divider())

        for i in range(7):
            day_date = today - timedelta(days=i)
            self._vbox.addWidget(self._build_day_row(day_date))
            if i < 6:
                self._vbox.addWidget(self._divider())

        self._vbox.addStretch()

    @staticmethod
    def _build_header() -> QWidget:
        row = QWidget()
        hbox = QHBoxLayout(row)
        hbox.setContentsMargins(0, 0, 0, 2)
        hbox.setSpacing(8)

        def lbl(text, w=None):
            l = QLabel(text)
            l.setStyleSheet("font-size: 10px; color: #555;")
            if w:
                l.setFixedWidth(w)
            return l

        hbox.addWidget(lbl("Date", 44))
        hbox.addWidget(lbl("Day", 28))
        hbox.addWidget(lbl("Activity"), 2)
        hbox.addWidget(lbl("Total", 48))
        hbox.addWidget(lbl("Credit", 64))
        hbox.addWidget(lbl("", 62))
        return row

    def _build_day_row(self, day_date: date) -> QWidget:
        row = QWidget()
        hbox = QHBoxLayout(row)
        hbox.setContentsMargins(0, 3, 0, 3)
        hbox.setSpacing(8)

        day = models.get_day(day_date.isoformat())

        date_lbl = QLabel(day_date.strftime("%d %b"))
        date_lbl.setFixedWidth(44)
        date_lbl.setStyleSheet("font-size: 12px; color: #ddd;")
        hbox.addWidget(date_lbl)

        day_lbl = QLabel(day_date.strftime("%a"))
        day_lbl.setFixedWidth(28)
        day_lbl.setStyleSheet("font-size: 12px; color: #888;")
        hbox.addWidget(day_lbl)

        if day and day.is_holiday:
            holiday_lbl = QLabel("Holiday")
            holiday_lbl.setStyleSheet("color: #6ab0f5; font-size: 11px;")
            hbox.addWidget(holiday_lbl, stretch=2)
            hbox.addWidget(QLabel(""))
            hbox.addWidget(QLabel(""))
            remove_btn = QPushButton("Remove Holiday")
            remove_btn.setFixedHeight(20)
            remove_btn.setStyleSheet("font-size: 9px; padding: 1px 6px;")
            remove_btn.clicked.connect(lambda _, d=day: self._remove_holiday(d))
            hbox.addWidget(remove_btn)
            return row

        blocks = models.get_blocks_for_day(day.id) if day else []
        proj_map = {b.project_id: get_project_by_id(b.project_id) for b in blocks}
        in_t = (day.in_time if day else None) or "08:00"
        out_t = (day.out_time if day else None) or "17:00"

        bar = TimelineBar(read_only=False)
        bar.setFixedHeight(22)
        bar.load(blocks, proj_map, in_t, out_t)
        bar.block_edited.connect(self._on_block_edited)
        hbox.addWidget(bar, stretch=2)

        if day and day.in_time and day.out_time:
            credit = _compute_day_credit(day)
            total_mins = TARGET_MINUTES + credit
            total_text = _format_duration(total_mins)
        else:
            credit = 0
            total_text = "-"

        total_lbl = QLabel(total_text)
        total_lbl.setFixedWidth(48)
        total_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        total_lbl.setStyleSheet("font-size: 11px; color: #aaa;")
        hbox.addWidget(total_lbl)

        if day and day.in_time and day.out_time:
            sign = "+" if credit >= 0 else ""
            credit_color = "#f4a261" if credit >= 0 else "#e07070"
            credit_text = f"{sign}{credit}mins"
        else:
            credit_color = "#555"
            credit_text = "-"

        credit_lbl = QLabel(credit_text)
        credit_lbl.setFixedWidth(64)
        credit_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        credit_lbl.setStyleSheet(f"font-size: 11px; color: {credit_color};")
        hbox.addWidget(credit_lbl)

        hol_btn = QPushButton("Holiday")
        hol_btn.setFixedSize(62, 20)
        hol_btn.setStyleSheet(
            "font-size: 9px; background: #3a3a3a; color: #888; border-radius: 3px; padding: 1px;"
        )
        hol_btn.clicked.connect(lambda _, dd=day_date: self._mark_holiday(dd))
        hbox.addWidget(hol_btn)

        return row

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #2a2a2a;")
        line.setFixedHeight(1)
        return line

    def _mark_holiday(self, day_date: date) -> None:
        iso = day_date.isoformat()
        day = models.get_or_create_day(iso, in_time="08:00")
        models.update_day(day.id, is_holiday=True, out_time="16:00")
        from modeswitch.db.schema import get_connection
        with get_connection() as conn:
            proj_row = conn.execute(
                "SELECT id FROM projects WHERE code='LNCH' LIMIT 1"
            ).fetchone()
            conn.execute("DELETE FROM time_blocks WHERE day_id=?", (day.id,))
        if proj_row:
            models.create_block(day.id, proj_row["id"], "08:00")
            open_block = models.get_open_block(day.id)
            if open_block:
                models.close_block(open_block.id, "16:00")
        self.refresh()

    def _remove_holiday(self, day: Day) -> None:
        models.update_day(day.id, is_holiday=False)
        self.refresh()

    def _on_block_edited(self, block_id: int, new_start: str, new_end: str) -> None:
        kw = {"start_time": new_start}
        if new_end:
            kw["end_time"] = new_end
        models.update_block(block_id, **kw)

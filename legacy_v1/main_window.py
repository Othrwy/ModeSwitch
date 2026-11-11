"""
MainWindow — the primary application window containing:
  • In / Lunch / Out time fields with time-left / overtime label
  • Today's timeline bar
  • Project mode-switch grid
  • Navigation to History
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QAbstractSpinBox, QPushButton, QFrame, QSizePolicy
)

from modeswitch.db import models
from modeswitch.db.models import Day, TimeBlock, get_project_by_id
from modeswitch.widgets.time_input import TimeInputWidget, parse_time_input
from modeswitch.widgets.timeline_bar import TimelineBar
from modeswitch.widgets.project_grid import ProjectGrid
from modeswitch.dialogs.add_project import AddProjectDialog


TARGET_MINUTES = 480   # 8-hour day


def _hhmm_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _minutes_to_hhmm(mins: int) -> str:
    mins = max(0, min(1439, mins))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ModeSwitch")
        self.setMinimumWidth(460)

        self._day: Day | None = None
        self._open_block: TimeBlock | None = None
        self._lunch_edited = False

        self._build_ui()
        self._init_day()

        # Refresh overtime label every minute
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_time_left)
        self._timer.start(60_000)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(12, 12, 12, 12)

        # --- Date label ---
        self._date_label = QLabel()
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date_label.setStyleSheet("font-size: 13px; color: #aaa;")
        root.addWidget(self._date_label)

        # --- In / Lunch / Out row ---
        ilo_row = QHBoxLayout()
        ilo_row.setSpacing(16)

        self._in_widget = self._make_time_field("In", ilo_row)
        self._lunch_spin = self._make_lunch_field(ilo_row)
        self._out_widget = self._make_time_field("Out", ilo_row)

        root.addLayout(ilo_row)

        # --- Time left / overtime ---
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("font-size: 12px; color: #ccc;")
        root.addWidget(self._status_label)

        # --- Divider ---
        root.addWidget(self._divider())

        # --- Mode-switch label + Edit Modes button ---
        mode_row = QHBoxLayout()
        mode_label = QLabel("Mode Switch")
        mode_label.setStyleSheet("font-size: 11px; color: #888;")
        mode_row.addWidget(mode_label)
        mode_row.addStretch()
        edit_modes_btn = QPushButton("Edit Modes")
        edit_modes_btn.setFixedHeight(22)
        edit_modes_btn.setStyleSheet("font-size: 10px; padding: 1px 8px;")
        edit_modes_btn.clicked.connect(self._open_edit_modes)
        mode_row.addWidget(edit_modes_btn)
        root.addLayout(mode_row)

        # --- Switch-time row (shown when a mode switch is pending) ---
        self._switch_row = QWidget()
        switch_layout = QHBoxLayout(self._switch_row)
        switch_layout.setContentsMargins(0, 0, 0, 0)
        switch_layout.setSpacing(6)
        self._switch_label = QLabel("Switch at:")
        self._switch_time_input = TimeInputWidget()
        self._switch_confirm_btn = QPushButton("Confirm")
        self._switch_confirm_btn.clicked.connect(self._confirm_mode_switch)
        switch_layout.addWidget(self._switch_label)
        switch_layout.addWidget(self._switch_time_input)
        switch_layout.addWidget(self._switch_confirm_btn)
        switch_layout.addStretch()
        self._switch_row.setVisible(False)
        root.addWidget(self._switch_row)

        # --- Project grid ---
        self._project_grid = ProjectGrid()
        self._project_grid.mode_switched.connect(self._on_mode_switched)
        self._project_grid.add_requested.connect(self._on_add_project)
        root.addWidget(self._project_grid)

        # --- Divider ---
        root.addWidget(self._divider())

        # --- Today's timeline ---
        timeline_label = QLabel("Today")
        timeline_label.setStyleSheet("font-size: 11px; color: #888;")
        root.addWidget(timeline_label)

        self._timeline = TimelineBar()
        self._timeline.setFixedHeight(32)
        self._timeline.block_edited.connect(self._on_block_edited)
        root.addWidget(self._timeline)

        # --- History button ---
        hist_btn = QPushButton("View History")
        hist_btn.clicked.connect(self._open_history)
        root.addWidget(hist_btn)

        root.addStretch()

        self._pending_project_id: int | None = None

    def _make_time_field(self, label_text: str, layout: QHBoxLayout) -> TimeInputWidget:
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl = QLabel(label_text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 11px; color: #aaa;")
        widget = TimeInputWidget()
        widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(lbl)
        col.addWidget(widget)
        layout.addLayout(col)
        return widget

    def _make_lunch_field(self, layout: QHBoxLayout) -> QSpinBox:
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl = QLabel("Lunch")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 11px; color: #aaa;")
        spin = QSpinBox()
        spin.setRange(0, 240)
        spin.setValue(60)
        spin.setSuffix(" mins")
        spin.setFixedWidth(80)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setStyleSheet("color: #666;")  # greyed until edited
        spin.valueChanged.connect(self._on_lunch_changed)
        col.addWidget(lbl)
        col.addWidget(spin, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(col)
        return spin

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        return line

    # ------------------------------------------------------------------
    # Day initialisation
    # ------------------------------------------------------------------
    def _init_day(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        now = _now_hhmm()
        self._day = models.get_or_create_day(today, in_time=now)

        self._date_label.setText(datetime.now().strftime("%A, %d %B %Y"))
        self._in_widget.set_time(self._day.in_time)
        self._lunch_spin.blockSignals(True)
        self._lunch_spin.setValue(self._day.lunch_mins)
        self._lunch_spin.blockSignals(False)
        self._recalculate_out()
        self._update_time_left()
        self._reload_timeline()

        self._in_widget.time_changed.connect(self._on_in_changed)
        self._out_widget.time_changed.connect(self._on_out_changed)

        # Restore active project from open block
        self._open_block = models.get_open_block(self._day.id)
        if self._open_block:
            self._project_grid.set_active_project(self._open_block.project_id)

    # ------------------------------------------------------------------
    # Time field logic
    # ------------------------------------------------------------------
    def _on_in_changed(self, value: str) -> None:
        if self._day:
            models.update_day(self._day.id, in_time=value)
            self._day.in_time = value
        self._recalculate_out()
        self._update_time_left()

    def _on_lunch_changed(self, value: int) -> None:
        self._lunch_spin.setStyleSheet("color: #fff;")  # un-grey
        self._lunch_edited = True
        if self._day:
            models.update_day(self._day.id, lunch_mins=value)
            self._day.lunch_mins = value
        self._recalculate_out()
        self._update_time_left()

    def _on_out_changed(self, value: str) -> None:
        if self._day:
            models.update_day(self._day.id, out_time=value)
            self._day.out_time = value
        self._update_time_left()

    def _recalculate_out(self) -> None:
        """Compute out = in + 8h - lunch and display it (unless manually set)."""
        if not self._day or not self._day.in_time:
            return
        in_m = _hhmm_to_minutes(self._day.in_time)
        lunch = self._day.lunch_mins
        out_m = in_m + TARGET_MINUTES + lunch
        computed = _minutes_to_hhmm(out_m)
        self._out_widget.set_time(computed)
        # Update DB only if out hasn't been manually overridden
        models.update_day(self._day.id, out_time=computed)
        if self._day:
            self._day.out_time = computed

    def _update_time_left(self) -> None:
        if not self._day or not self._day.out_time:
            self._status_label.setText("")
            return
        now_m = _hhmm_to_minutes(_now_hhmm())
        out_m = _hhmm_to_minutes(self._day.out_time)
        diff = out_m - now_m
        if diff > 0:
            self._status_label.setText(f"time left: {diff}mins")
            self._status_label.setStyleSheet("font-size: 12px; color: #aaa;")
        else:
            self._status_label.setText(f"overtime: +{-diff}mins")
            self._status_label.setStyleSheet("font-size: 12px; color: #f4a261;")

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------
    def _on_mode_switched(self, project_id: int, default_time: str) -> None:
        self._pending_project_id = project_id
        self._switch_time_input.set_time(default_time)
        self._switch_row.setVisible(True)
        self._switch_time_input.setFocus()
        self._switch_time_input.selectAll()

    def _confirm_mode_switch(self) -> None:
        switch_time = self._switch_time_input.get_time()
        if not switch_time or not self._day:
            return

        # Close the currently open block
        if self._open_block:
            models.close_block(self._open_block.id, switch_time)
            self._open_block = None

        if self._pending_project_id is not None:
            self._open_block = models.create_block(
                self._day.id, self._pending_project_id, switch_time
            )
            models.update_project(self._pending_project_id, last_used=switch_time)
            self._project_grid.set_active_project(self._pending_project_id)

        self._switch_row.setVisible(False)
        self._pending_project_id = None
        self._project_grid.refresh()
        self._reload_timeline()

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------
    def _reload_timeline(self) -> None:
        if not self._day:
            return
        blocks = models.get_blocks_for_day(self._day.id)
        proj_ids = {b.project_id for b in blocks}
        projects = {pid: get_project_by_id(pid) for pid in proj_ids}
        in_t = self._day.in_time or _now_hhmm()
        out_t = self._day.out_time or _minutes_to_hhmm(_hhmm_to_minutes(in_t) + TARGET_MINUTES + 60)
        self._timeline.load(blocks, projects, in_t, out_t)

    def _on_block_edited(self, block_id: int, new_start: str, new_end: str) -> None:
        kw = {"start_time": new_start}
        if new_end:
            kw["end_time"] = new_end
        models.update_block(block_id, **kw)

    # ------------------------------------------------------------------
    # Add project / Edit modes
    # ------------------------------------------------------------------
    def _on_add_project(self) -> None:
        dlg = AddProjectDialog(self)
        if dlg.exec():
            self._project_grid.refresh()

    def _open_edit_modes(self) -> None:
        from modeswitch.windows.edit_modes import EditModesDialog
        dlg = EditModesDialog(self)
        dlg.exec()
        self._project_grid.refresh()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def _open_history(self) -> None:
        from modeswitch.windows.history_panel import HistoryWindow
        if not hasattr(self, "_history_win") or self._history_win is None:
            self._history_win = HistoryWindow(parent=None)
        self._history_win.refresh()
        self._history_win.show()
        self._history_win.raise_()

    # ------------------------------------------------------------------
    # Save out time on close
    # ------------------------------------------------------------------
    def save_out_time(self) -> None:
        if self._day and not self._day.out_time:
            now = _now_hhmm()
            models.update_day(self._day.id, out_time=now)

        if self._open_block:
            now = _now_hhmm()
            models.close_block(self._open_block.id, now)
            self._open_block = None

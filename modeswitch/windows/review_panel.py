"""
ReviewPanel — opens beside the ribbon, on the side away from the screen edge.

Top:    one editable timeline per past working day, this week and last week,
        oldest on the left; "Earlier" adds another week. Today is left out, because
        it is already on the ribbon.
Bottom: the projects table and the credit chart.
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QScreen
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QColorDialog, QMessageBox, QGroupBox
)

from modeswitch import days
from modeswitch.db import models
from modeswitch.timeutil import fmt_duration, fmt_signed
from modeswitch.widgets.credit_chart import ChartDay, CreditChart
from modeswitch.widgets.day_timeline import DayTimeline, RIBBON_WIDTH
from modeswitch.widgets.house_button import HouseButton
from modeswitch.widgets.icon_buttons import SandwichButton, SunButton
from modeswitch.windows.ribbon import summary_text

TABLES_HEIGHT = 230
COLUMN_GAP = 8


class DayColumn(QWidget):
    """Header, timeline, totals and time per project for one day."""
    changed = pyqtSignal()

    def __init__(self, day_date: date, parent=None):
        super().__init__(parent)
        self.day_date = day_date
        self.date_str = day_date.isoformat()
        self.setFixedWidth(RIBBON_WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 0)
        self._house = HouseButton(size=20)
        self._house.toggled.connect(self._on_house_toggled)
        header.addWidget(self._house)
        self._lunch = SandwichButton(size=20)
        self._lunch.toggled.connect(lambda on: self.timeline.set_lunch(on))
        header.addWidget(self._lunch)
        label = QLabel(day_date.strftime("%a %d %b"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        is_today = day_date == date.today()
        label.setStyleSheet(f"font-size: 11px; color: {'#fff' if is_today else '#aaa'};")
        header.addWidget(label, stretch=1)
        self._holiday_btn = SunButton(size=20)
        self._holiday_btn.clicked.connect(self._on_holiday_clicked)
        header.addWidget(self._holiday_btn)
        root.addLayout(header)

        self.timeline = DayTimeline()
        self.timeline.changed.connect(self._on_timeline_changed)
        root.addWidget(self.timeline, stretch=1)

        self._placeholder = QWidget()
        ph = QVBoxLayout(self._placeholder)
        self._placeholder_label = QLabel()
        self._placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder_label.setStyleSheet("color: #666;")
        self._add_btn = QPushButton("Add day")
        self._add_btn.clicked.connect(self._on_add_day)
        ph.addStretch()
        ph.addWidget(self._placeholder_label)
        ph.addWidget(self._add_btn)
        ph.addStretch()
        root.addWidget(self._placeholder, stretch=1)

        self._totals = QLabel()
        self._totals.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._totals.setStyleSheet("font-size: 11px; color: #aaa;")
        root.addWidget(self._totals)

        self._summary = QLabel()
        self._summary.setFont(QFont("Consolas", 8))
        self._summary.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._summary.setStyleSheet("color: #ccc;")
        root.addWidget(self._summary)

        self.reload()

    def has_timeline(self) -> bool:
        return self.timeline.isVisibleTo(self)

    def reload(self) -> None:
        day = models.get_day(self.date_str)
        holiday = bool(day and day.is_holiday)
        has_blocks = bool(day and models.get_blocks_for_day(day.id))
        show_timeline = has_blocks and not holiday

        self._holiday_btn.setChecked(holiday)
        self._house.setVisible(show_timeline)
        self._lunch.setVisible(show_timeline)
        self.timeline.setVisible(show_timeline)
        self._placeholder.setVisible(not show_timeline)
        self._placeholder_label.setText("Holiday" if holiday else "No data")
        self._add_btn.setVisible(not holiday)

        if show_timeline:
            self.timeline.load(day)
            model = self.timeline.model
            for button, checked in ((self._house, day.wfh), (self._lunch, model.has_lunch())):
                button.blockSignals(True)
                button.setChecked(checked)
                button.blockSignals(False)
            credit = model.credit(days.target_minutes())
            color = "#f4a261" if credit >= 0 else "#e07070"
            self._totals.setText(
                f"{fmt_duration(model.worked_minutes())}  "
                f"<span style='color:{color}'>{fmt_signed(credit)}</span>")
            self._summary.setText(summary_text(self.timeline))
        else:
            self._totals.setText("-")
            self._summary.setText("")

    def summary_lines(self) -> int:
        text = self._summary.text()
        return text.count("\n") + 1 if text else 0

    def set_summary_lines(self, lines: int) -> None:
        """Every column reserves the same space, so the timelines stay level."""
        self._summary.setFixedHeight(lines * QFontMetrics(self._summary.font()).lineSpacing())

    def _on_timeline_changed(self) -> None:
        self.reload()
        self.changed.emit()

    def _on_house_toggled(self, checked: bool) -> None:
        self.timeline.set_wfh(checked)

    def _on_add_day(self) -> None:
        days.ensure_day(self.date_str)
        self.reload()
        self.changed.emit()

    def _on_holiday_clicked(self, checked: bool) -> None:
        day = models.get_or_create_day(self.date_str, wfh=days.default_wfh(self.day_date))
        models.update_day(day.id, is_holiday=checked)
        self.reload()
        self.changed.emit()


class ReviewPanel(QWidget):
    data_changed = pyqtSignal()   # a day or project was edited here

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ModeSwitch - Review")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self._weeks_back = 1
        self._columns: list[DayColumn] = []
        self._from_right = 0       # how far the day strip is scrolled back from today
        self._rebuilding = False
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        bar = QHBoxLayout()
        earlier = QPushButton("◀ Earlier")
        earlier.clicked.connect(self._show_earlier)
        bar.addWidget(earlier)
        bar.addStretch()
        title = QLabel("Review")
        title.setStyleSheet("font-size: 13px; color: #aaa;")
        bar.addWidget(title)
        bar.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        bar.addWidget(close)
        root.addLayout(bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._days_widget = QWidget()
        self._days_layout = QHBoxLayout(self._days_widget)
        self._days_layout.setContentsMargins(0, 0, 0, 0)
        self._days_layout.setSpacing(COLUMN_GAP)
        self._scroll.setWidget(self._days_widget)
        bar_h = self._scroll.horizontalScrollBar()
        bar_h.rangeChanged.connect(self._on_scroll_range)
        bar_h.valueChanged.connect(self._on_scroll_value)
        root.addWidget(self._scroll, stretch=1)

        tables = QHBoxLayout()
        tables.addWidget(self._build_projects_group(), stretch=2)
        tables.addWidget(self._build_credit_group(), stretch=3)
        holder = QWidget()
        holder.setLayout(tables)
        tables.setContentsMargins(0, 0, 0, 0)
        holder.setFixedHeight(TABLES_HEIGHT)
        root.addWidget(holder)

    def _build_projects_group(self) -> QGroupBox:
        group = QGroupBox("Projects")
        vbox = QVBoxLayout(group)
        self._proj_table = QTableWidget()
        self._proj_table.setColumnCount(4)
        self._proj_table.setHorizontalHeaderLabels(["Code", "Name", "Colour", ""])
        self._proj_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._proj_table.verticalHeader().setVisible(False)
        self._proj_table.setColumnWidth(0, 60)
        self._proj_table.setColumnWidth(2, 60)
        self._proj_table.setColumnWidth(3, 30)
        self._proj_table.itemChanged.connect(self._on_project_item_changed)
        vbox.addWidget(self._proj_table)
        add = QPushButton("+ Add project")
        add.clicked.connect(self._add_project)
        vbox.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
        return group

    def _build_credit_group(self) -> QGroupBox:
        group = QGroupBox("Credit — hours worked each day (dashed) against the nominal day (solid)")
        vbox = QVBoxLayout(group)
        self._chart = CreditChart()
        vbox.addWidget(self._chart)
        return group

    def place_beside(self, ribbon_geometry: QRect, screen: QScreen, edge: str) -> None:
        """Fill the space beside the ribbon, as wide as the days need."""
        area = screen.availableGeometry()
        wanted = len(self._visible_dates()) * (RIBBON_WIDTH + COLUMN_GAP) + 24
        if edge == "right":
            width = max(720, min(wanted, ribbon_geometry.left() - area.left()))
            left = ribbon_geometry.left() - width
        else:
            width = max(720, min(wanted, area.right() - ribbon_geometry.right()))
            left = ribbon_geometry.right() + 1
        self.setGeometry(left, ribbon_geometry.top(), width, ribbon_geometry.height())

    # ------------------------------------------------------------------
    # Day columns
    # ------------------------------------------------------------------
    def _visible_dates(self) -> list[date]:
        """Working days from the Monday `_weeks_back` weeks ago up to yesterday."""
        today = date.today()
        monday = today - timedelta(days=today.weekday() + 7 * self._weeks_back)
        working = models.get_day_list_setting("working_days")
        count = (today - monday).days
        return [d for d in (monday + timedelta(days=i) for i in range(count))
                if d.isoweekday() in working]

    def _on_scroll_value(self, value: int) -> None:
        if not self._rebuilding:
            self._from_right = self._scroll.horizontalScrollBar().maximum() - value

    def _on_scroll_range(self, _low: int, high: int) -> None:
        # Hold the view still relative to the newest day, which sits on the right
        bar = self._scroll.horizontalScrollBar()
        bar.blockSignals(True)
        bar.setValue(high - self._from_right)
        bar.blockSignals(False)

    def _end_rebuild(self) -> None:
        self._rebuilding = False

    def refresh(self) -> None:
        self._rebuilding = True
        QTimer.singleShot(200, self._end_rebuild)
        for col in self._columns:
            col.setParent(None)
            col.deleteLater()
        self._columns = []
        while self._days_layout.count():
            self._days_layout.takeAt(0)

        self._days_layout.addStretch()
        for d in self._visible_dates():
            col = DayColumn(d)
            col.changed.connect(self._on_day_changed)
            self._columns.append(col)
            self._days_layout.addWidget(col)

        self._sync_ranges()
        self._update_chart()
        self._populate_projects()

    def _show_earlier(self) -> None:
        self._weeks_back += 1
        self.refresh()

    def _sync_ranges(self) -> None:
        """Put every day on the same time scale so they line up side by side."""
        lines = max((c.summary_lines() for c in self._columns), default=0)
        for col in self._columns:
            col.set_summary_lines(lines)
        models_ = [c.timeline.model for c in self._columns
                   if c.has_timeline() and c.timeline.model and c.timeline.model.sections]
        if not models_:
            return
        start = min(m.sections[0].start for m in models_)
        end = max(m.sections[-1].end for m in models_)
        for col in self._columns:
            col.timeline.set_range(start, end)

    def reload_day(self, date_str: str) -> None:
        """Called when that day was edited somewhere else (the ribbon)."""
        for col in self._columns:
            if col.date_str == date_str:
                col.reload()
        self._sync_ranges()
        self._update_chart()

    def _reload_all(self) -> None:
        for col in self._columns:
            col.reload()
        self._sync_ranges()
        self._update_chart()

    def _on_day_changed(self) -> None:
        self._sync_ranges()
        self._update_chart()
        self.data_changed.emit()

    def _update_chart(self) -> None:
        rows = []
        for col in self._columns:
            if col.has_timeline():
                rows.append(ChartDay(col.day_date, col.timeline.model.worked_minutes()))
            else:
                day = models.get_day(col.date_str)
                rows.append(ChartDay(col.day_date, None,
                                     "Holiday" if day and day.is_holiday else "No data"))
        self._chart.set_days(rows, days.target_minutes())

    # ------------------------------------------------------------------
    # Projects table
    # ------------------------------------------------------------------
    def _populate_projects(self) -> None:
        self._proj_table.blockSignals(True)
        self._proj_table.setRowCount(0)
        for proj in models.get_all_projects():
            row = self._proj_table.rowCount()
            self._proj_table.insertRow(row)

            code_item = QTableWidgetItem(proj.code)
            code_item.setData(Qt.ItemDataRole.UserRole, proj.id)
            self._proj_table.setItem(row, 0, code_item)
            self._proj_table.setItem(row, 1, QTableWidgetItem(proj.name))

            color_btn = QPushButton()
            color_btn.setStyleSheet(f"background: {proj.color}; border: none; border-radius: 3px;")
            color_btn.clicked.connect(lambda _, p=proj: self._pick_color(p))
            self._proj_table.setCellWidget(row, 2, color_btn)

            del_btn = QPushButton("✕")
            del_btn.setToolTip("Delete project")
            del_btn.clicked.connect(lambda _, p=proj: self._delete_project(p))
            self._proj_table.setCellWidget(row, 3, del_btn)
        self._proj_table.blockSignals(False)

    def _projects_edited(self) -> None:
        self._populate_projects()
        self._reload_all()
        self.data_changed.emit()

    def _on_project_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        pid = self._proj_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        text = item.text().strip()
        if item.column() == 0:
            code = text.upper()
            taken = {p.code for p in models.get_all_projects() if p.id != pid}
            if not code or len(code) > 4 or code in taken:
                QMessageBox.warning(self, "Project code",
                                    "The code must be 1 to 4 characters and not already in use.")
            else:
                models.update_project(pid, code=code)
        elif item.column() == 1 and text:
            models.update_project(pid, name=text)
        # Rebuild once the table has finished committing the edit
        QTimer.singleShot(0, self._projects_edited)

    def _pick_color(self, proj) -> None:
        color = QColorDialog.getColor(QColor(proj.color), self, "Choose Colour")
        if color.isValid():
            models.update_project(proj.id, color=color.name())
            self._projects_edited()

    def _delete_project(self, proj) -> None:
        reply = QMessageBox.question(
            self, "Delete Project",
            f"Delete {proj.code} {proj.name}?\n"
            "Time already logged against it is kept but becomes unassigned.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            models.delete_project(proj.id)
            self._projects_edited()

    def _add_project(self) -> None:
        from modeswitch.dialogs.add_project import AddProjectDialog
        if AddProjectDialog(self).exec():
            self._projects_edited()

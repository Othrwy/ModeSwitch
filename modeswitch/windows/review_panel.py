"""
ReviewPanel — opens to the left of the ribbon.

Top:    one editable timeline per working day, this week and last week,
        oldest on the left; "Earlier" adds another week.
Bottom: the projects table and the title rules table.
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QColorDialog, QMessageBox, QInputDialog, QGroupBox, QToolButton
)

from modeswitch import days
from modeswitch.db import models
from modeswitch.timeutil import fmt_duration, fmt_signed
from modeswitch.widgets.day_timeline import DayTimeline, RIBBON_WIDTH, LETTERS
from modeswitch.widgets.house_button import HouseButton

TABLES_HEIGHT = 230
COLUMN_GAP = 8


class DayColumn(QWidget):
    """Header, timeline and totals for one day."""
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
        label = QLabel(day_date.strftime("%a %d %b"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        is_today = day_date == date.today()
        label.setStyleSheet(f"font-size: 11px; color: {'#fff' if is_today else '#aaa'};")
        header.addWidget(label, stretch=1)
        self._holiday_btn = QToolButton()
        self._holiday_btn.setText("H")
        self._holiday_btn.setCheckable(True)
        self._holiday_btn.setFixedSize(20, 20)
        self._holiday_btn.setToolTip("Mark as holiday")
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
        self.timeline.setVisible(show_timeline)
        self._placeholder.setVisible(not show_timeline)
        self._placeholder_label.setText("Holiday" if holiday else "No data")
        self._add_btn.setVisible(not holiday)

        if show_timeline:
            self.timeline.load(day)
            self._house.blockSignals(True)
            self._house.setChecked(day.wfh)
            self._house.blockSignals(False)
            model = self.timeline.model
            credit = model.credit(days.target_minutes())
            color = "#f4a261" if credit >= 0 else "#e07070"
            self._totals.setText(
                f"{fmt_duration(model.worked_minutes())}  "
                f"<span style='color:{color}'>{fmt_signed(credit)}</span>")
        else:
            self._totals.setText("-")

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
    data_changed = pyqtSignal()   # a day, project or rule was edited here

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
        close = QPushButton("Close ▶")
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
        tables.addWidget(self._build_projects_group(), stretch=3)
        tables.addWidget(self._build_rules_group(), stretch=2)
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

    def _build_rules_group(self) -> QGroupBox:
        group = QGroupBox("Title rules — a section whose title contains the text gets the project")
        vbox = QVBoxLayout(group)
        self._rule_table = QTableWidget()
        self._rule_table.setColumnCount(4)
        self._rule_table.setHorizontalHeaderLabels(["Title contains", "Code", "Letter", ""])
        self._rule_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._rule_table.verticalHeader().setVisible(False)
        self._rule_table.setColumnWidth(1, 70)
        self._rule_table.setColumnWidth(2, 50)
        self._rule_table.setColumnWidth(3, 30)
        self._rule_table.itemChanged.connect(self._on_rule_item_changed)
        vbox.addWidget(self._rule_table)
        add = QPushButton("+ Add rule")
        add.clicked.connect(self._add_rule)
        vbox.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
        return group

    def place_beside(self, ribbon_geometry: QRect) -> None:
        """Fill the space to the left of the ribbon, as wide as the days need."""
        area = QApplication.primaryScreen().availableGeometry()
        wanted = len(self._visible_dates()) * (RIBBON_WIDTH + COLUMN_GAP) + 24
        width = max(720, min(wanted, ribbon_geometry.left() - area.left()))
        self.setGeometry(ribbon_geometry.left() - width, ribbon_geometry.top(),
                         width, ribbon_geometry.height())

    # ------------------------------------------------------------------
    # Day columns
    # ------------------------------------------------------------------
    def _visible_dates(self) -> list[date]:
        """Working days from the Monday `_weeks_back` weeks ago up to today."""
        today = date.today()
        monday = today - timedelta(days=today.weekday() + 7 * self._weeks_back)
        working = models.get_day_list_setting("working_days")
        count = (today - monday).days + 1
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
        self._populate_projects()
        self._populate_rules()

    def _show_earlier(self) -> None:
        self._weeks_back += 1
        self.refresh()

    def _sync_ranges(self) -> None:
        """Put every day on the same time scale so they line up side by side."""
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
        self._populate_rules()

    def _reload_all(self) -> None:
        for col in self._columns:
            col.reload()
        self._sync_ranges()

    def _on_day_changed(self) -> None:
        self._sync_ranges()
        self._populate_rules()
        self.data_changed.emit()

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
        self._populate_rules()
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

    # ------------------------------------------------------------------
    # Title rules table
    # ------------------------------------------------------------------
    def _populate_rules(self) -> None:
        projects = models.get_all_projects()
        self._rule_table.blockSignals(True)
        self._rule_table.setRowCount(0)
        for rule in models.get_rules():
            row = self._rule_table.rowCount()
            self._rule_table.insertRow(row)

            pattern_item = QTableWidgetItem(rule.pattern)
            pattern_item.setData(Qt.ItemDataRole.UserRole, rule.id)
            self._rule_table.setItem(row, 0, pattern_item)

            code_box = QComboBox()
            for p in projects:
                code_box.addItem(p.code, p.id)
            code_box.setCurrentIndex(code_box.findData(rule.project_id))
            code_box.activated.connect(
                lambda _, r=rule, box=code_box: self._save_rule(r.pattern, box.currentData(), r.category))
            self._rule_table.setCellWidget(row, 1, code_box)

            letter_box = QComboBox()
            letter_box.addItems(LETTERS)
            letter_box.setCurrentText(rule.category)
            letter_box.activated.connect(
                lambda _, r=rule, box=letter_box: self._save_rule(r.pattern, r.project_id, box.currentText()))
            self._rule_table.setCellWidget(row, 2, letter_box)

            del_btn = QPushButton("✕")
            del_btn.setToolTip("Delete rule")
            del_btn.clicked.connect(lambda _, r=rule: self._delete_rule(r.id))
            self._rule_table.setCellWidget(row, 3, del_btn)
        self._rule_table.blockSignals(False)

    def _save_rule(self, pattern: str, project_id: int, category: str) -> None:
        models.upsert_rule(pattern, project_id, category)
        self._populate_rules()

    def _delete_rule(self, rule_id: int) -> None:
        models.delete_rule(rule_id)
        self._populate_rules()

    def _on_rule_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        rule_id = item.data(Qt.ItemDataRole.UserRole)
        rule = next((r for r in models.get_rules() if r.id == rule_id), None)
        new_pattern = item.text().strip().lower()
        if rule and new_pattern and new_pattern != rule.pattern:
            models.delete_rule(rule.id)
            models.upsert_rule(new_pattern, rule.project_id, rule.category)
        QTimer.singleShot(0, self._populate_rules)

    def _add_rule(self) -> None:
        projects = models.get_recent_projects()
        if not projects:
            QMessageBox.information(self, "Title rules", "Add a project first.")
            return
        text, ok = QInputDialog.getText(self, "New title rule", "Title contains:")
        if ok and text.strip():
            models.upsert_rule(text, projects[0].id, "A")
            self._populate_rules()

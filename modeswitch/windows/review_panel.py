"""
ReviewPanel — opens beside the ribbon, on the side away from the screen edge.

Top:    one editable timeline per past working day, this week and last week,
        oldest on the left; "Earlier" adds another week. Today is left out, because
        it is already on the ribbon. Each week sits in its own block, alternate weeks
        shaded, with a line between weeks.
Bottom: the projects table (with Lunch and Commute, for their colours; ⤷ on a
        project shows its subtasks) and Settings, and the tracker chart: credit, or
        time on one project, lunch or commute.
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QScreen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QMessageBox, QGroupBox, QToolButton, QInputDialog
)

from modeswitch import days, theme as theme_mod
from modeswitch.day_model import WORK, LUNCH, COMMUTE
from modeswitch.db import models
from modeswitch.theme import current as theme
from modeswitch.timeutil import fmt_duration, fmt_signed
from modeswitch.widgets.credit_chart import ChartDay, CreditChart
from modeswitch.widgets.day_timeline import DayTimeline, RIBBON_WIDTH
from modeswitch.widgets.house_button import HouseButton
from modeswitch.widgets.icon_buttons import SandwichButton, SunButton
from modeswitch.windows.ribbon import summary_text

TABLES_HEIGHT = 250
COLUMN_GAP = 8
WEEK_GAP = 6
KIND_ROWS = [(LUNCH, "Lunch"), (COMMUTE, "Commute")]   # fixed rows in the projects table
# Projects table columns
COL_ARROW, COL_CODE, COL_NAME, COL_COLOUR, COL_DELETE = range(5)


class DayColumn(QWidget):
    """Header, timeline, totals and time per project for one day."""
    changed = pyqtSignal()

    def __init__(self, day_date: date, parent=None):
        super().__init__(parent)
        self.day_date = day_date
        self.date_str = day_date.isoformat()
        self.setFixedWidth(RIBBON_WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
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
        label.setProperty("role", "muted")
        label.setStyleSheet("font-size: 11px;")
        header.addWidget(label, stretch=1)
        self._holiday_btn = SunButton(size=20)
        self._holiday_btn.clicked.connect(self._on_holiday_clicked)
        header.addWidget(self._holiday_btn)
        root.addLayout(header)

        self.timeline = DayTimeline()
        self.timeline.meeting_edges = False
        self.timeline.changed.connect(self._on_timeline_changed)
        root.addWidget(self.timeline, stretch=1)

        self._placeholder = QWidget()
        ph = QVBoxLayout(self._placeholder)
        self._placeholder_label = QLabel()
        self._placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder_label.setProperty("role", "faint")
        self._add_btn = QPushButton("Add day")
        self._add_btn.setToolTip("Start a timeline for this day from your usual hours")
        self._add_btn.clicked.connect(self._on_add_day)
        ph.addStretch()
        ph.addWidget(self._placeholder_label)
        ph.addWidget(self._add_btn)
        ph.addStretch()
        root.addWidget(self._placeholder, stretch=1)

        self._totals = QLabel()
        self._totals.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._totals.setProperty("role", "muted")
        self._totals.setStyleSheet("font-size: 11px;")
        root.addWidget(self._totals)

        self._summary = QLabel()
        self._summary.setFont(QFont("Consolas", 8))
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        self._summary.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
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
            credit = model.credit(self.timeline.target())
            color = theme.credit if credit >= 0 else theme.debit
            self._totals.setText(
                f"{fmt_duration(model.worked_minutes())}  "
                f"<span style='color:{color}'>{fmt_signed(credit)}</span>")
            self._summary.setText(summary_text(self.timeline))
        else:
            self._totals.setText("-")
            self._summary.setText("")

    def summary_height(self) -> int:
        return self._summary.sizeHint().height() if self._summary.text() else 0

    def set_summary_height(self, height: int) -> None:
        """Every column reserves the same space, so the timelines stay level."""
        self._summary.setFixedHeight(height)

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
        self._week_frames: list[QWidget] = []
        self._from_right = 0       # how far the day strip is scrolled back from today
        self._rebuilding = False
        self._expanded: set[int] = set()   # projects showing their subtasks
        self._build_ui()
        theme_mod.hub().projects_changed.connect(self._on_projects_changed_elsewhere)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        bar = QHBoxLayout()
        earlier = QPushButton("◀ Earlier")
        earlier.setToolTip("Load the week before the oldest one shown")
        earlier.clicked.connect(self._show_earlier)
        bar.addWidget(earlier)
        bar.addStretch()
        title = QLabel("Review")
        title.setProperty("role", "muted")
        title.setStyleSheet("font-size: 13px;")
        bar.addWidget(title)
        bar.addStretch()
        close = QPushButton("Close")
        close.setToolTip("Close the review panel")
        close.clicked.connect(self.hide)
        bar.addWidget(close)
        root.addLayout(bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._days_widget = QWidget()
        self._days_layout = QHBoxLayout(self._days_widget)
        self._days_layout.setContentsMargins(0, 0, 0, 0)
        self._days_layout.setSpacing(WEEK_GAP)
        self._scroll.setWidget(self._days_widget)
        bar_h = self._scroll.horizontalScrollBar()
        bar_h.rangeChanged.connect(self._on_scroll_range)
        bar_h.valueChanged.connect(self._on_scroll_value)
        root.addWidget(self._scroll, stretch=1)

        tables = QHBoxLayout()
        tables.addWidget(self._build_projects_group(), stretch=2)
        tables.addWidget(self._build_chart_group(), stretch=3)
        holder = QWidget()
        holder.setLayout(tables)
        tables.setContentsMargins(0, 0, 0, 0)
        holder.setFixedHeight(TABLES_HEIGHT)
        root.addWidget(holder)

    def _build_projects_group(self) -> QGroupBox:
        group = QGroupBox("Projects")
        vbox = QVBoxLayout(group)
        self._proj_table = QTableWidget()
        self._proj_table.setColumnCount(5)
        self._proj_table.setHorizontalHeaderLabels(["", "Code", "Name", "Colour", ""])
        self._proj_table.horizontalHeader().setSectionResizeMode(
            COL_NAME, QHeaderView.ResizeMode.Stretch)
        self._proj_table.verticalHeader().setVisible(False)
        self._proj_table.setColumnWidth(COL_ARROW, 26)
        self._proj_table.setColumnWidth(COL_CODE, 60)
        self._proj_table.setColumnWidth(COL_COLOUR, 60)
        self._proj_table.setColumnWidth(COL_DELETE, 30)
        self._proj_table.itemChanged.connect(self._on_project_item_changed)
        vbox.addWidget(self._proj_table)
        buttons = QHBoxLayout()
        add = QPushButton("+ Add project")
        add.setToolTip("Add a project code that sections can be assigned to")
        add.clicked.connect(self._add_project)
        buttons.addWidget(add)
        settings = QPushButton("⚙ Settings")
        settings.setToolTip("Theme, working week, hours, lunch, commute and snapping")
        settings.clicked.connect(self._open_settings)
        buttons.addWidget(settings)
        buttons.addStretch()
        vbox.addLayout(buttons)
        return group

    def _build_chart_group(self) -> QGroupBox:
        group = QGroupBox("Tracker")
        vbox = QVBoxLayout(group)
        row = QHBoxLayout()
        label = QLabel("Track")
        label.setProperty("role", "muted")
        row.addWidget(label)
        self._series = QComboBox()
        self._series.setToolTip("What the chart plots: your hours credit, or time on one"
                                " project, lunch or commute")
        self._series.activated.connect(self._on_series_chosen)
        row.addWidget(self._series)
        self._series_hint = QLabel()
        self._series_hint.setProperty("role", "faint")
        row.addWidget(self._series_hint, stretch=1)
        vbox.addLayout(row)
        self._chart = CreditChart()
        vbox.addWidget(self._chart, stretch=1)
        return group

    def place_beside(self, ribbon_geometry: QRect, screen: QScreen, edge: str) -> None:
        """Fill the space beside the ribbon, as wide as the days need."""
        area = screen.availableGeometry()
        weeks = len({d.isocalendar()[:2] for d in self._visible_dates()})
        wanted = (len(self._visible_dates()) * (RIBBON_WIDTH + COLUMN_GAP)
                  + weeks * (WEEK_GAP + 12) + 24)
        if edge == "right":
            width = max(720, min(wanted, ribbon_geometry.left() - area.left()))
            left = ribbon_geometry.left() - width
        else:
            width = max(720, min(wanted, area.right() - ribbon_geometry.right()))
            left = ribbon_geometry.right() + 1
        self.setGeometry(left, ribbon_geometry.top(), width, ribbon_geometry.height())

    def _open_settings(self) -> None:
        from modeswitch.windows.settings_dialog import SettingsDialog
        SettingsDialog(self).exec()   # announces its own changes on the hub

    # ------------------------------------------------------------------
    # Day columns, grouped by week
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
        for w in self._week_frames:
            w.setParent(None)
            w.deleteLater()
        self._columns, self._week_frames = [], []
        while self._days_layout.count():
            self._days_layout.takeAt(0)

        weeks: dict[tuple[int, int], list[date]] = {}
        for d in self._visible_dates():
            weeks.setdefault(d.isocalendar()[:2], []).append(d)

        self._days_layout.addStretch()
        # Shade alternate weeks, counting back from the newest so it stays plain
        for n, (_, dates) in enumerate(reversed(list(weeks.items()))):
            frame = QFrame()
            frame.setObjectName("weekAlt" if n % 2 else "week")
            layout = QHBoxLayout(frame)
            layout.setContentsMargins(6, 0, 6, 0)
            layout.setSpacing(COLUMN_GAP)
            for d in dates:
                col = DayColumn(d)
                col.changed.connect(self._on_day_changed)
                self._columns.append(col)
                layout.addWidget(col)
            self._week_frames.insert(0, frame)
        self._columns.sort(key=lambda c: c.day_date)
        for k, frame in enumerate(list(self._week_frames)):
            if k:
                line = QFrame()
                line.setObjectName("weekSeparator")
                line.setFixedWidth(1)
                self._week_frames.append(line)   # so the next refresh removes it
                self._days_layout.addWidget(line)
            self._days_layout.addWidget(frame)

        self._sync_ranges()
        self._populate_projects()
        self._populate_series()
        self._update_chart()

    def _show_earlier(self) -> None:
        self._weeks_back += 1
        self.refresh()

    def _sync_ranges(self) -> None:
        """Put every day on the same time scale so they line up side by side."""
        height = max((c.summary_height() for c in self._columns), default=0)
        for col in self._columns:
            col.set_summary_height(height)
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

    # ------------------------------------------------------------------
    # Tracker chart
    # ------------------------------------------------------------------
    def _populate_series(self) -> None:
        chosen = models.get_setting("chart_series", "credit")
        self._series.blockSignals(True)
        self._series.clear()
        self._series.addItem("Credit", "credit")
        self._series.addItem("Lunch", LUNCH)
        self._series.addItem("Commute", COMMUTE)
        for proj in models.get_all_projects():
            self._series.addItem(f"{proj.code}  {proj.name}", f"p:{proj.id}")
        index = self._series.findData(chosen)
        self._series.setCurrentIndex(index if index >= 0 else 0)
        self._series.blockSignals(False)

    def _on_series_chosen(self, _index: int) -> None:
        models.set_setting("chart_series", self._series.currentData())
        self._update_chart()

    def _update_chart(self) -> None:
        series = self._series.currentData() or "credit"
        kind_colors = days.kind_colors()
        lunch_target = models.get_int_setting("lunch_minutes", 60)
        project = None
        if series.startswith("p:"):
            pid = int(series[2:])
            project = next((p for p in models.get_all_projects() if p.id == pid), None)

        rows = []
        for col in self._columns:
            if not col.has_timeline():
                day = models.get_day(col.date_str)
                rows.append(ChartDay(col.day_date, None, None,
                                     "Holiday" if day and day.is_holiday else "No data"))
                continue
            model = col.timeline.model
            if series == "credit":
                rows.append(ChartDay(col.day_date, model.worked_minutes(), col.timeline.target()))
            elif series in (LUNCH, COMMUTE):
                mins = sum(s.duration for s in model.sections if s.kind == series)
                rows.append(ChartDay(col.day_date, mins,
                                     lunch_target if series == LUNCH else None))
            else:
                mins = sum(s.duration for s in model.sections
                           if s.kind == WORK and project and s.project_id == project.id)
                rows.append(ChartDay(col.day_date, mins))

        if series == "credit":
            self._chart.set_series(rows, "credit")
            self._series_hint.setText("hours worked (dashed) against the nominal day (solid)")
        elif series in (LUNCH, COMMUTE):
            self._chart.set_series(rows, "total", kind_colors[series], series)
            self._series_hint.setText(f"{series} each day"
                                      + (" against the usual lunch" if series == LUNCH else ""))
        else:
            code = project.code if project else "?"
            self._chart.set_series(rows, "total", project.color if project else None,
                                   f"on {code}")
            self._series_hint.setText(f"time on {code} each day")

    # ------------------------------------------------------------------
    # Projects table (Lunch and Commute first: colour only, cannot be deleted)
    # ------------------------------------------------------------------
    def _populate_projects(self) -> None:
        scroll = self._proj_table.verticalScrollBar().value()
        self._proj_table.blockSignals(True)
        self._proj_table.setRowCount(0)
        kind_colors = days.kind_colors()
        for kind, name in KIND_ROWS:
            row = self._add_row(kind, "—", name)
            for c in (COL_CODE, COL_NAME):
                self._fix_item(row, c)
            self._colour_button(row, kind_colors[kind], lambda _, k=kind: self._pick_kind_color(k))
        subtasks: dict[int, list] = {}
        for sub in models.get_subtasks():
            subtasks.setdefault(sub.project_id, []).append(sub)
        for proj in models.get_all_projects():
            row = self._add_row(proj.id, proj.code, proj.name)
            self._arrow_button(row, proj, len(subtasks.get(proj.id, [])))
            self._colour_button(row, proj.color, lambda _, p=proj: self._pick_color(p))
            self._delete_button(row, "Delete this project",
                                lambda _, p=proj: self._delete_project(p))
            if proj.id in self._expanded:
                for sub in subtasks.get(proj.id, []):
                    row = self._add_row(f"sub:{sub.id}", "⤷", sub.name)
                    self._fix_item(row, COL_CODE)
                    self._delete_button(row, "Delete this subtask",
                                        lambda _, s=sub, p=proj: self._delete_subtask(s, p))
                row = self._add_row(f"add:{proj.id}", "", "")
                for c in (COL_CODE, COL_NAME):
                    self._fix_item(row, c)
                add = QPushButton("+ Add subtask")
                add.setToolTip(f"Add a subtask to {proj.code}")
                add.setStyleSheet("text-align: left; padding: 2px 6px;")
                add.clicked.connect(lambda _, p=proj: self._add_subtask(p))
                self._proj_table.setCellWidget(row, COL_NAME, add)
        self._proj_table.blockSignals(False)
        self._proj_table.verticalScrollBar().setValue(scroll)

    def _add_row(self, key, code: str, name: str) -> int:
        row = self._proj_table.rowCount()
        self._proj_table.insertRow(row)
        code_item = QTableWidgetItem(code)
        code_item.setData(Qt.ItemDataRole.UserRole, key)
        self._proj_table.setItem(row, COL_CODE, code_item)
        self._proj_table.setItem(row, COL_NAME, QTableWidgetItem(name))
        return row

    def _fix_item(self, row: int, col: int) -> None:
        """Not editable, and muted."""
        item = self._proj_table.item(row, col)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setForeground(theme.q("muted"))

    def _colour_button(self, row: int, color: str, on_click) -> None:
        b = QPushButton()
        b.setStyleSheet(f"background: {color}; border: none; border-radius: 3px;")
        b.setToolTip("Change colour")
        b.clicked.connect(on_click)
        self._proj_table.setCellWidget(row, COL_COLOUR, b)

    def _delete_button(self, row: int, tip: str, on_click) -> None:
        b = QPushButton("✕")
        b.setToolTip(tip)
        b.clicked.connect(on_click)
        self._proj_table.setCellWidget(row, COL_DELETE, b)

    def _arrow_button(self, row: int, proj, count: int) -> None:
        b = QToolButton()
        b.setText("⤷")
        b.setCheckable(True)
        b.setChecked(proj.id in self._expanded)
        b.setAutoRaise(True)
        b.setStyleSheet(f"QToolButton {{ border: none; background: transparent; font-size: 13px;"
                        f" color: {theme.text if count else theme.faint}; }}"
                        f"QToolButton:checked {{ color: {theme.accent}; }}")
        noun = "subtask" if count == 1 else "subtasks"
        b.setToolTip((f"Hide {proj.code}'s subtasks" if proj.id in self._expanded
                      else f"Show {proj.code}'s subtasks ({count} {noun})"))
        b.toggled.connect(lambda on, p=proj: self._toggle_subtasks(p.id, on))
        self._proj_table.setCellWidget(row, COL_ARROW, b)

    def _toggle_subtasks(self, project_id: int, on: bool) -> None:
        if on:
            self._expanded.add(project_id)
        else:
            self._expanded.discard(project_id)
        # Rebuild after the click has finished with the button
        QTimer.singleShot(0, self._populate_projects)

    def _on_projects_changed_elsewhere(self) -> None:
        """A project or subtask was added on a timeline."""
        self._populate_projects()
        self._populate_series()

    def _projects_edited(self) -> None:
        self._populate_projects()
        self._populate_series()
        self._reload_all()
        self.data_changed.emit()

    def _on_project_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        pid = self._proj_table.item(row, COL_CODE).data(Qt.ItemDataRole.UserRole)
        text = item.text().strip()
        if isinstance(pid, str) and pid.startswith("sub:"):
            if text and not models.rename_subtask(int(pid[4:]), text):
                QMessageBox.warning(self, "Subtask", "This project already has a subtask by that name.")
            QTimer.singleShot(0, self._projects_edited)
            return
        if not isinstance(pid, int):
            return   # Lunch and Commute rows
        if item.column() == COL_CODE:
            code = text.upper()
            taken = {p.code for p in models.get_all_projects() if p.id != pid}
            if not code or len(code) > 4 or code in taken:
                QMessageBox.warning(self, "Project code",
                                    "The code must be 1 to 4 characters and not already in use.")
            else:
                models.update_project(pid, code=code)
        elif item.column() == COL_NAME and text:
            models.update_project(pid, name=text)
        # Rebuild once the table has finished committing the edit
        QTimer.singleShot(0, self._projects_edited)

    def _pick_color(self, proj) -> None:
        from modeswitch.dialogs.colour_picker import pick_colour
        color = pick_colour(self, proj.color, f"Colour for {proj.code}")
        if color:
            models.update_project(proj.id, color=color)
            self._projects_edited()

    def _pick_kind_color(self, kind: str) -> None:
        from modeswitch.dialogs.colour_picker import pick_colour
        color = pick_colour(self, days.kind_colors()[kind], f"Colour for {kind}")
        if color:
            models.set_setting(f"{kind}_color", color)
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

    def _add_subtask(self, proj) -> None:
        name, ok = QInputDialog.getText(self, "New subtask", f"Subtask of {proj.code} {proj.name}:")
        if ok and name.strip():
            models.get_or_create_subtask(proj.id, name.strip())
            self._projects_edited()

    def _delete_subtask(self, sub, proj) -> None:
        reply = QMessageBox.question(
            self, "Delete Subtask",
            f"Delete the subtask \"{sub.name}\" from {proj.code}?\n"
            "Time already logged against it stays on the project.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            models.delete_subtask(sub.id)
            self._projects_edited()

    def _add_project(self) -> None:
        from modeswitch.dialogs.add_project import AddProjectDialog
        if AddProjectDialog(self).exec():
            self._projects_edited()

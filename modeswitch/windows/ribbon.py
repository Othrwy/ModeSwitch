"""
RibbonWindow — the narrow always-on-top strip down the left or right edge of a monitor:
  • house button (working from home) and today's date
  • today's timeline
  • time left / credit
  • time per project
  • Review button
The minimise button collapses it to just the slider; clicking the slider expands it.
The button reaches right up into the top corner, and the outermost column of pixels
down the screen edge toggles it too, so it can be hit by throwing the mouse there.

It registers as a Windows app bar, so it reserves its strip of the screen and other
windows snap to it rather than sliding underneath. Drag the header to move it to
another edge or monitor; it snaps to the nearest left or right edge.
"""
from __future__ import annotations

from ctypes import wintypes
from datetime import date, datetime
from html import escape
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QRect, QPoint, QEvent
from PyQt6.QtGui import QFont, QScreen
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QToolButton, QRubberBand
)

from modeswitch import days
from modeswitch.theme import current as theme
from modeswitch.appbar import (
    AppBar, monitor_rects, CALLBACK_MSG, TASKBAR_CREATED_MSG, ABN_POSCHANGED, ABN_FULLSCREENAPP,
)
from modeswitch.db import models
from modeswitch.system_times import first_on_time
from modeswitch.timeutil import fmt_duration, fmt_signed, now_min, to_hhmm
from modeswitch.widgets.day_timeline import DayTimeline, RIBBON_WIDTH, COMPACT_WIDTH
from modeswitch.widgets.house_button import HouseButton
from modeswitch.widgets.icon_buttons import SandwichButton


def summary_text(timeline: DayTimeline, subtasks: bool = True) -> str:
    """One row per project, '✦ 0000 | 2h 35m', as an HTML table, the ✦ in the
    project's colour. Under it, a '⤷ name | 1h 20m' row for each subtask worked on;
    time on the project with no subtask is only in the project's total."""
    projects: dict = {}   # project_id -> [total, [(subtask_id, minutes)]]
    for project_id, subtask_id, minutes in timeline.model.summary():
        entry = projects.setdefault(project_id, [0, []])
        entry[0] += minutes
        if subtask_id is not None and subtasks:
            entry[1].append((subtask_id, minutes))
    if not projects:
        return ""
    bar = f"<td style='color:{theme.faint}'>&nbsp;|&nbsp;</td>"
    html = []
    for project_id, (total, subs) in sorted(projects.items(),
                                            key=lambda kv: (kv[0] is None, -kv[1][0])):
        proj = timeline.projects.get(project_id) if project_id else None
        color = proj.color if proj else theme.track
        html.append(f"<tr><td style='color:{color}'>✦&nbsp;</td>"
                    f"<td>{proj.code if proj else '----'}</td>{bar}"
                    f"<td align='right'>{fmt_duration(total)}</td></tr>")
        for subtask_id, minutes in sorted(subs, key=lambda r: -r[1]):
            sub = timeline.subtasks.get(subtask_id)
            name = escape(_shorten(sub.name if sub else "?", SUBTASK_CHARS))
            html.append(f"<tr style='color:{theme.muted}'><td></td>"
                        f"<td>⤷&nbsp;{name}</td>{bar}"
                        f"<td align='right'>{fmt_duration(minutes)}</td></tr>")
    return f"<table align='center' cellspacing='0' cellpadding='0'>{''.join(html)}</table>"


SUBTASK_CHARS = 9   # what fits in the ribbon's summary beside the time


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


class RibbonWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ModeSwitch")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self._today = ""
        self._review = None
        self._collapsed = False
        self._appbar: Optional[AppBar] = None
        self._docked_on = None          # (monitor rect, edge) the app bar was last given
        self._drag_offset: Optional[QPoint] = None
        self._drag_start = QPoint()
        self._dragging = False
        self._drop_preview = QRubberBand(QRubberBand.Shape.Rectangle)

        self._build_ui()
        # Clicks on the outermost pixel column are caught on the native window, before
        # Qt picks a widget: it never hands clicks to a widget only 1px wide
        self.winId()
        self.windowHandle().installEventFilter(self)
        QApplication.instance().screenAdded.connect(self._on_screens_changed)
        QApplication.instance().screenRemoved.connect(self._on_screens_changed)
        self.set_collapsed(models.get_setting("ribbon_collapsed", "0") == "1")
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

        self._header = QWidget()
        self._header.setCursor(Qt.CursorShape.OpenHandCursor)
        self._header.setToolTip("Drag to move to another edge or monitor")
        self._header.installEventFilter(self)
        header = QHBoxLayout(self._header)
        header.setContentsMargins(6, 0, 6, 0)
        self._house = HouseButton()
        self._house.toggled.connect(self._on_house_toggled)
        header.addWidget(self._house)
        self._lunch = SandwichButton()
        self._lunch.toggled.connect(lambda on: self.timeline.set_lunch(on))
        header.addWidget(self._lunch)
        self._date_label = QLabel()
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._date_label.setProperty("role", "muted")
        self._date_label.setStyleSheet("font-size: 11px;")
        header.addWidget(self._date_label, stretch=1)
        self._collapse_btn = QToolButton()
        self._collapse_btn.setFixedSize(20, 20)
        self._collapse_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self._collapse_btn.setToolTip("Minimise to just the slider. Click the slider to expand it again")
        self._collapse_btn.clicked.connect(lambda: self.set_collapsed(True))
        header.addWidget(self._collapse_btn)
        root.addWidget(self._header)

        self.timeline = DayTimeline()
        self.timeline.changed.connect(self._on_timeline_changed)
        self.timeline.clicked_compact.connect(lambda: self.set_collapsed(False))
        root.addWidget(self.timeline, stretch=1)

        self._divider_line = self._divider()
        root.addWidget(self._divider_line)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status_label)

        self._summary_label = QLabel("")
        self._summary_label.setFont(QFont("Consolas", 8))
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._summary_label.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self._summary_label)

        self._review_btn = QPushButton("Review")
        self._review_btn.setCheckable(True)
        self._review_btn.setToolTip("Open or close past days, projects and the tracker")
        self._review_btn.clicked.connect(self._toggle_review)
        self._btn_holder = QWidget()
        btn_row = QHBoxLayout(self._btn_holder)
        btn_row.setContentsMargins(6, 2, 6, 0)
        btn_row.addWidget(self._review_btn)
        root.addWidget(self._btn_holder)

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        return line

    # ------------------------------------------------------------------
    # Docking
    # ------------------------------------------------------------------
    def dock_edge(self) -> str:
        return "left" if models.get_setting("dock_edge", "right") == "left" else "right"

    def dock_screen(self) -> QScreen:
        name = models.get_setting("dock_screen", "")
        return next((s for s in QApplication.screens() if s.name() == name),
                    QApplication.primaryScreen())

    def place(self) -> None:
        """Dock to the chosen edge of the chosen monitor, full height, reserving the space."""
        width = COMPACT_WIDTH if self._collapsed else RIBBON_WIDTH
        edge = self.dock_edge()
        self._review_btn.setText("◀  Review" if edge == "right" else "Review  ▶")
        self._collapse_btn.setText("→" if edge == "right" else "←")   # into the screen edge
        self.timeline.set_edge(edge)
        self.setFixedWidth(width)
        if not self.isVisible():
            return   # showEvent places it

        screen = self.dock_screen()
        geo, dpr = screen.geometry(), screen.devicePixelRatio()
        # Qt keeps each screen's top-left in physical pixels and scales only its size
        mon, work = monitor_rects(geo.left(), geo.top())
        target = (mon[0], work[1], mon[2], work[3])
        native_w = round(width * dpr)

        rc = None
        if QApplication.platformName() == "windows":
            if self._appbar is None:
                self._appbar = AppBar(int(self.winId()))
            if self._docked_on and self._docked_on != (mon, edge):
                self._appbar.remove()     # moving monitor or edge: register afresh
            rc = self._appbar.dock(target, edge, native_w)
            self._docked_on = (mon, edge) if rc else None
            if rc is None:
                QTimer.singleShot(5000, self.place)   # at login the shell may not be up yet
        if rc is None:   # not on Windows, or the shell is not ready yet: just float there
            left = target[0] if edge == "left" else target[2] - native_w
            rc = (left, target[1], left + native_w, target[3])

        self.setGeometry(QRect(round(geo.left() + (rc[0] - geo.left()) / dpr),
                               round(geo.top() + (rc[1] - geo.top()) / dpr),
                               width, round((rc[3] - rc[1]) / dpr)))
        if self._review and self._review.isVisible():
            self._review.place_beside(self.geometry(), screen, edge)

    def undock(self) -> None:
        """Give the reserved space back to other windows."""
        if self._appbar:
            self._appbar.remove()
        self._docked_on = None

    def _on_screen_edge(self, x: float) -> bool:
        """Whether a window x is in the single pixel column at the screen edge."""
        return x < 1 if self.dock_edge() == "left" else x >= self.width() - 1

    def _corner_rect(self) -> QRect:
        """The minimise button stretched up and out to the ribbon's top corner, so a
        click anywhere in the margin around it still counts."""
        top_left = self._collapse_btn.mapTo(self, QPoint(0, 0))
        return QRect(QPoint(top_left.x(), 0),
                     QPoint(self.width() - 1, top_left.y() + self._collapse_btn.height() - 1))

    def mousePressEvent(self, event):
        # Only the margins above and below the header and timeline land here
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._collapsed:
            self.set_collapsed(False)
        elif self._corner_rect().contains(event.position().toPoint()):
            self.set_collapsed(True)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.place)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.undock()

    def nativeEvent(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == CALLBACK_MSG and self._appbar:
                if msg.wParam == ABN_POSCHANGED:
                    QTimer.singleShot(0, self.place)
                elif msg.wParam == ABN_FULLSCREENAPP:
                    # Step back while a full-screen app (a presentation) is in front
                    self._appbar.set_topmost(not msg.lParam)
            elif msg.message == TASKBAR_CREATED_MSG and self._appbar:
                # Explorer restarted and forgot every app bar
                self._appbar.registered = False
                self._docked_on = None
                QTimer.singleShot(1000, self.place)
        return False, 0

    def _on_screens_changed(self, _screen) -> None:
        if self.isVisible():
            QTimer.singleShot(500, self.place)

    # ------------------------------------------------------------------
    # Dragging by the header to another edge or monitor
    # ------------------------------------------------------------------
    def _drop_target(self, pos: QPoint) -> tuple[QScreen, str]:
        screen = QApplication.screenAt(pos) or self.screen()
        edge = "left" if pos.x() < screen.geometry().center().x() else "right"
        return screen, edge

    def eventFilter(self, obj, event):
        if obj is self.windowHandle():
            if (event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick)
                    and event.button() == Qt.MouseButton.LeftButton
                    and self._on_screen_edge(event.position().x())):
                self.set_collapsed(not self._collapsed)
                return True
            return False
        if obj is not self._header:
            return super().eventFilter(obj, event)
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if self._corner_rect().contains(self._header.mapTo(self, event.position().toPoint())):
                self.set_collapsed(True)   # the margin beside the minimise button
                return True
            self._drag_start = event.globalPosition().toPoint()
            self._drag_offset = self._drag_start - self.pos()
            return True
        if kind == QEvent.Type.MouseMove and self._drag_offset is not None:
            pos = event.globalPosition().toPoint()
            if not self._dragging:
                if (pos - self._drag_start).manhattanLength() < QApplication.startDragDistance():
                    return True
                self._dragging = True
                self._header.setCursor(Qt.CursorShape.ClosedHandCursor)
                if self._review:
                    self._review.hide()
                    self._review_btn.setChecked(False)
            self.move(pos - self._drag_offset)
            screen, edge = self._drop_target(pos)
            area = screen.availableGeometry()
            left = area.left() if edge == "left" else area.right() - self.width() + 1
            self._drop_preview.setGeometry(left, area.top(), self.width(), area.height())
            self._drop_preview.show()
            return True
        if kind == QEvent.Type.MouseButtonRelease and self._drag_offset is not None:
            self._drag_offset = None
            if self._dragging:
                self._dragging = False
                self._drop_preview.hide()
                self._header.setCursor(Qt.CursorShape.OpenHandCursor)
                screen, edge = self._drop_target(event.globalPosition().toPoint())
                models.set_setting("dock_screen", screen.name())
                models.set_setting("dock_edge", edge)
                self.place()
            return True
        return super().eventFilter(obj, event)

    def set_collapsed(self, collapsed: bool) -> None:
        """Shrink to just the slider, or back to the full ribbon."""
        self._collapsed = collapsed
        models.set_setting("ribbon_collapsed", "1" if collapsed else "0")
        if collapsed and self._review:
            self._review.hide()
            self._review_btn.setChecked(False)
        for w in (self._header, self._divider_line, self._status_label,
                  self._summary_label, self._btn_holder):
            w.setVisible(not collapsed)
        self.timeline.set_compact(collapsed)
        self.place()

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
        self.timeline.load(day)
        self._sync_header_buttons()
        self._refresh_readouts()

    def _sync_header_buttons(self) -> None:
        for button, checked in ((self._house, self.timeline.day.wfh),
                                (self._lunch, self.timeline.model.has_lunch())):
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)

    def _tick(self) -> None:
        if date.today().isoformat() != self._today:
            self.open_today()
            return
        models.update_day(self.timeline.day.id, last_seen=datetime.now().strftime("%H:%M"))
        self.timeline.refresh_meetings()
        self._refresh_readouts()

    # ------------------------------------------------------------------
    # Readouts
    # ------------------------------------------------------------------
    def _refresh_readouts(self) -> None:
        self._summary_label.setText(summary_text(self.timeline))
        day, model = self.timeline.day, self.timeline.model

        left = model.work_end - now_min()
        following = day.out_source in ("computed", "manual")
        credit = model.credit(self.timeline.target())
        if following and left > 0:
            text, color = f"time left: {fmt_duration(left)}", theme.muted
        elif following and credit >= 0:
            # The end is following the clock, so this grows as you work
            text, color = f"overtime: +{fmt_duration(credit)}", theme.credit
        else:
            credit = model.credit(self.timeline.target())
            text = f"credit: {fmt_signed(credit)}"
            color = theme.credit if credit >= 0 else theme.debit
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
        if self._collapsed:
            self.set_collapsed(False)
        if self._review is None:
            self._review = ReviewPanel()
            self._review.data_changed.connect(self._on_review_changed)
        self._review.reset_view()
        self._review.place_beside(self.geometry(), self.dock_screen(), self.dock_edge())
        self._review.refresh()
        self._review.show()
        self._review.raise_()
        self._review_btn.setChecked(True)

    def on_meetings_synced(self, changed: list[str]) -> None:
        self.timeline.refresh_meetings()
        if self._review and self._review.isVisible():
            for date_str in changed:
                self._review.reload_day(date_str)

    def on_settings_changed(self) -> None:
        """Theme, working days, day lengths or colours changed."""
        self.timeline.reload()
        self._sync_header_buttons()
        self._refresh_readouts()
        self.update()
        for w in self.findChildren(QWidget):
            w.update()
        if self._review:
            self._review.refresh()

    def _on_review_changed(self) -> None:
        """Something was edited in the review panel; pick up today's changes."""
        self.timeline.reload()
        self._sync_header_buttons()
        self._refresh_readouts()

    # ------------------------------------------------------------------
    # Leaving for the day
    # ------------------------------------------------------------------
    def end_time_is_set(self) -> bool:
        return self.timeline.day.out_source == "held"

    def save_out_time(self) -> None:
        self.timeline.set_end_now()

"""
QApplication + QSystemTrayIcon wrapper.
"""
from __future__ import annotations

import queue
import sys
import threading
from datetime import datetime

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox
)

from modeswitch import calendar_sync, days
from modeswitch.db.schema import init_db
from modeswitch.timeutil import now_min, to_hhmm
from modeswitch.windows.ribbon import RibbonWindow


def _make_default_icon() -> QIcon:
    """Create a simple coloured square icon for the tray."""
    px = QPixmap(16, 16)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setBrush(QColor("#4CAF50"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(1, 1, 14, 14, 3, 3)
    p.end()
    return QIcon(px)


SYNC_INTERVAL_MS = 5 * 60_000


class CalendarSyncer(QObject):
    """Fetches meetings on a background thread and stores them on the main one.

    One long-lived worker thread does every fetch, because the COM link to classic
    Outlook belongs to the thread that opened it.
    """
    synced = pyqtSignal(list)                # dates whose meetings changed
    status_changed = pyqtSignal(str, bool)   # text, and whether to pop up a warning
    _fetched = pyqtSignal(str, object, bool)
    _failed = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._jobs: queue.Queue[bool] = queue.Queue()
        self._fetched.connect(self._on_fetched)
        self._failed.connect(self._on_failed)
        threading.Thread(target=self._worker, daemon=True).start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.sync(user_started=False))
        self._timer.start(SYNC_INTERVAL_MS)
        QTimer.singleShot(2000, lambda: self.sync(user_started=False))

    def sync(self, user_started: bool) -> None:
        """user_started: from the tray menu, so report a failure with a pop-up."""
        if self._busy:
            return
        self._busy = True
        self._jobs.put(user_started)

    def _worker(self) -> None:
        outlook = calendar_sync.OutlookReader()
        while True:
            user_started = self._jobs.get()
            try:
                first, last = calendar_sync.sync_range()
                source, by_date = calendar_sync.fetch_meetings(first, last, outlook)
                self._fetched.emit(source, by_date, user_started)
            except Exception as e:
                self._failed.emit(f"Calendar sync failed: {e}", user_started)

    def _on_fetched(self, source: str, by_date, user_started: bool) -> None:
        self._busy = False
        changed = days.store_meetings(by_date)
        self.status_changed.emit(f"Calendar synced from {source} at {datetime.now():%H:%M}",
                                 False)
        if user_started:
            total = sum(len(m) for m in by_date.values())
            self.status_changed.emit(f"Calendar synced from {source}: {total} meetings "
                                     f"since last Monday week", True)
        self.synced.emit(changed)

    def _on_failed(self, message: str, user_started: bool) -> None:
        # Background failures (offline, Outlook busy) only update the tooltip
        self._busy = False
        self.status_changed.emit(message, user_started)


class App:
    def __init__(self):
        self.qapp = QApplication.instance() or QApplication(sys.argv)
        self.qapp.setQuitOnLastWindowClosed(False)
        self.qapp.setApplicationName("ModeSwitch")

        self._apply_stylesheet()

        init_db()

        self.ribbon = RibbonWindow()
        self.ribbon.show()
        self.qapp.aboutToQuit.connect(self.ribbon.undock)

        self._tray = self._build_tray()
        self._tray.show()

        self.calendar = CalendarSyncer(self.qapp)
        self.calendar.synced.connect(self.ribbon.on_meetings_synced)
        self.calendar.status_changed.connect(self._on_calendar_status)

    # ------------------------------------------------------------------
    def _build_tray(self) -> QSystemTrayIcon:
        icon = _make_default_icon()
        tray = QSystemTrayIcon(icon, self.qapp)
        tray.setToolTip("ModeSwitch")

        menu = QMenu()
        show_action = menu.addAction("Show")
        show_action.triggered.connect(self._show_ribbon)

        hide_action = menu.addAction("Hide")
        hide_action.triggered.connect(self._hide_ribbon)

        review_action = menu.addAction("Review")
        review_action.triggered.connect(self._show_review)

        menu.addSeparator()

        sync_action = menu.addAction("Sync calendar now")
        sync_action.triggered.connect(lambda: self.calendar.sync(user_started=True))

        settings_action = menu.addAction("Settings")
        settings_action.triggered.connect(self._open_settings)

        menu.addSeparator()

        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self._exit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        return tray

    def _on_calendar_status(self, text: str, popup: bool) -> None:
        failed = text.startswith("Calendar sync failed")
        if popup:
            icon = (QSystemTrayIcon.MessageIcon.Warning if failed
                    else QSystemTrayIcon.MessageIcon.Information)
            self._tray.showMessage("ModeSwitch", text, icon)
        if failed or not popup:
            self._tray.setToolTip(f"ModeSwitch\n{text}")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_ribbon()

    def _show_ribbon(self) -> None:
        self.ribbon.show()
        self.ribbon.raise_()

    def _hide_ribbon(self) -> None:
        if self.ribbon._review:
            self.ribbon._review.hide()
        self.ribbon.hide()

    def _show_review(self) -> None:
        self._show_ribbon()
        self.ribbon.show_review()

    def _open_settings(self) -> None:
        from modeswitch.windows.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.ribbon)
        dlg.exec()

    def _exit(self) -> None:
        if not self.ribbon.end_time_is_set():
            now = to_hhmm(now_min())
            reply = QMessageBox.question(
                None,
                "Save Out Time",
                f"Save out time as {now}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.ribbon.save_out_time()

        self.qapp.quit()

    # ------------------------------------------------------------------
    def _apply_stylesheet(self) -> None:
        self.qapp.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
            }
            QLineEdit, QSpinBox, QComboBox {
                background: #2d2d2d;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 3px 6px;
                color: #e0e0e0;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #888;
            }
            QPushButton, QToolButton {
                background: #3a3a3a;
                color: #e0e0e0;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QToolButton {
                padding: 0;
            }
            QPushButton:hover, QToolButton:hover {
                background: #4a4a4a;
            }
            QPushButton:pressed, QPushButton:checked, QToolButton:checked {
                background: #555;
            }
            QScrollArea, QScrollBar {
                background: #1e1e1e;
                border: none;
            }
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                color: #aaa;
            }
            QTableWidget {
                background: #252525;
                gridline-color: #333;
            }
            QHeaderView::section {
                background: #2d2d2d;
                color: #aaa;
                border: none;
                padding: 4px;
            }
            QMenu {
                background: #2d2d2d;
                border: 1px solid #555;
            }
            QMenu::item {
                padding: 4px 18px;
            }
            QMenu::item:selected {
                background: #4a4a4a;
            }
            QMenu::item:disabled {
                color: #666;
            }
            QToolTip {
                background: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #555;
            }
        """)

    # ------------------------------------------------------------------
    def run(self) -> int:
        return self.qapp.exec()

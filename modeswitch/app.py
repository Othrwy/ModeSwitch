"""
QApplication + QSystemTrayIcon wrapper.
"""
from __future__ import annotations

import queue
import sys
import threading
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox
)

from modeswitch import autostart, calendar_sync, days, theme
from modeswitch.app_icon import app_icon
from modeswitch.db import models
from modeswitch.db.schema import init_db
from modeswitch.timeutil import now_min, to_hhmm
from modeswitch.windows.ribbon import RibbonWindow


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
        self._jobs.put((user_started, models.get_setting("outlook_profile", "")))

    def _worker(self) -> None:
        outlook = calendar_sync.OutlookReader()
        while True:
            user_started, profile = self._jobs.get()
            try:
                outlook.use_profile(profile)
                first, last = calendar_sync.sync_range()
                source, by_date = calendar_sync.fetch_meetings(first, last, outlook)
                self._fetched.emit(source, by_date, user_started)
            except Exception as e:
                self._failed.emit(f"Calendar sync failed: {calendar_sync.explain_error(e)}",
                                  user_started)

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
        self.qapp.setWindowIcon(app_icon())

        init_db()
        autostart.migrate_shortcut()
        theme.apply(self.qapp)
        theme.hub().settings_changed.connect(self._on_settings_changed)
        # A brand-new user (nothing logged yet) gets the guide once, on first launch
        show_guide = (models.get_setting("guide_seen", "") != "1"
                      and not models.get_first_logged_date())
        models.set_setting("guide_seen", "1")

        self.ribbon = RibbonWindow()
        self.ribbon.show()
        self.qapp.aboutToQuit.connect(self.ribbon.undock)

        self._tray = self._build_tray()
        self._tray.show()

        self.calendar = CalendarSyncer(self.qapp)
        self.calendar.synced.connect(self.ribbon.on_meetings_synced)
        self.calendar.status_changed.connect(self._on_calendar_status)
        theme.hub().sync_requested.connect(lambda: self.calendar.sync(user_started=True))
        if show_guide:
            QTimer.singleShot(1500, self._show_guide)

    # ------------------------------------------------------------------
    def _build_tray(self) -> QSystemTrayIcon:
        icon = app_icon()
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

        guide_action = menu.addAction("Getting started")
        guide_action.triggered.connect(self._show_guide)

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
        SettingsDialog(self.ribbon).exec()   # announces its own changes on the hub

    def _show_guide(self) -> None:
        from modeswitch.dialogs.guide import GuideDialog
        GuideDialog(self.ribbon).exec()

    def _on_settings_changed(self) -> None:
        theme.apply(self.qapp)
        self.ribbon.on_settings_changed()

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
    def run(self) -> int:
        return self.qapp.exec()

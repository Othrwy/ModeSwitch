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

from modeswitch import autostart, calendar_sync, days, theme, updater
from modeswitch.app_icon import app_icon
from modeswitch.db import models
from modeswitch.db.schema import init_db
from modeswitch.timeutil import now_min, to_hhmm
from modeswitch.windows.ribbon import RibbonWindow


SYNC_INTERVAL_MS = 5 * 60_000
UPDATE_INTERVAL_MS = 6 * 60 * 60_000   # look for a new version every 6 hours


class UpdateChecker(QObject):
    """Looks for a new version on GitHub, and applies it, on a background thread."""
    checked = pyqtSignal(object, bool)   # UpdateInfo or None, and whether the user asked
    failed = pyqtSignal(str, bool)       # message, and whether the user asked
    applied = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.check(user_started=False))
        self._timer.start(UPDATE_INTERVAL_MS)
        QTimer.singleShot(30_000, lambda: self.check(user_started=False))

    def check(self, user_started: bool) -> None:
        self._run(lambda: self.checked.emit(updater.check(), user_started), user_started)

    def apply(self) -> None:
        def job():
            updater.apply()
            self.applied.emit()
        self._run(job, True)

    def _run(self, job, user_started: bool) -> None:
        if self._busy:
            return
        self._busy = True

        def work():
            try:
                job()
            except Exception as e:
                self.failed.emit(str(e), user_started)
            finally:
                self._busy = False
        threading.Thread(target=work, daemon=True).start()


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

        self.restart = False   # set by Refresh: start a fresh copy once this one exits
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
        self._update: updater.UpdateInfo | None = None
        if updater.available():
            self.updates = UpdateChecker(self.qapp)
            self.updates.checked.connect(self._on_update_checked)
            self.updates.failed.connect(self._on_update_failed)
            self.updates.applied.connect(self._refresh)
        if show_guide:
            QTimer.singleShot(1500, self._show_guide)

    # ------------------------------------------------------------------
    def _build_tray(self) -> QSystemTrayIcon:
        icon = app_icon()
        tray = QSystemTrayIcon(icon, self.qapp)
        tray.setToolTip("ModeSwitch")

        menu = QMenu()
        menu.setToolTipsVisible(True)
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

        self._update_action = menu.addAction("Check for updates")
        self._update_action.setToolTip("Look on GitHub for a newer version of ModeSwitch")
        self._update_action.triggered.connect(self._on_update_clicked)
        self._update_action.setVisible(updater.available())

        refresh_action = menu.addAction("Refresh")
        refresh_action.setToolTip("Restart ModeSwitch to pick up changes, without closing"
                                  " it and starting it again by hand")
        refresh_action.triggered.connect(self._refresh)

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

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------
    def _on_update_clicked(self) -> None:
        if self._update and not self._update.blocked:
            self._update_action.setText("Updating…")
            self._update_action.setEnabled(False)
            self.updates.apply()   # restarts when done
        else:
            self.updates.check(user_started=True)

    def _on_update_checked(self, info, user_started: bool) -> None:
        previous, self._update = self._update, info
        if not info:
            self._update_action.setText("Check for updates")
            self._update_action.setToolTip("Look on GitHub for a newer version of ModeSwitch")
            if user_started:
                self._tray.showMessage("ModeSwitch", "ModeSwitch is up to date",
                                       QSystemTrayIcon.MessageIcon.Information)
            return
        noun = "change" if info.behind == 1 else "changes"
        listed = "\n".join(f"• {c}" for c in info.changes[:5])
        if info.behind > 5:
            listed += f"\n…and {info.behind - 5} more"
        if info.blocked:
            self._update_action.setText(f"Update available ({info.behind} {noun})")
            self._update_action.setToolTip(info.blocked)
            if user_started:
                self._tray.showMessage("ModeSwitch", f"{info.blocked}. Run git pull by hand.",
                                       QSystemTrayIcon.MessageIcon.Warning)
            return
        self._update_action.setText(f"Update now ({info.behind} {noun})")
        self._update_action.setToolTip(f"Download the new version and restart:\n{listed}")
        if not user_started and previous and previous.behind == info.behind:
            return   # already announced; the 6-hourly check need not repeat it
        self._tray.showMessage(
            "ModeSwitch update available",
            f"{listed}\n\nRight-click the tray icon and choose Update now.",
            QSystemTrayIcon.MessageIcon.Information)

    def _on_update_failed(self, message: str, user_started: bool) -> None:
        # A background check that fails (offline, signed out of GitHub) stays quiet
        self._update_action.setText("Check for updates")
        self._update_action.setEnabled(True)
        if user_started:
            self._tray.showMessage("ModeSwitch", f"Could not update: {message}",
                                   QSystemTrayIcon.MessageIcon.Warning)

    def _refresh(self) -> None:
        """Close and start again. Nothing is lost: every edit is saved as it is made,
        and the end of day is left as it is, so there is no "Save out time?" question."""
        self.restart = True
        self.qapp.quit()

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

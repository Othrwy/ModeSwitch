"""
Connect to Outlook — a setup page that checks each thing calendar sync needs, says
how to fix what is missing, and tests the connection.

Classic Outlook is the default route: it needs no admin approval. Microsoft Graph is
shown as an optional second route, which works only once IT approves the app.
"""
from __future__ import annotations

import threading
from datetime import date

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
)

from modeswitch import calendar_sync, theme as theme_mod
from modeswitch.db import models
from modeswitch.theme import current as theme

OK, BAD, TODO = "✓", "✗", "○"


class OutlookSetupDialog(QDialog):
    _tested = pyqtSignal(bool, str)       # from the test thread: worked, message
    _graph_done = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Outlook")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._tested.connect(self._on_tested)
        self._graph_done.connect(self._on_graph_done)
        self._build_ui()
        self._check()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = QLabel(
            "ModeSwitch draws your Outlook meetings behind the day's timeline, as a guide "
            "to log your time against. It reads them through <b>classic Outlook</b>, which "
            "is installed alongside the new Outlook app on most work laptops. That needs "
            "no admin approval, and your calendar never leaves your computer.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        steps = QGridLayout()
        steps.setHorizontalSpacing(10)
        steps.setVerticalSpacing(12)
        steps.setColumnStretch(1, 1)
        self._marks = []
        self._bodies = []

        def step(row: int, heading: str) -> QVBoxLayout:
            mark = QLabel(TODO)
            mark.setStyleSheet("font-size: 15px;")
            mark.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            mark.setFixedWidth(18)
            steps.addWidget(mark, row, 0)
            box = QVBoxLayout()
            box.setSpacing(3)
            title = QLabel(f"<b>{heading}</b>")
            box.addWidget(title)
            body = QLabel()
            body.setWordWrap(True)
            body.setProperty("role", "muted")
            body.setTextFormat(Qt.TextFormat.RichText)
            box.addWidget(body)
            steps.addLayout(box, row, 1)
            self._marks.append(mark)
            self._bodies.append(body)
            return box

        step(0, "1. Classic Outlook is installed")
        box = step(1, "2. Classic Outlook has been opened and signed in once")
        row = QHBoxLayout()
        row.addWidget(QLabel("Mail profile"))
        self._profile = QComboBox()
        self._profile.setToolTip("The Outlook mail profile to read the calendar from. "
                                 "Most people only have one")
        self._profile.activated.connect(self._on_profile_chosen)
        row.addWidget(self._profile)
        row.addStretch()
        box.addLayout(row)
        box = step(2, "3. Test the connection")
        row = QHBoxLayout()
        self._test_btn = QPushButton("Test connection")
        self._test_btn.setToolTip("Read today's meetings through classic Outlook")
        self._test_btn.clicked.connect(self._test)
        row.addWidget(self._test_btn)
        self._sync_btn = QPushButton("Sync now")
        self._sync_btn.setToolTip("Fetch meetings from Monday last week to today, and draw them")
        self._sync_btn.clicked.connect(self._sync_now)
        row.addWidget(self._sync_btn)
        row.addStretch()
        box.addLayout(row)
        layout.addLayout(steps)

        about = QLabel(
            "Once connected, ModeSwitch syncs on launch and every 5 minutes, from Monday "
            "last week to today. All-day events, events marked Free, and declined or "
            "cancelled meetings are left out. Classic Outlook stays open in the "
            "background with no window, so its copy of your calendar stays up to date.")
        about.setWordWrap(True)
        about.setProperty("role", "faint")
        layout.addWidget(about)

        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        layout.addWidget(line)

        graph_title = QLabel("<b>Optional: Microsoft Graph</b>")
        layout.addWidget(graph_title)
        self._graph_text = QLabel()
        self._graph_text.setWordWrap(True)
        self._graph_text.setProperty("role", "muted")
        layout.addWidget(self._graph_text)
        row = QHBoxLayout()
        self._graph_btn = QPushButton()
        self._graph_btn.clicked.connect(self._on_graph_clicked)
        row.addWidget(self._graph_btn)
        row.addStretch()
        layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------
    def _set_step(self, k: int, state: str, html: str) -> None:
        color = {OK: theme.credit, BAD: theme.debit, TODO: theme.faint}[state]
        self._marks[k].setText(state)
        self._marks[k].setStyleSheet(f"font-size: 15px; color: {color};")
        self._bodies[k].setText(html)

    def _check(self) -> None:
        """Look at what is installed and set up; no Outlook connection yet."""
        path = calendar_sync.classic_outlook_path()
        if path:
            self._set_step(0, OK, f"Found at {path}")
        else:
            self._set_step(0, BAD,
                "Not found. It comes with Microsoft 365 Apps: look for "
                "<b>Outlook (classic)</b> in the Start menu. If it is not there, install "
                "Microsoft 365 Apps from Company Portal or office.com, or ask IT for "
                "classic Outlook. The new Outlook app on its own cannot be read.")

        names, default = calendar_sync.outlook_profiles()
        chosen = models.get_setting("outlook_profile", "")
        self._profile.clear()
        self._profile.addItem(f"Default ({default})" if default else "Default", "")
        for name in names:
            self._profile.addItem(name, name)
        self._profile.setCurrentIndex(max(0, self._profile.findData(chosen)))
        self._profile.setEnabled(bool(names))
        if names:
            self._set_step(1, OK,
                "A mail profile is set up. If you have more than one, pick the one with "
                "your work calendar.")
        else:
            self._set_step(1, BAD if path else TODO,
                "No mail profile yet. Open <b>Outlook (classic)</b> from the Start menu, "
                "sign in with your work account, and wait until your calendar shows. "
                "Then close it and press <b>Test connection</b>.<br>If it opens the new "
                "Outlook instead, use the <b>New Outlook</b> toggle at its top right to "
                "go back to classic.")
        self._set_step(2, TODO, "Reads today's meetings, to check everything works.")
        self._update_graph()

    def _on_profile_chosen(self, _index: int) -> None:
        models.set_setting("outlook_profile", self._profile.currentData())
        self._set_step(2, TODO, "Profile changed. Test again to check it.")

    def _test(self) -> None:
        self._test_btn.setEnabled(False)
        self._set_step(2, TODO, "Connecting to classic Outlook… the first time can take "
                                "up to a minute while it starts in the background.")
        profile = self._profile.currentData() or ""

        def run():
            try:
                count = calendar_sync.test_outlook(profile)
                self._tested.emit(True, f"Connected. {count} meeting{'s' if count != 1 else ''}"
                                        f" today ({date.today():%a %d %b}).")
            except Exception as e:
                self._tested.emit(False, calendar_sync.explain_error(e))
        threading.Thread(target=run, daemon=True).start()

    def _on_tested(self, worked: bool, message: str) -> None:
        self._test_btn.setEnabled(True)
        if worked:
            message += (" If that looks low, classic Outlook may still be catching up: "
                        "press Sync now again in a minute.")
            theme_mod.hub().sync_requested.emit()
        self._set_step(2, OK if worked else BAD, message)

    def _sync_now(self) -> None:
        theme_mod.hub().sync_requested.emit()   # the tray reports the result
        self._set_step(2, self._marks[2].text(),
                       "Syncing… the result pops up from the tray icon.")

    # ------------------------------------------------------------------
    # Microsoft Graph
    # ------------------------------------------------------------------
    def _update_graph(self) -> None:
        signed_in = calendar_sync.is_signed_in()
        if signed_in:
            self._graph_text.setText(
                "Signed in. ModeSwitch reads your calendar from Microsoft 365 directly "
                "and does not need classic Outlook.")
            self._graph_btn.setText("Sign out")
            self._graph_btn.setToolTip("Go back to reading through classic Outlook")
        else:
            self._graph_text.setText(
                "Reads the calendar straight from Microsoft 365, with no classic Outlook. "
                "It only works once IT has approved the ModeSwitch app for the company; "
                "until then, signing in stops at <i>Need admin approval</i>. Classic "
                "Outlook above does the same job without that.")
            self._graph_text.setTextFormat(Qt.TextFormat.RichText)
            self._graph_btn.setText("Sign in with Microsoft…")
            self._graph_btn.setToolTip("Opens your browser to sign in")
        self._graph_btn.setEnabled(True)

    def _on_graph_clicked(self) -> None:
        if calendar_sync.is_signed_in():
            calendar_sync.sign_out()
            self._update_graph()
            return
        self._graph_btn.setEnabled(False)
        self._graph_text.setText("Finish signing in in your browser…")

        def run():
            try:
                today = date.today()
                calendar_sync.graph_events(today, today, interactive=True)
                self._graph_done.emit(True, "")
            except Exception as e:
                self._graph_done.emit(False, str(e))
        threading.Thread(target=run, daemon=True).start()

    def _on_graph_done(self, worked: bool, message: str) -> None:
        self._update_graph()
        if worked:
            theme_mod.hub().sync_requested.emit()
        else:
            self._graph_text.setText(f"Sign-in did not work: {message}")

"""
Settings dialog — appearance, working week, day length, lunch, commute, startup.
Opened from the tray menu and from the review panel. Projects (and the lunch and
commute colours) are edited in the review panel.

Saving announces the change on theme.hub(), and every window refreshes itself.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QTime, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QSpinBox, QTimeEdit, QToolButton, QVBoxLayout, QWidget
)

from modeswitch import days, theme as theme_mod
from modeswitch.db import models
from modeswitch.theme import current as theme

STARTUP_FOLDER = Path(os.environ.get("APPDATA", "")) / \
    "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
SHORTCUT_NAME = "ModeSwitch.lnk"

DAY_LETTERS = {1: "M", 2: "T", 3: "W", 4: "T", 5: "F", 6: "S", 7: "S"}
DAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
             5: "Friday", 6: "Saturday", 7: "Sunday"}
THEMES = [("dark", "Dark"), ("light", "Light"), ("custom", "Custom")]


def _autostart_enabled() -> bool:
    return (STARTUP_FOLDER / SHORTCUT_NAME).exists()


def create_autostart_shortcut() -> None:
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(STARTUP_FOLDER / SHORTCUT_NAME))
        if getattr(sys, "frozen", False):
            shortcut.Targetpath = sys.executable
            shortcut.WorkingDirectory = str(Path(sys.executable).parent)
        else:
            # pythonw so no console window is left open at login
            exe = Path(sys.executable)
            pythonw = exe.with_name("pythonw.exe")
            project = Path(__file__).parent.parent.parent
            shortcut.Targetpath = str(pythonw if pythonw.exists() else exe)
            shortcut.Arguments = f'"{project / "main.py"}"'
            shortcut.WorkingDirectory = str(project)
        shortcut.save()
    except Exception as e:
        QMessageBox.warning(None, "Autostart", f"Could not create shortcut:\n{e}")


def _remove_autostart_shortcut() -> None:
    path = STARTUP_FOLDER / SHORTCUT_NAME
    if path.exists():
        path.unlink()


def _minutes(t: QTime) -> int:
    return t.hour() * 60 + t.minute()


def _qtime(minutes: int) -> QTime:
    minutes = max(0, min(23 * 60 + 59, minutes))
    return QTime(minutes // 60, minutes % 60)


class DayDots(QWidget):
    """Seven round toggles, M T W T F S S."""
    changed = pyqtSignal()

    def __init__(self, selected: list[int], parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._buttons: dict[int, QToolButton] = {}
        for iso, letter in DAY_LETTERS.items():
            b = QToolButton()
            b.setText(letter)
            b.setToolTip(DAY_NAMES[iso] + " (click to switch on or off)")
            b.setCheckable(True)
            b.setChecked(iso in selected)
            b.setFixedSize(26, 26)
            b.setStyleSheet(
                f"QToolButton {{ border-radius: 13px; border: 1px solid {theme.border};"
                f" background: {theme.surface}; color: {theme.muted}; font-weight: 600; }}"
                f"QToolButton:checked {{ background: {theme.accent}; color: white;"
                f" border: 1px solid {theme.accent}; }}")
            b.toggled.connect(self.changed)
            self._buttons[iso] = b
            row.addWidget(b)
        row.addStretch()

    def selected(self) -> list[int]:
        return [iso for iso, b in self._buttons.items() if b.isChecked()]

    def as_setting(self) -> str:
        return ",".join(str(iso) for iso in self.selected())


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        self.setModal(True)
        try:
            self._custom = json.loads(models.get_setting("theme_custom", "{}")) or {}
        except ValueError:
            self._custom = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Appearance ---
        look = QGroupBox("Appearance")
        row = QHBoxLayout(look)
        self._theme = QComboBox()
        for key, label in THEMES:
            self._theme.addItem(label, key)
        self._theme.setCurrentIndex(self._theme.findData(models.get_setting("theme", "dark")))
        self._theme.setToolTip("Colour scheme for the whole app")
        self._theme.currentIndexChanged.connect(self._on_theme_chosen)
        row.addWidget(self._theme)
        self._edit_colours = QPushButton("Edit colours…")
        self._edit_colours.setToolTip("Pick each colour of the custom theme")
        self._edit_colours.clicked.connect(self._open_colours)
        row.addWidget(self._edit_colours)
        row.addStretch()
        layout.addWidget(look)

        # --- Working week ---
        week = QGroupBox("Working week")
        form = QFormLayout(week)
        self._working = DayDots(models.get_day_list_setting("working_days"))
        self._working.changed.connect(self._update_lengths)
        self._working.setToolTip("Days you are expected to work. Other days count no hours")
        form.addRow("Working days", self._working)
        self._wfh = DayDots(models.get_day_list_setting("wfh_days"))
        self._wfh.setToolTip("Days that start with no commute")
        form.addRow("Work from home", self._wfh)
        layout.addWidget(week)

        # --- Hours ---
        hours = QGroupBox("Hours (not counting lunch)")
        vbox = QVBoxLayout(hours)
        top = QHBoxLayout()
        self._same = QCheckBox("Same length every day")
        self._same.setChecked(models.get_setting("target_same", "1") == "1")
        self._same.setToolTip("Untick to set a different length for each day")
        self._same.toggled.connect(self._update_lengths)
        top.addWidget(self._same)
        self._all_length = QTimeEdit(_qtime(days.target_minutes()))
        self._all_length.setDisplayFormat("H:mm")
        self._all_length.setToolTip("Hours expected each working day")
        top.addWidget(self._all_length)
        top.addStretch()
        vbox.addLayout(top)
        grid = QGridLayout()
        self._day_lengths: dict[int, QTimeEdit] = {}
        by_day = days.target_by_weekday()
        for col, (iso, letter) in enumerate(DAY_LETTERS.items()):
            label = QLabel(letter)
            label.setProperty("role", "muted")
            grid.addWidget(label, 0, col)
            edit = QTimeEdit(_qtime(by_day.get(iso, days.target_minutes())))
            edit.setDisplayFormat("H:mm")
            edit.setToolTip(DAY_NAMES[iso])
            self._day_lengths[iso] = edit
            grid.addWidget(edit, 1, col)
        vbox.addLayout(grid)
        layout.addWidget(hours)

        # --- Lunch and commute ---
        usual = QGroupBox("Usual times")
        form = QFormLayout(usual)
        self._lunch = QSpinBox()
        self._lunch.setRange(5, 180)
        self._lunch.setSingleStep(5)
        self._lunch.setSuffix(" min")
        self._lunch.setValue(models.get_int_setting("lunch_minutes", 60))
        self._lunch.setToolTip("Length of lunch when it is added to a day")
        form.addRow("Lunch", self._lunch)
        self._commute = QSpinBox()
        self._commute.setRange(0, 240)
        self._commute.setSingleStep(5)
        self._commute.setSuffix(" min each way")
        self._commute.setValue(models.get_int_setting("commute_minutes", 60))
        self._commute.setToolTip("Length of each commute, morning and evening")
        form.addRow("Commute", self._commute)
        note = QLabel("Used for new days, and when lunch or a commute is added back to a day.")
        note.setProperty("role", "faint")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(usual)

        # --- Snapping ---
        snapping = QGroupBox("Dragging nodes")
        form = QFormLayout(snapping)
        self._node_snap = QSpinBox()
        self._node_snap.setRange(1, 60)
        self._node_snap.setSuffix(" min")
        self._node_snap.setValue(models.get_int_setting("node_snap", 5))
        self._node_snap.setToolTip("Dragged nodes land on marks this far apart")
        form.addRow("Snap to every", self._node_snap)
        self._meeting_snap = QSpinBox()
        self._meeting_snap.setRange(0, 60)
        self._meeting_snap.setSuffix(" min")
        self._meeting_snap.setSpecialValueText("Off")
        self._meeting_snap.setValue(models.get_int_setting("meeting_snap", 5))
        self._meeting_snap.setToolTip("A node dragged this close to the start or end of a"
                                      " meeting jumps to it")
        form.addRow("Snap to meeting edges within", self._meeting_snap)
        note = QLabel("Nodes also snap to the current time. Hold Alt to snap only to meeting"
                      " starts and ends.")
        note.setProperty("role", "faint")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(snapping)

        # --- Startup ---
        startup = QGroupBox("Startup")
        hbox = QHBoxLayout(startup)
        self._autostart = QCheckBox("Launch ModeSwitch when Windows starts")
        self._autostart.setChecked(_autostart_enabled())
        self._autostart.setToolTip("Adds a shortcut to your Windows Startup folder")
        hbox.addWidget(self._autostart)
        layout.addWidget(startup)

        # --- Save / Cancel ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setToolTip("Close without saving")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.setToolTip("Save and apply straight away")
        save.clicked.connect(self._on_save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

        self._on_theme_chosen()
        self._update_lengths()

    # ------------------------------------------------------------------
    def _update_lengths(self) -> None:
        same = self._same.isChecked()
        self._all_length.setEnabled(same)
        working = self._working.selected()
        for iso, edit in self._day_lengths.items():
            edit.setEnabled(not same and iso in working)

    def _on_theme_chosen(self) -> None:
        custom = self._theme.currentData() == "custom"
        self._edit_colours.setEnabled(custom)
        if custom and not self._custom:
            # Start a custom theme from whichever preset is in use
            self._custom = {"base": theme.name if theme.name in theme_mod.PRESETS else "dark",
                            "tokens": {}}

    def _open_colours(self) -> None:
        from modeswitch.dialogs.theme_editor import ThemeEditor
        dlg = ThemeEditor(self, self._custom)
        if dlg.exec():
            self._custom = dlg.result_theme()

    def _on_save(self) -> None:
        models.set_setting("theme", self._theme.currentData())
        if self._custom:
            models.set_setting("theme_custom", json.dumps(self._custom))
        models.set_setting("working_days", self._working.as_setting())
        models.set_setting("wfh_days", self._wfh.as_setting())
        models.set_setting("target_same", "1" if self._same.isChecked() else "0")
        models.set_setting("target_minutes", str(_minutes(self._all_length.time())))
        models.set_setting("target_by_day", ",".join(
            f"{iso}:{_minutes(edit.time())}" for iso, edit in self._day_lengths.items()))
        models.set_setting("lunch_minutes", str(self._lunch.value()))
        models.set_setting("commute_minutes", str(self._commute.value()))
        models.set_setting("node_snap", str(self._node_snap.value()))
        models.set_setting("meeting_snap", str(self._meeting_snap.value()))

        if self._autostart.isChecked():
            if not _autostart_enabled():
                create_autostart_shortcut()
        else:
            _remove_autostart_shortcut()

        self.accept()
        theme_mod.hub().settings_changed.emit()

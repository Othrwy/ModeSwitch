"""
Settings dialog — working week, work-from-home days, autostart toggle.
Projects are edited in the review panel.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
    QPushButton, QMessageBox, QGroupBox
)

from modeswitch.db import models


STARTUP_FOLDER = Path(os.environ.get("APPDATA", "")) / \
    "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
SHORTCUT_NAME = "ModeSwitch.lnk"

DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


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


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Working week ---
        self._working_checks = self._day_group(
            "Working Week", models.get_day_list_setting("working_days"), layout)

        # --- Work from home ---
        self._wfh_checks = self._day_group(
            "Work From Home By Default (other days get a commute)",
            models.get_day_list_setting("wfh_days"), layout)

        # --- Autostart ---
        auto_group = QGroupBox("Startup")
        auto_hbox = QHBoxLayout(auto_group)
        self._autostart_cb = QCheckBox("Launch ModeSwitch when Windows starts")
        self._autostart_cb.setChecked(_autostart_enabled())
        auto_hbox.addWidget(self._autostart_cb)
        layout.addWidget(auto_group)

        # --- OK / Cancel ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("Save")
        ok_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    @staticmethod
    def _day_group(title: str, selected: list[int], layout: QVBoxLayout) -> dict[int, QCheckBox]:
        group = QGroupBox(title)
        hbox = QHBoxLayout(group)
        checks: dict[int, QCheckBox] = {}
        for iso, label in DAY_NAMES.items():
            cb = QCheckBox(label)
            cb.setChecked(iso in selected)
            checks[iso] = cb
            hbox.addWidget(cb)
        layout.addWidget(group)
        return checks

    @staticmethod
    def _checked(checks: dict[int, QCheckBox]) -> str:
        return ",".join(str(iso) for iso, cb in checks.items() if cb.isChecked())

    def _on_save(self) -> None:
        models.set_setting("working_days", self._checked(self._working_checks))
        models.set_setting("wfh_days", self._checked(self._wfh_checks))

        if self._autostart_cb.isChecked():
            if not _autostart_enabled():
                create_autostart_shortcut()
        else:
            _remove_autostart_shortcut()

        self.accept()

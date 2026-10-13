"""
ProjectGrid — shows up to 6 recent user projects + built-in buttons (LNCH, COMM, OW)
plus a "+" button to add new projects.

Emits mode_switched(project_id: int, default_time: str).
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QPushButton, QSizePolicy
)

from modeswitch.db.models import Project, get_recent_projects, get_builtin_projects


def _contrasting_text(hex_color: str) -> str:
    """Return black or white depending on background luminance."""
    c = QColor(hex_color)
    luminance = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#000000" if luminance > 140 else "#ffffff"


class ProjectGrid(QWidget):
    mode_switched = pyqtSignal(int, str)    # project_id, default_time (HH:MM)
    add_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setSpacing(4)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._active_project_id: int | None = None
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the button grid from the database."""
        # Clear existing
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        recent = get_recent_projects(limit=6)
        builtins = get_builtin_projects()

        all_projects = recent + builtins
        cols = 4
        for i, proj in enumerate(all_projects):
            btn = self._make_button(proj)
            self._layout.addWidget(btn, i // cols, i % cols)

        # "+" button
        plus_btn = QPushButton("+")
        plus_btn.setFixedHeight(28)
        plus_btn.setStyleSheet(
            "QPushButton { background: #444; color: #fff; border-radius: 4px; font-size: 16px; }"
            "QPushButton:hover { background: #666; }"
        )
        plus_btn.clicked.connect(self.add_requested.emit)
        idx = len(all_projects)
        self._layout.addWidget(plus_btn, idx // cols, idx % cols)

    def _make_button(self, proj: Project) -> QPushButton:
        text = f"{proj.code}"
        btn = QPushButton(text)
        btn.setFixedHeight(28)
        btn.setToolTip(proj.name)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        text_color = _contrasting_text(proj.color)
        self._style_button(btn, proj.color, text_color, active=proj.id == self._active_project_id)
        btn.clicked.connect(lambda checked, pid=proj.id: self._on_click(pid))
        btn.setProperty("project_id", proj.id)
        return btn

    @staticmethod
    def _style_button(btn: QPushButton, bg: str, fg: str, active: bool = False) -> None:
        border = "2px solid #fff" if active else "none"
        btn.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {fg}; border: {border}; "
            f"border-radius: 4px; font-size: 10px; }}"
            f"QPushButton:hover {{ opacity: 0.85; border: 2px solid #aaa; }}"
        )

    def _on_click(self, project_id: int) -> None:
        from datetime import datetime
        now = datetime.now().strftime("%H:%M")
        self._active_project_id = project_id
        self._update_active_highlight()
        self.mode_switched.emit(project_id, now)

    def _update_active_highlight(self) -> None:
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item and item.widget():
                btn = item.widget()
                pid = btn.property("project_id")
                if pid is not None:
                    # Re-apply style with/without active border
                    # We don't store color on the button, so just toggle border via property
                    active = (pid == self._active_project_id)
                    ss = btn.styleSheet()
                    # Toggle border line
                    if active:
                        ss = ss.replace("border: none", "border: 2px solid #fff")
                    else:
                        ss = ss.replace("border: 2px solid #fff", "border: none")
                    btn.setStyleSheet(ss)

    def set_active_project(self, project_id: int | None) -> None:
        self._active_project_id = project_id
        self._update_active_highlight()

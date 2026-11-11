"""
Add / Edit Project dialog — prompts for code, name, and color.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox
)

from modeswitch.db import models


class AddProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Project")
        self.setModal(True)
        self.setFixedWidth(320)
        self._color = "#4CAF50"
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Code
        layout.addWidget(QLabel("Project Code (up to 4 chars):"))
        self._code_edit = QLineEdit()
        self._code_edit.setMaxLength(4)
        self._code_edit.setPlaceholderText("e.g. 0001")
        layout.addWidget(self._code_edit)

        # Name
        layout.addWidget(QLabel("Project Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setMaxLength(40)
        self._name_edit.setPlaceholderText("e.g. My Project")
        layout.addWidget(self._name_edit)

        # Color
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Colour:"))
        self._color_preview = QPushButton()
        self._color_preview.setFixedSize(40, 24)
        self._apply_color_preview()
        self._color_preview.setToolTip("Change colour")
        self._color_preview.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_preview)
        color_row.addStretch()
        layout.addLayout(color_row)

        # Buttons
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _apply_color_preview(self) -> None:
        self._color_preview.setStyleSheet(
            f"background: {self._color}; border: 1px solid #888; border-radius: 3px;"
        )

    def _pick_color(self) -> None:
        from modeswitch.dialogs.colour_picker import pick_colour
        color = pick_colour(self, self._color, "Choose Project Colour")
        if color:
            self._color = color
            self._apply_color_preview()

    def _on_ok(self) -> None:
        code = self._code_edit.text().strip().upper()
        name = self._name_edit.text().strip()

        if not code:
            QMessageBox.warning(self, "Validation", "Project code is required.")
            return
        if not name:
            QMessageBox.warning(self, "Validation", "Project name is required.")
            return

        # Check uniqueness
        existing = [p.code for p in models.get_all_projects()]
        if code in existing:
            QMessageBox.warning(self, "Validation", f"Code '{code}' already exists.")
            return

        self.created_project = models.create_project(code, name, self._color)
        self.accept()

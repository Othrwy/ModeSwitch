"""
EditModesDialog — list all projects with inline rename, colour-pick, and delete.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QWidget, QColorDialog, QMessageBox
)

from modeswitch.db import models
from modeswitch.db.models import Project


class EditModesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Modes")
        self.setMinimumWidth(420)
        self.setMinimumHeight(300)
        self.setModal(True)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Scrollable rows area
        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setSpacing(4)
        self._rows_layout.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rows_widget)
        layout.addWidget(scroll)

        # Add new + Close buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add New Mode")
        add_btn.clicked.connect(self._add_project)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    def _populate(self) -> None:
        # Clear old rows
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_projects = models.get_all_projects()
        for proj in all_projects:
            self._rows_layout.addWidget(self._build_row(proj))

        self._rows_layout.addStretch()

    # ------------------------------------------------------------------
    def _build_row(self, proj: Project) -> QWidget:
        row = QWidget()
        hbox = QHBoxLayout(row)
        hbox.setContentsMargins(0, 2, 0, 2)
        hbox.setSpacing(8)

        # Colour swatch button
        color_btn = QPushButton()
        color_btn.setFixedSize(22, 22)
        color_btn.setStyleSheet(
            f"background: {proj.color}; border: 1px solid #666; border-radius: 3px;"
        )
        color_btn.setToolTip("Change colour")
        color_btn.clicked.connect(lambda _, p=proj: self._edit_color(p))
        hbox.addWidget(color_btn)

        # Code label (fixed, not editable)
        code_lbl = QLabel(proj.code)
        code_lbl.setFixedWidth(38)
        code_lbl.setStyleSheet("font-weight: bold; color: #ddd; font-size: 11px;")
        hbox.addWidget(code_lbl)

        # Name (editable; builtins can rename too except code stays fixed)
        name_edit = QLineEdit(proj.name)
        name_edit.setMaxLength(40)
        name_edit.editingFinished.connect(
            lambda ne=name_edit, pid=proj.id: self._save_name(pid, ne.text())
        )
        hbox.addWidget(name_edit)

        # Builtin badge
        if proj.is_builtin:
            badge = QLabel("built-in")
            badge.setStyleSheet("color: #666; font-size: 9px;")
            badge.setFixedWidth(42)
            hbox.addWidget(badge)

        # Delete button (non-builtin only)
        if not proj.is_builtin:
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(26, 26)
            del_btn.setToolTip("Delete project")
            del_btn.setStyleSheet(
                "background: #7a2c2c; color: #fff; border-radius: 3px; font-size: 11px;"
            )
            del_btn.clicked.connect(lambda _, pid=proj.id: self._delete_project(pid))
            hbox.addWidget(del_btn)
        else:
            # Placeholder so layout stays aligned
            spacer = QWidget()
            spacer.setFixedSize(26, 26)
            hbox.addWidget(spacer)

        return row

    # ------------------------------------------------------------------
    def _save_name(self, project_id: int, name: str) -> None:
        name = name.strip()
        if name:
            models.update_project(project_id, name=name)

    def _edit_color(self, proj: Project) -> None:
        color = QColorDialog.getColor(QColor(proj.color), self, "Choose Colour")
        if color.isValid():
            models.update_project(proj.id, color=color.name())
            self._populate()

    def _delete_project(self, project_id: int) -> None:
        reply = QMessageBox.question(
            self, "Delete Mode",
            "Delete this mode? Existing time log entries will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            models.delete_project(project_id)
            self._populate()

    def _add_project(self) -> None:
        from modeswitch.dialogs.add_project import AddProjectDialog
        dlg = AddProjectDialog(self)
        if dlg.exec():
            self._populate()

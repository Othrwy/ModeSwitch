"""
QApplication + QSystemTrayIcon wrapper.
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox
)

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


class App:
    def __init__(self):
        self.qapp = QApplication.instance() or QApplication(sys.argv)
        self.qapp.setQuitOnLastWindowClosed(False)
        self.qapp.setApplicationName("ModeSwitch")

        self._apply_stylesheet()

        init_db()

        self.ribbon = RibbonWindow()
        self.ribbon.show()

        self._tray = self._build_tray()
        self._tray.show()

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

        settings_action = menu.addAction("Settings")
        settings_action.triggered.connect(self._open_settings)

        menu.addSeparator()

        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self._exit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        return tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_ribbon()

    def _show_ribbon(self) -> None:
        self.ribbon.place()
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

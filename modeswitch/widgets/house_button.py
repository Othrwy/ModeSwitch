"""
HouseButton — a small checkable button with a house on it.
Checked means working from home (no commute).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QPolygonF
from PyQt6.QtWidgets import QToolButton

from modeswitch.theme import current as theme


class HouseButton(QToolButton):
    def __init__(self, parent=None, size: int = 24):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._update_tooltip)
        self._update_tooltip(False)

    def _update_tooltip(self, checked: bool) -> None:
        self.setToolTip("Working from home — click to add a commute" if checked
                        else "Commuting — click for working from home")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        on = self.isChecked()

        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor("#2e5d3a") if on else theme.q("surface")
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)

        p.setBrush(QColor("#ffffff") if on else theme.q("faint"))
        roof = QPolygonF([QPointF(w * 0.5, h * 0.2), QPointF(w * 0.85, h * 0.5),
                          QPointF(w * 0.15, h * 0.5)])
        p.drawPolygon(roof)
        p.drawRect(QRectF(w * 0.27, h * 0.5, w * 0.46, h * 0.3))
        p.setBrush(bg)
        p.drawRect(QRectF(w * 0.44, h * 0.6, w * 0.12, h * 0.2))
        p.end()

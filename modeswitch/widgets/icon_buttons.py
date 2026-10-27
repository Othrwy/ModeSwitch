"""
Small checkable buttons with a painted icon, in the same style as HouseButton:
  • SunButton      — the day is a holiday
  • SandwichButton — the day has a lunch break
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QToolButton

from modeswitch.theme import current as theme


def off_bg() -> QColor:
    return theme.q("surface")


def off_fg() -> QColor:
    return theme.q("faint")


class _IconButton(QToolButton):
    ON_BG = QColor("#3a3a3a")
    TIP_ON = TIP_OFF = ""

    def __init__(self, parent=None, size: int = 24):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._update_tooltip)
        self._update_tooltip(False)

    def _update_tooltip(self, checked: bool) -> None:
        self.setToolTip(self.TIP_ON if checked else self.TIP_OFF)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.ON_BG if self.isChecked() else off_bg())
        p.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)
        self.paint_icon(p, w, h, self.isChecked())
        p.end()

    def paint_icon(self, p: QPainter, w: int, h: int, on: bool) -> None:
        raise NotImplementedError


class SunButton(_IconButton):
    ON_BG = QColor("#6b5214")
    TIP_ON = "Holiday — click to make it a working day"
    TIP_OFF = "Mark as holiday"

    def paint_icon(self, p, w, h, on):
        color = QColor("#ffd34d") if on else off_fg()
        cx, cy = w / 2, h / 2
        p.setPen(QPen(color, max(1.0, w / 14), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for k in range(8):
            a = k * math.pi / 4
            p.drawLine(QPointF(cx + math.cos(a) * w * 0.27, cy + math.sin(a) * h * 0.27),
                       QPointF(cx + math.cos(a) * w * 0.40, cy + math.sin(a) * h * 0.40))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(cx, cy), w * 0.18, h * 0.18)


class SandwichButton(_IconButton):
    ON_BG = QColor("#5a3d1e")
    TIP_ON = "Lunch today — click to take lunch off this day"
    TIP_OFF = "No lunch today — click to add it back"

    def paint_icon(self, p, w, h, on):
        bread = QColor("#e8b96a") if on else off_fg()
        lettuce = QColor("#6cc04a") if on else off_fg().darker(120)
        tomato = QColor("#e0533d") if on else off_fg().darker(110)
        # Side on: bread, lettuce, tomato, bread
        p.setPen(Qt.PenStyle.NoPen)
        x, width = w * 0.16, w * 0.68
        p.setBrush(bread)
        p.drawRoundedRect(QRectF(x, h * 0.22, width, h * 0.18), 2, 2)
        p.setBrush(lettuce)
        p.drawRect(QRectF(x - w * 0.03, h * 0.42, width + w * 0.06, h * 0.10))
        p.setBrush(tomato)
        p.drawRect(QRectF(x + w * 0.02, h * 0.52, width - w * 0.04, h * 0.09))
        p.setBrush(bread)
        p.drawRoundedRect(QRectF(x, h * 0.62, width, h * 0.16), 2, 2)

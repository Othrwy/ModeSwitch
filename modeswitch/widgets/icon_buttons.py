"""
Small checkable buttons with a painted icon, in the same style as HouseButton:
  • SunButton      — the day is a holiday
  • SandwichButton — the day has a lunch break
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
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
    TIP_ON = TIP_OFF = "Lunch Toggle"

    def paint_icon(self, p, w, h, on):
        # A sandwich wedge: the top slice seen as a triangle, then the layers from
        # the side: crust, lettuce, a sliver of filling with tomato, bottom slice.
        def c(on_colour, off_factor=100):
            return QColor(on_colour) if on else off_fg().lighter(off_factor)
        bread = c("#f9c17a", 120)
        crust = c("#a8754e", 90)
        lettuce = c("#9bd13c", 105)
        filling = c("#f4efe4", 130)
        tomato = c("#e8322b", 80)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bread)        # top slice
        p.drawPolygon(QPolygonF([QPointF(w * 0.14, h * 0.47), QPointF(w * 0.63, h * 0.14),
                                 QPointF(w * 0.84, h * 0.47)]))
        p.setBrush(crust)        # top crust
        p.drawRoundedRect(QRectF(w * 0.12, h * 0.44, w * 0.76, h * 0.11), h * 0.05, h * 0.05)
        p.setBrush(filling)
        p.drawRect(QRectF(w * 0.15, h * 0.58, w * 0.55, h * 0.06))
        p.setBrush(lettuce)
        p.drawRoundedRect(QRectF(w * 0.11, h * 0.54, w * 0.70, h * 0.06), h * 0.03, h * 0.03)
        p.setBrush(tomato)
        p.drawRoundedRect(QRectF(w * 0.52, h * 0.56, w * 0.36, h * 0.12), h * 0.06, h * 0.06)
        p.setBrush(crust)        # bottom slice
        p.drawRoundedRect(QRectF(w * 0.14, h * 0.66, w * 0.72, h * 0.12), h * 0.05, h * 0.05)

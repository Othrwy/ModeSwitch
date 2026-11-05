"""
The app's icon: two rounded green triangles on a dark rounded tile. The top one sits
against the right edge pointing left, the bottom one against the left edge pointing
right, and the dark gap between them makes an S — ModeSwitch switching between modes.
The tile keeps it visible on both light and dark taskbars.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QPen, QPolygonF

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

TILE = "#191a1b"
GREEN = "#26e600"
# Corners as fractions of the icon's size: (back edge top, back edge bottom, point)
TRIANGLES = [
    ((0.86, 0.12), (0.86, 0.54), (0.36, 0.27)),   # top, pointing left
    ((0.14, 0.46), (0.14, 0.88), (0.64, 0.73)),   # bottom, pointing right
]


def paint(p: QPainter, size: int) -> None:
    s = float(size)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(TILE))
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)

    # A round-joined outline in the same green softens the corners
    pen = QPen(QColor(GREEN), s * 0.07)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(QColor(GREEN))
    for corners in TRIANGLES:
        p.drawPolygon(QPolygonF([QPointF(x * s, y * s) for x, y in corners]))


def pixmap(size: int) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    paint(p, size)
    p.end()
    return px


def app_icon() -> QIcon:
    """Drawn at each size, so it stays crisp at any display scaling."""
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(pixmap(size))
    return icon

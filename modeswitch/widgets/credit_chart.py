"""
CreditChart — hours worked per day against the nominal day, with the running
credit balance above it.

  • solid line  — the nominal day (8h)
  • dashed line — hours actually worked each day
  • headline    — total credit (+) or debit (−) over the days shown

Holidays and days with nothing logged are shown on the axis but not counted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt, QEvent, QPointF, QRect, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

from modeswitch.timeutil import fmt_duration, fmt_signed

CREDIT = QColor("#f4a261")
DEBIT = QColor("#e07070")
NOMINAL = QColor("#9a9a9a")
GRID = QColor("#333333")
TEXT = QColor("#aaaaaa")
FAINT = QColor("#666666")

HEAD_H = 34
AXIS_W = 30
FOOT_H = 18
POINT_R = 3.5


@dataclass
class ChartDay:
    day: date
    worked: Optional[int]   # minutes; None for a day not counted
    note: str = ""          # why it is not counted: "Holiday", "No data"


class CreditChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._days: list[ChartDay] = []
        self._target = 480
        self._font = QFont("Segoe UI", 8)
        self._head_font = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_days(self, days: list[ChartDay], target_minutes: int) -> None:
        self._days = days
        self._target = target_minutes
        self.update()

    def _counted(self) -> list[ChartDay]:
        return [d for d in self._days if d.worked is not None]

    def balance(self) -> int:
        return sum(d.worked - self._target for d in self._counted())

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _plot_rect(self) -> QRect:
        return QRect(AXIS_W, HEAD_H, self.width() - AXIS_W - 8, self.height() - HEAD_H - FOOT_H)

    def _hour_range(self) -> tuple[int, int]:
        """Whole hours, always including an hour either side of the nominal day."""
        nominal = self._target / 60
        values = [d.worked / 60 for d in self._counted()] + [nominal - 1, nominal + 1]
        return int(min(values)) - (1 if min(values) % 1 == 0 else 0), int(max(values)) + 1

    def _x(self, i: int) -> float:
        r = self._plot_rect()
        n = len(self._days)
        if n == 1:
            return r.center().x()
        return r.left() + 8 + i * (r.width() - 16) / (n - 1)

    def _y(self, minutes: float) -> float:
        r = self._plot_rect()
        lo, hi = self._hour_range()
        return r.bottom() - (minutes / 60 - lo) / (hi - lo) * r.height()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#252525"))
        self._paint_headline(p)
        if not self._days:
            p.end()
            return
        self._paint_grid(p)
        self._paint_nominal(p)
        self._paint_worked(p)
        self._paint_days(p)
        p.end()

    def _paint_headline(self, p: QPainter) -> None:
        counted = self._counted()
        if not counted:
            p.setFont(self._font)
            p.setPen(FAINT)
            p.drawText(QRect(8, 6, self.width() - 16, 20), int(Qt.AlignmentFlag.AlignLeft),
                       "No finished days to show yet")
            return
        bal = self.balance()
        p.setFont(self._head_font)
        p.setPen(CREDIT if bal >= 0 else DEBIT)
        if bal == 0:
            headline = "On target"
        else:
            headline = f"{fmt_duration(abs(bal))} {'in credit' if bal > 0 else 'to make up'}"
        p.drawText(QRect(8, 4, self.width() - 16, 20), int(Qt.AlignmentFlag.AlignLeft), headline)
        p.setFont(self._font)
        p.setPen(TEXT)
        first = counted[0].day.strftime("%a %d %b")
        p.drawText(QRect(8, 4, self.width() - 16, 20),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                   f"{len(counted)} days since {first}")

    def _paint_grid(self, p: QPainter) -> None:
        r = self._plot_rect()
        lo, hi = self._hour_range()
        step = 1 if hi - lo <= 6 else 2
        p.setFont(self._font)
        for h in range(lo, hi + 1, step):
            y = self._y(h * 60)
            p.setPen(QPen(GRID, 1))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(FAINT)
            p.drawText(QRectF(0, y - 7, AXIS_W - 4, 14),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), f"{h}h")

    def _paint_nominal(self, p: QPainter) -> None:
        r = self._plot_rect()
        y = self._y(self._target)
        p.setPen(QPen(NOMINAL, 1.5))
        p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))

    def _paint_worked(self, p: QPainter) -> None:
        points = [(i, d) for i, d in enumerate(self._days) if d.worked is not None]
        if len(points) > 1:
            path = QPainterPath()
            for k, (i, d) in enumerate(points):
                pt = QPointF(self._x(i), self._y(d.worked))
                path.moveTo(pt) if k == 0 else path.lineTo(pt)
            pen = QPen(CREDIT, 1.5, Qt.PenStyle.DashLine)
            pen.setDashPattern([4, 3])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        for i, d in points:
            p.setBrush(CREDIT if d.worked >= self._target else DEBIT)
            p.drawEllipse(QPointF(self._x(i), self._y(d.worked)), POINT_R, POINT_R)

    def _paint_days(self, p: QPainter) -> None:
        r = self._plot_rect()
        p.setFont(self._font)
        every = max(1, -(-len(self._days) * 40 // max(1, r.width())))   # labels need ~40px
        for i, d in enumerate(self._days):
            if i % every and i != len(self._days) - 1:
                continue
            p.setPen(TEXT if d.worked is not None else FAINT)
            label = d.day.strftime("%a %d")
            if d.worked is None and d.note == "Holiday":
                label += " ☀"
            p.drawText(QRectF(self._x(i) - 30, r.bottom() + 3, 60, FOOT_H - 3),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), label)

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------
    def event(self, e):
        if e.type() == QEvent.Type.ToolTip:
            text = self._tooltip_at(e.pos().x())
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def _tooltip_at(self, x: float) -> str:
        if not self._days:
            return ""
        i = min(range(len(self._days)), key=lambda k: abs(self._x(k) - x))
        if abs(self._x(i) - x) > 20:
            return ""
        d = self._days[i]
        name = d.day.strftime("%a %d %b")
        if d.worked is None:
            return f"{name}: {d.note or 'not counted'}"
        return f"{name}: {fmt_duration(d.worked)} ({fmt_signed(d.worked - self._target)})"

"""
CreditChart — one value per day plotted as a dashed line, optionally against a
nominal value drawn as a solid line.

Two modes:
  • "credit" — hours worked against the nominal working day. The headline is the
               running balance; points are credit-coloured at or over the nominal
               day and debit-coloured under it.
  • "total"  — time on one thing (a project, lunch, commute). The headline is the
               total and the average per counted day; points use the thing's colour.

Either mode can be drawn as a dashed line with points, or as bars from zero.

Holidays and days with nothing logged are shown on the axis but not counted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt, QEvent, QPointF, QRect, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

from modeswitch.theme import current as theme
from modeswitch.timeutil import fmt_duration, fmt_signed

HEAD_H = 34
AXIS_W = 30
FOOT_H = 18
POINT_R = 3.5
X_INSET = 26        # room either side for the first and last day labels
BAR_MAX_W = 22
BAR_RADIUS = 4


def bar_path(rect: QRectF, radius: float = BAR_RADIUS) -> QPainterPath:
    """A bar with its top corners rounded and its foot square on the baseline."""
    r = min(radius, rect.width() / 2, rect.height())
    path = QPainterPath()
    path.moveTo(rect.bottomLeft())
    path.lineTo(rect.left(), rect.top() + r)
    path.quadTo(rect.topLeft(), QPointF(rect.left() + r, rect.top()))
    path.lineTo(rect.right() - r, rect.top())
    path.quadTo(rect.topRight(), QPointF(rect.right(), rect.top() + r))
    path.lineTo(rect.bottomRight())
    path.closeSubpath()
    return path


@dataclass
class ChartDay:
    day: date
    value: Optional[int]            # minutes; None for a day not counted
    target: Optional[int] = None    # nominal minutes for that day, if there is one
    note: str = ""                  # why it is not counted: "Holiday", "No data"


class CreditChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._days: list[ChartDay] = []
        self._mode = "credit"
        self._style = "line"
        self._color: Optional[str] = None
        self._label = ""
        self._font = QFont("Segoe UI", 8)
        self._head_font = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_series(self, days: list[ChartDay], mode: str = "credit",
                   color: Optional[str] = None, label: str = "") -> None:
        self._days = days
        self._mode = mode
        self._color = color
        self._label = label
        self.update()

    def set_style(self, style: str) -> None:
        """'line' (dashed line and points) or 'bar'."""
        self._style = style if style == "bar" else "line"
        self.update()

    def _counted(self) -> list[ChartDay]:
        return [d for d in self._days if d.value is not None]

    def balance(self) -> int:
        return sum(d.value - (d.target or 0) for d in self._counted())

    def _series_color(self) -> QColor:
        return QColor(self._color) if self._color else theme.q("credit")

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _plot_rect(self) -> QRect:
        return QRect(AXIS_W, HEAD_H, self.width() - AXIS_W - 8, self.height() - HEAD_H - FOOT_H)

    def _hour_range(self) -> tuple[int, int]:
        values = [d.value / 60 for d in self._counted()]
        values += [d.target / 60 for d in self._days if d.target is not None]
        if self._mode == "credit" and self._style == "line":
            targets = [d.target / 60 for d in self._days if d.target is not None] or [8]
            values += [min(targets) - 1, max(targets) + 1]
            return int(min(values)) - (1 if min(values) % 1 == 0 else 0), int(max(values)) + 1
        return 0, max(1, int(max(values or [0])) + 1)

    def _x(self, i: int) -> float:
        r = self._plot_rect()
        n = len(self._days)
        if n == 1:
            return r.center().x()
        return r.left() + X_INSET + i * (r.width() - 2 * X_INSET) / (n - 1)

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
        p.fillRect(self.rect(), theme.q("surface"))
        self._paint_headline(p)
        if not self._days:
            p.end()
            return
        self._paint_grid(p)
        if self._style == "bar":
            self._paint_bars(p)
            self._paint_nominal(p)   # over the bars, so it reads as the bar to reach
        else:
            self._paint_nominal(p)
            self._paint_values(p)
        self._paint_days(p)
        p.end()

    def _paint_headline(self, p: QPainter) -> None:
        counted = self._counted()
        box = QRect(8, 4, self.width() - 16, 20)
        if not counted:
            p.setFont(self._font)
            p.setPen(theme.q("faint"))
            p.drawText(box, int(Qt.AlignmentFlag.AlignLeft), "No finished days to show yet")
            return
        p.setFont(self._head_font)
        if self._mode == "credit":
            bal = self.balance()
            p.setPen(theme.q("credit") if bal >= 0 else theme.q("debit"))
            if bal == 0:
                headline = "On target"
            else:
                headline = f"{fmt_duration(abs(bal))} {'in credit' if bal > 0 else 'to make up'}"
        else:
            total = sum(d.value for d in counted)
            p.setPen(self._series_color())
            headline = (f"{fmt_duration(total) if total else '0m'} {self._label}"
                        f"  ·  {fmt_duration(round(total / len(counted))) or '0m'} a day")
        p.drawText(box, int(Qt.AlignmentFlag.AlignLeft), headline)
        p.setFont(self._font)
        p.setPen(theme.q("muted"))
        first = counted[0].day.strftime("%a %d %b")
        p.drawText(box, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                   f"{len(counted)} days since {first}")

    def _paint_grid(self, p: QPainter) -> None:
        r = self._plot_rect()
        lo, hi = self._hour_range()
        step = 1 if hi - lo <= 6 else 2
        p.setFont(self._font)
        for h in range(lo, hi + 1, step):
            y = self._y(h * 60)
            p.setPen(QPen(theme.q("grid"), 1))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(theme.q("faint"))
            p.drawText(QRectF(0, y - 7, AXIS_W - 4, 14),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), f"{h}h")

    def _paint_nominal(self, p: QPainter) -> None:
        """Solid line at each day's nominal value: a step where day lengths differ,
        one flat line when every day is the same."""
        points = [(i, d.target) for i, d in enumerate(self._days) if d.target is not None]
        if not points:
            return
        r = self._plot_rect()
        p.setPen(QPen(theme.q("muted"), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        for k, (i, target) in enumerate(points):
            left = r.left() if k == 0 else (self._x(points[k - 1][0]) + self._x(i)) / 2
            right = r.right() if k == len(points) - 1 else (self._x(i) + self._x(points[k + 1][0])) / 2
            y = self._y(target)
            if k == 0:
                path.moveTo(QPointF(left, y))
            else:
                path.lineTo(QPointF(left, y))
            path.lineTo(QPointF(right, y))
        p.drawPath(path)

    def _paint_values(self, p: QPainter) -> None:
        points = [(i, d) for i, d in enumerate(self._days) if d.value is not None]
        color = self._series_color()
        if len(points) > 1:
            path = QPainterPath()
            for k, (i, d) in enumerate(points):
                pt = QPointF(self._x(i), self._y(d.value))
                path.moveTo(pt) if k == 0 else path.lineTo(pt)
            pen = QPen(color, 1.5, Qt.PenStyle.DashLine)
            pen.setDashPattern([4, 3])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        for i, d in points:
            if self._mode == "credit":
                p.setBrush(theme.q("credit") if d.value >= (d.target or 0) else theme.q("debit"))
            else:
                p.setBrush(color)
            p.drawEllipse(QPointF(self._x(i), self._y(d.value)), POINT_R, POINT_R)

    def _paint_bars(self, p: QPainter) -> None:
        r = self._plot_rect()
        n = len(self._days)
        slot = (r.width() - 2 * X_INSET) / max(1, n - 1) if n > 1 else r.width()
        width = max(3.0, min(BAR_MAX_W, slot * 0.6))
        base = self._y(0)
        color = self._series_color()
        p.setPen(Qt.PenStyle.NoPen)
        for i, d in enumerate(self._days):
            if not d.value:
                continue
            if self._mode == "credit":
                p.setBrush(theme.q("credit") if d.value >= (d.target or 0) else theme.q("debit"))
            else:
                p.setBrush(color)
            top = self._y(d.value)
            p.drawPath(bar_path(QRectF(self._x(i) - width / 2, top, width, base - top)))

    def _paint_days(self, p: QPainter) -> None:
        r = self._plot_rect()
        p.setFont(self._font)
        every = max(1, -(-len(self._days) * 40 // max(1, r.width())))   # labels need ~40px
        for i, d in enumerate(self._days):
            if i % every and i != len(self._days) - 1:
                continue
            p.setPen(theme.q("muted") if d.value is not None else theme.q("faint"))
            label = d.day.strftime("%a %d")
            if d.value is None and d.note == "Holiday":
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
        if d.value is None:
            return f"{name}: {d.note or 'not counted'}"
        text = f"{name}: {fmt_duration(d.value) or '0m'}"
        if self._mode == "credit" and d.target is not None:
            text += f" ({fmt_signed(d.value - d.target)} against {fmt_duration(d.target)})"
        return text

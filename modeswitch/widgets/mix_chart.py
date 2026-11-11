"""
MixChart — every project's time together, one stack or pie per period.

Each period (a week, fortnight, month, or all time) holds the minutes on each
project. Two styles:
  • "bar" — one stacked bar per period, the biggest project overall at the foot.
  • "pie" — one pie per period, as many of the newest as fit side by side.

Periods hold totals; with `per_day` (all time) everything is divided by the days
counted, so the chart shows an average day. A legend on the right names the
projects, and hovering a segment or slice gives its time and share.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import Qt, QEvent, QPointF, QRect, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

from modeswitch.theme import current as theme
from modeswitch.timeutil import fmt_duration
from modeswitch.widgets.credit_chart import AXIS_W, FOOT_H, HEAD_H, bar_path

LEGEND_W = 92
LEGEND_ROW = 14
MIN_SLOT = 14       # narrowest a period's slot can get before older ones are dropped
BAR_MAX_W = 40
GAP = 2             # surface-coloured gap between segments and slices
MIN_PIE = 70


@dataclass
class MixSeries:
    key: object                 # project id, or None for unassigned time
    code: str                   # "1234", in the legend
    name: str                   # "1234 Name", in the tooltip
    color: str


@dataclass
class MixPeriod:
    label: str                  # under the bar or pie: "02 Nov"
    name: str                   # in the tooltip: "Week of Mon 02 Nov"
    days: int                   # days counted
    minutes: dict = field(default_factory=dict)   # series key -> minutes

    def total(self) -> int:
        return sum(self.minutes.values())


def _nice_step(top_hours: float) -> int:
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500):
        if top_hours / step <= 5:
            return step
    return 1000


class MixChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._periods: list[MixPeriod] = []
        self._series: list[MixSeries] = []
        self._style = "bar"
        self._per_day = False
        self._unit = "week"
        self._note = ""
        self._hits: list[tuple] = []    # ("bar", rect, period, series) or ("pie", centre, r, a0, span, period, series)
        self._font = QFont("Segoe UI", 8)
        self._head_font = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_data(self, periods: list[MixPeriod], series: list[MixSeries], style: str = "bar",
                 per_day: bool = False, unit: str = "week", note: str = "") -> None:
        """`series` in stacking order (biggest first); `unit` names a period in the
        headline; `note` goes top right."""
        self._periods = periods
        self._series = series
        self._style = style if style == "pie" else "bar"
        self._per_day = per_day
        self._unit = unit
        self._note = note
        self.update()

    def _value(self, period: MixPeriod, minutes: float) -> float:
        return minutes / period.days if self._per_day and period.days else minutes

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _plot_rect(self) -> QRect:
        left = AXIS_W if self._style == "bar" else 8
        return QRect(left, HEAD_H, self.width() - left - LEGEND_W - 8,
                     self.height() - HEAD_H - FOOT_H)

    def _shown(self) -> list[MixPeriod]:
        """The newest periods that fit."""
        width = self._plot_rect().width()
        fit = width // MIN_SLOT if self._style == "bar" else width // (MIN_PIE + 8)
        return self._periods[-max(1, fit):]

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), theme.q("surface"))
        self._hits = []
        shown = self._shown()
        self._paint_headline(p)
        if any(period.days for period in shown):
            if self._style == "bar":
                self._paint_bars(p, shown)
            else:
                self._paint_pies(p, shown)
            self._paint_legend(p, shown)
        p.end()

    def _paint_headline(self, p: QPainter) -> None:
        box = QRect(8, 4, self.width() - 16, 20)
        counted = [period for period in self._periods if period.days]
        if not counted:
            p.setFont(self._font)
            p.setPen(theme.q("faint"))
            p.drawText(box, int(Qt.AlignmentFlag.AlignLeft), "No finished days to show yet")
            return
        total = sum(period.total() for period in counted)
        if self._per_day:
            days = sum(period.days for period in counted)
            headline = f"{fmt_duration(round(total / days)) or '0m'} on an average day"
        else:
            headline = (f"{fmt_duration(round(total / len(counted))) or '0m'}"
                        f" a {self._unit} on average")
        p.setFont(self._head_font)
        p.setPen(theme.q("text"))
        p.drawText(box, int(Qt.AlignmentFlag.AlignLeft), headline)
        p.setFont(self._font)
        p.setPen(theme.q("muted"))
        p.drawText(box, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                   self._note)

    def _paint_bars(self, p: QPainter, shown: list[MixPeriod]) -> None:
        r = self._plot_rect()
        top_hours = max((self._value(period, period.total()) for period in shown), default=0) / 60
        step = _nice_step(max(top_hours, 1))
        hi = max(step, math.ceil(top_hours / step) * step)
        y = lambda minutes: r.bottom() - minutes / 60 / hi * r.height()

        p.setFont(self._font)
        for h in range(0, hi + 1, step):
            p.setPen(QPen(theme.q("grid"), 1))
            p.drawLine(QPointF(r.left(), y(h * 60)), QPointF(r.right(), y(h * 60)))
            p.setPen(theme.q("faint"))
            p.drawText(QRectF(0, y(h * 60) - 7, AXIS_W - 4, 14),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), f"{h}h")

        slot = r.width() / len(shown)
        width = max(4.0, min(BAR_MAX_W, slot * 0.65))
        every = max(1, math.ceil(44 / slot))   # labels need ~44px
        surface = theme.q("surface")
        for i, period in enumerate(shown):
            cx = r.left() + slot * (i + 0.5)
            if i % every == 0 or i == len(shown) - 1:
                p.setPen(theme.q("muted") if period.days else theme.q("faint"))
                p.drawText(QRectF(cx - slot * every / 2, r.bottom() + 3, slot * every, FOOT_H - 3),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                           period.label)
            total = self._value(period, period.total())
            if not total:
                continue
            p.save()
            p.setClipPath(bar_path(QRectF(cx - width / 2, y(total), width, y(0) - y(total))))
            p.setPen(Qt.PenStyle.NoPen)
            below = 0.0
            for series in self._series:
                minutes = self._value(period, period.minutes.get(series.key, 0))
                if not minutes:
                    continue
                seg = QRectF(cx - width / 2, y(below + minutes), width, y(below) - y(below + minutes))
                p.fillRect(seg, QColor(series.color))
                if below:
                    p.fillRect(QRectF(seg.left(), seg.bottom() - GAP / 2, width, GAP), surface)
                self._hits.append(("bar", seg.adjusted(-3, 0, 3, 0), period, series))
                below += minutes
            p.restore()

    def _paint_pies(self, p: QPainter, shown: list[MixPeriod]) -> None:
        r = self._plot_rect()
        slot = r.width() / len(shown)
        label_h = 28
        radius = max(10.0, min(slot - 12, r.height() + FOOT_H - label_h, 150) / 2)
        p.setFont(self._font)
        for i, period in enumerate(shown):
            centre = QPointF(r.left() + slot * (i + 0.5), r.top() + radius + 2)
            box = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
            total = period.total()
            if not total:
                p.setPen(QPen(theme.q("grid"), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(box)
            else:
                p.setPen(QPen(theme.q("surface"), GAP))
                angle = 90.0   # start at twelve o'clock and go clockwise
                for series in self._series:
                    minutes = period.minutes.get(series.key, 0)
                    if not minutes:
                        continue
                    span = -360.0 * minutes / total
                    p.setBrush(QColor(series.color))
                    if abs(span) >= 359.9:
                        p.drawEllipse(box)
                    else:
                        p.drawPie(box, round(angle * 16), round(span * 16))
                    self._hits.append(("pie", centre, radius, angle, span, period, series))
                    angle += span
            text = period.label if self._per_day or not total else \
                f"{period.label}\n{fmt_duration(total)}"
            p.setPen(theme.q("muted") if period.days else theme.q("faint"))
            p.drawText(QRectF(centre.x() - slot / 2, box.bottom() + 2, slot, label_h),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                       text if period.days else f"{period.label}\nNo data")

    def _paint_legend(self, p: QPainter, shown: list[MixPeriod]) -> None:
        present = [s for s in self._series if any(period.minutes.get(s.key) for period in shown)]
        left = self.width() - LEGEND_W
        rows = max(1, (self._plot_rect().height() + FOOT_H) // LEGEND_ROW)
        listed = present if len(present) <= rows else present[:rows - 1]
        p.setFont(self._font)
        for k, series in enumerate(listed):
            y = HEAD_H + k * LEGEND_ROW
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(series.color))
            p.drawRoundedRect(QRectF(left, y + 3, 8, 8), 2, 2)
            p.setPen(theme.q("muted"))
            p.drawText(QRectF(left + 13, y, LEGEND_W - 15, LEGEND_ROW),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       series.code)
        if len(listed) < len(present):
            p.setPen(theme.q("faint"))
            p.drawText(QRectF(left + 13, HEAD_H + len(listed) * LEGEND_ROW, LEGEND_W - 15, LEGEND_ROW),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       f"+{len(present) - len(listed)} more")

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------
    def event(self, e):
        if e.type() == QEvent.Type.ToolTip:
            text = self._tooltip_at(QPointF(e.pos()))
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def _tooltip_at(self, pos: QPointF) -> str:
        for hit in self._hits:
            if hit[0] == "bar":
                _, rect, period, series = hit
                if not rect.contains(pos):
                    continue
            else:
                _, centre, radius, a0, span, period, series = hit
                dx, dy = pos.x() - centre.x(), centre.y() - pos.y()
                if dx * dx + dy * dy > radius * radius:
                    continue
                # How far clockwise from the slice's start edge the cursor is
                along = (a0 - math.degrees(math.atan2(dy, dx))) % 360
                if along > -span:
                    continue
            minutes = period.minutes.get(series.key, 0)
            share = round(100 * minutes / period.total())
            text = f"{period.name}\n{series.name}: "
            if self._per_day:
                return text + f"{fmt_duration(round(minutes / period.days))} a day ({share}%)"
            return (text + f"{fmt_duration(minutes)} ({share}%)"
                    f"\n{fmt_duration(round(minutes / period.days)) or '0m'} a day"
                    f" over {period.days} day{'s' if period.days != 1 else ''}")
        return ""

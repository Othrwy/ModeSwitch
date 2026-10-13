"""
Small time and colour helpers shared across the app.
Times are handled as minutes since midnight and stored as "HH:MM".
"""
from __future__ import annotations

from datetime import datetime

DAY_MAX = 1435   # 23:55 — latest time a node can sit at


def to_min(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def to_hhmm(mins: int) -> str:
    mins = max(0, min(1439, int(mins)))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def now_min() -> int:
    n = datetime.now()
    return n.hour * 60 + n.minute


def snap(minutes: float, step: int = 5) -> int:
    return int(round(minutes / step) * step)


def fmt_duration(minutes: int) -> str:
    minutes = max(0, int(minutes))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def fmt_signed(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{fmt_duration(abs(minutes))}"


def contrasting_text(hex_color: str) -> str:
    """Return black or white depending on background luminance."""
    c = hex_color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luminance > 140 else "#ffffff"

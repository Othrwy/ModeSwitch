"""
Colour themes: dark, light, and custom.

A theme is a set of named colours ("tokens"). Only a handful are picked by hand
(BASE_TOKENS); the rest (borders, muted text, hover, grid lines …) are derived from
them, so a custom theme stays consistent however the base colours are chosen. A
derived token can still be overridden in a custom theme.

Also here: the colour maths the custom-theme editor uses (mixing, shades,
colour-wheel harmonies, contrast), and applying a theme to the whole app.
"""
from __future__ import annotations

import colorsys
import json
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette

# ---------------------------------------------------------------------------
# Colour maths
# ---------------------------------------------------------------------------

def _rgb(hex_: str) -> tuple[float, float, float]:
    c = QColor(hex_)
    return c.redF(), c.greenF(), c.blueF()


def _hex(r: float, g: float, b: float) -> str:
    clamp = lambda v: max(0, min(255, round(v * 255)))
    return f"#{clamp(r):02x}{clamp(g):02x}{clamp(b):02x}"


def mix(a: str, b: str, t: float) -> str:
    """t of the way from colour a to colour b."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return _hex(ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t)


def lightness(hex_: str) -> float:
    return colorsys.rgb_to_hls(*_rgb(hex_))[1]


def with_lightness(hex_: str, l: float) -> str:
    h, _, s = colorsys.rgb_to_hls(*_rgb(hex_))
    return _hex(*colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s))


def shades(hex_: str, steps: int = 9) -> list[str]:
    """The same hue from dark to light: for shadows, borders and highlights."""
    return [with_lightness(hex_, 0.08 + 0.84 * i / (steps - 1)) for i in range(steps)]


def rotate_hue(hex_: str, degrees: float) -> str:
    h, l, s = colorsys.rgb_to_hls(*_rgb(hex_))
    return _hex(*colorsys.hls_to_rgb((h + degrees / 360) % 1.0, l, s))


def harmonies(hex_: str) -> list[tuple[str, list[str]]]:
    """Colour-wheel matches for a colour: (name, colours)."""
    return [
        ("Complementary", [rotate_hue(hex_, 180)]),
        ("Analogous", [rotate_hue(hex_, -30), rotate_hue(hex_, 30)]),
        ("Triadic", [rotate_hue(hex_, 120), rotate_hue(hex_, 240)]),
        ("Split complementary", [rotate_hue(hex_, 150), rotate_hue(hex_, 210)]),
    ]


def _luminance(hex_: str) -> float:
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio, 1 to 21. 4.5 or more is comfortable for small text."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def nudge(hex_: str, amount: float) -> str:
    """Slightly lighter on a dark colour, slightly darker on a light one."""
    l = lightness(hex_)
    return with_lightness(hex_, l + amount if l < 0.5 else l - amount)


def extend(a: str, b: str, n: float) -> str:
    """n steps of the way from a towards b, where b is one step; can go past b."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return _hex(ra + (rb - ra) * n, ga + (gb - ga) * n, ba + (bb - ba) * n)


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

# (token, label, group). Picked by hand in a custom theme.
BASE_TOKENS: list[tuple[str, str, str]] = [
    ("bg", "Background", "Base"),
    ("surface", "Panels, boxes and buttons", "Base"),
    ("text", "Text", "Base"),
    ("accent", "Accent (selection, focus)", "Base"),
    ("credit", "Credit and overtime", "Status"),
    ("debit", "Debit", "Status"),
    ("now_line", "Current time line", "Timeline"),
    ("node", "Nodes", "Timeline"),
    ("meeting_past", "Meeting, finished", "Meetings"),
    ("meeting_later", "Meeting, later today", "Meetings"),
    ("meeting_soon", "Meeting, starting soon (pulses)", "Meetings"),
    ("meeting_now", "Meeting, on now", "Meetings"),
]

# Worked out from the base tokens unless overridden.
DERIVED_TOKENS: dict[str, tuple[str, Callable[[dict], str]]] = {
    "muted": ("Secondary text", lambda t: mix(t["text"], t["bg"], 0.3)),
    "faint": ("Faint text and off icons", lambda t: mix(t["text"], t["bg"], 0.55)),
    "border": ("Borders", lambda t: mix(t["surface"], t["text"], 0.25)),
    "hover": ("Button hover", lambda t: nudge(t["surface"], 0.07)),
    "pressed": ("Button pressed", lambda t: nudge(t["surface"], 0.14)),
    "grid": ("Chart grid lines", lambda t: mix(t["bg"], t["text"], 0.12)),
    "track": ("Unassigned time on the slider", lambda t: mix(t["bg"], t["text"], 0.22)),
    "week_alt": ("Last week's shading (older weeks go further)",
                 lambda t: nudge(t["bg"], 0.03)),
}

DARK = {
    "bg": "#1e1e1e", "surface": "#2d2d2d", "text": "#e0e0e0", "accent": "#4a90d9",
    "credit": "#f4a261", "debit": "#e07070",
    "now_line": "#ffffff", "node": "#ffffff",
    "meeting_past": "#808080", "meeting_later": "#8b0000",
    "meeting_soon": "#dc2828", "meeting_now": "#c81e1e",
}

LIGHT = {
    "bg": "#f4f4f2", "surface": "#ffffff", "text": "#1f1f1f", "accent": "#2f6fb5",
    "credit": "#c96a1b", "debit": "#c0392b",
    "now_line": "#1f1f1f", "node": "#3a3a3a",
    "meeting_past": "#9a9a9a", "meeting_later": "#b23a3a",
    "meeting_soon": "#e53935", "meeting_now": "#d32f2f",
}

PRESETS = {"dark": DARK, "light": LIGHT}


def resolve(overrides: dict, preset: str = "dark") -> dict:
    """Every token's colour: the preset, then overrides, then derived ones filled in."""
    tokens = dict(PRESETS.get(preset, DARK))
    tokens.update({k: v for k, v in overrides.items() if k in tokens})
    for key, (_, rule) in DERIVED_TOKENS.items():
        tokens[key] = overrides.get(key) or rule(tokens)
    return tokens


# ---------------------------------------------------------------------------
# The active theme
# ---------------------------------------------------------------------------

class _Theme:
    def __init__(self):
        self.name = "dark"
        self.tokens = resolve({})

    def __getattr__(self, key: str) -> str:
        try:
            return self.__dict__["tokens"][key]
        except KeyError:
            raise AttributeError(key)

    def q(self, key: str, alpha: Optional[int] = None) -> QColor:
        c = QColor(self.tokens[key])
        if alpha is not None:
            c.setAlpha(alpha)
        return c

    def week_shade(self, weeks_back: int) -> str:
        """Background for a week in the review panel: plain for the newest, then a
        step further from the background (lighter in a dark theme, darker in a light one)
        for each week back."""
        return extend(self.tokens["bg"], self.tokens["week_alt"], weeks_back)

    @property
    def is_dark(self) -> bool:
        return lightness(self.tokens["bg"]) < 0.5


current = _Theme()


class _Hub(QObject):
    """Settings or the theme changed; windows refresh themselves."""
    settings_changed = pyqtSignal()
    projects_changed = pyqtSignal()   # a project or subtask was added outside the review panel


_hub: Optional[_Hub] = None


def hub() -> _Hub:
    global _hub
    if _hub is None:
        _hub = _Hub()
    return _hub


def load() -> None:
    """Read the chosen theme from settings into `current`."""
    from modeswitch.db import models
    name = models.get_setting("theme", "dark")
    if name == "custom":
        try:
            custom = json.loads(models.get_setting("theme_custom", "{}"))
        except ValueError:
            custom = {}
        current.tokens = resolve(custom.get("tokens", {}), custom.get("base", "dark"))
    else:
        current.tokens = resolve({}, name)
    current.name = name


def apply(app) -> None:
    """Load the theme and restyle the whole app with it."""
    load()
    t = current
    pal = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.Base, "bg"),
                      (QPalette.ColorRole.AlternateBase, "surface"),
                      (QPalette.ColorRole.Button, "surface"),
                      (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.Text, "text"),
                      (QPalette.ColorRole.ButtonText, "text"),
                      (QPalette.ColorRole.ToolTipBase, "surface"),
                      (QPalette.ColorRole.ToolTipText, "text"),
                      (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.PlaceholderText, "faint")):
        pal.setColor(role, t.q(key))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(
        "#000000" if lightness(t.accent) > 0.6 else "#ffffff"))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())


def stylesheet() -> str:
    t = current
    return f"""
        QWidget {{
            color: {t.text};
            font-family: "Segoe UI", sans-serif;
            font-size: 12px;
        }}
        QDialog, QMenu {{ background-color: {t.bg}; }}
        QLabel[role="muted"] {{ color: {t.muted}; }}
        QLabel[role="faint"] {{ color: {t.faint}; }}
        QLabel[role="strong"] {{ color: {t.text}; }}
        QLineEdit, QSpinBox, QComboBox, QTimeEdit {{
            background: {t.surface};
            border: 1px solid {t.border};
            border-radius: 4px;
            padding: 3px 6px;
            color: {t.text};
        }}
        QLineEdit:focus, QSpinBox:focus, QTimeEdit:focus, QComboBox:focus {{
            border: 1px solid {t.accent};
        }}
        /* Styled spin boxes lose their native arrows; type or use the mouse wheel */
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
        QComboBox QAbstractItemView {{
            background: {t.surface};
            selection-background-color: {t.accent};
        }}
        QPushButton, QToolButton {{
            background: {t.surface};
            color: {t.text};
            border: 1px solid {t.border};
            border-radius: 4px;
            padding: 5px 10px;
        }}
        QToolButton {{ padding: 0; }}
        QPushButton:hover, QToolButton:hover {{ background: {t.hover}; }}
        QPushButton:pressed, QPushButton:checked, QToolButton:checked {{ background: {t.pressed}; }}
        QPushButton:disabled {{ color: {t.faint}; }}
        QScrollArea, QScrollBar {{ background: {t.bg}; border: none; }}
        QGroupBox {{
            border: 1px solid {t.border};
            border-radius: 5px;
            margin-top: 8px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            color: {t.muted};
        }}
        QFrame#weekSeparator {{ background: {t.border}; }}
        QFrame#divider {{ background: {t.border}; }}
        QTableWidget {{
            background: {t.surface};
            gridline-color: {t.grid};
            border: 1px solid {t.border};
        }}
        QHeaderView::section {{
            background: {t.bg};
            color: {t.muted};
            border: none;
            padding: 4px;
        }}
        QMenu {{ border: 1px solid {t.border}; }}
        QMenu::item {{ padding: 4px 18px; }}
        QMenu::item:selected {{ background: {t.hover}; }}
        QMenu::item:disabled {{ color: {t.faint}; }}
        QToolTip {{
            background: {t.surface};
            color: {t.text};
            border: 1px solid {t.border};
        }}
    """

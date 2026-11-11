"""
Colour picker with help choosing colours that go together.

  • Lighter and darker — the same hue in steps, for shadows, borders and highlights
  • Goes with …       — colour-wheel matches (complementary, analogous, triadic,
                        split complementary) for a reference colour
  • In use            — colours already used by projects and the theme, to reuse
  • Readability       — contrast against the background, where that matters
  • More…             — the full Windows colour dialog
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QToolButton, QVBoxLayout, QWidget
)

from modeswitch import theme as theme_mod
from modeswitch.theme import current as theme

SWATCH = 22


def colours_in_use() -> list[str]:
    from modeswitch import days
    from modeswitch.db import models
    seen, out = set(), []
    for c in ([p.color for p in models.get_all_projects()] + list(days.kind_colors().values())
              + [theme.tokens[k] for k, _, _ in theme_mod.BASE_TOKENS]):
        c = QColor(c).name()
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:16]


class ColourPicker(QDialog):
    def __init__(self, parent, initial: str, title: str,
                 reference: Optional[str] = None, contrast_against: Optional[str] = None,
                 reference_name: str = "the accent colour"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._colour = QColor(initial).name()
        self._reference = reference or theme.accent
        self._reference_name = reference_name
        self._contrast_against = contrast_against

        root = QVBoxLayout(self)
        root.setSpacing(10)

        top = QHBoxLayout()
        self._preview = QLabel()
        self._preview.setFixedSize(64, 40)
        top.addWidget(self._preview)
        self._hex = QLineEdit()
        self._hex.setMaxLength(7)
        self._hex.setFixedWidth(90)
        self._hex.editingFinished.connect(self._on_hex)
        top.addWidget(self._hex)
        self._contrast = QLabel()
        self._contrast.setProperty("role", "muted")
        top.addWidget(self._contrast, stretch=1)
        root.addLayout(top)

        self._shades_row = self._row(root, "Lighter and darker")
        self._harmony_grid = QGridLayout()
        self._harmony_grid.setHorizontalSpacing(4)
        heading = QHBoxLayout()
        label = QLabel(f"Goes with {self._reference_name}")
        label.setProperty("role", "muted")
        heading.addWidget(label)
        ref = QLabel()
        ref.setFixedSize(14, 14)
        ref.setStyleSheet(f"background: {self._reference}; border: 1px solid {theme.border};"
                          f" border-radius: 2px;")
        heading.addWidget(ref)
        heading.addStretch()
        root.addLayout(heading)
        root.addLayout(self._harmony_grid)
        self._in_use_row = self._row(root, "In use")

        buttons = QHBoxLayout()
        more = QPushButton("More…")
        more.setToolTip("Open the full Windows colour dialog")
        more.clicked.connect(self._more)
        buttons.addWidget(more)
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)

        self._fill_harmonies()
        self._fill_row(self._in_use_row, colours_in_use())
        self._set(self._colour)

    # ------------------------------------------------------------------
    def colour(self) -> str:
        return self._colour

    @staticmethod
    def _row(root: QVBoxLayout, title: str) -> QHBoxLayout:
        label = QLabel(title)
        label.setProperty("role", "muted")
        root.addWidget(label)
        row = QHBoxLayout()
        row.setSpacing(4)
        root.addLayout(row)
        return row

    def _swatch(self, colour: str) -> QToolButton:
        b = QToolButton()
        b.setFixedSize(SWATCH, SWATCH)
        b.setToolTip(colour)
        b.setStyleSheet(f"QToolButton {{ background: {colour}; border: 1px solid {theme.border};"
                        f" border-radius: 3px; }}"
                        f"QToolButton:hover {{ border: 2px solid {theme.text}; }}")
        b.clicked.connect(lambda: self._set(colour))
        return b

    def _fill_row(self, row: QHBoxLayout, colours: list[str]) -> None:
        while row.count():
            item = row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for c in colours:
            row.addWidget(self._swatch(c))
        row.addStretch()

    def _fill_harmonies(self) -> None:
        for r, (name, colours) in enumerate(theme_mod.harmonies(self._reference)):
            label = QLabel(name)
            label.setProperty("role", "faint")
            self._harmony_grid.addWidget(label, r, 0)
            for c, colour in enumerate(colours):
                self._harmony_grid.addWidget(self._swatch(colour), r, c + 1)
        self._harmony_grid.setColumnStretch(4, 1)

    def _set(self, colour: str) -> None:
        self._colour = QColor(colour).name()
        self._preview.setStyleSheet(f"background: {self._colour}; border: 1px solid {theme.border};"
                                    f" border-radius: 4px;")
        self._hex.setText(self._colour)
        self._fill_row(self._shades_row, theme_mod.shades(self._colour))
        if self._contrast_against:
            ratio = theme_mod.contrast(self._colour, self._contrast_against)
            verdict = ("easy to read" if ratio >= 4.5 else
                       "fine for large text" if ratio >= 3 else "hard to read")
            self._contrast.setText(f"Contrast {ratio:.1f} : 1 — {verdict}")

    def _on_hex(self) -> None:
        text = self._hex.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        if QColor.isValidColorName(text):
            self._set(text)
        else:
            self._hex.setText(self._colour)

    def _more(self) -> None:
        c = QColorDialog.getColor(QColor(self._colour), self, self.windowTitle())
        if c.isValid():
            self._set(c.name())


def pick_colour(parent: QWidget, initial: str, title: str = "Choose colour",
                reference: Optional[str] = None,
                contrast_against: Optional[str] = None,
                reference_name: str = "the accent colour") -> Optional[str]:
    """The chosen colour as '#rrggbb', or None if cancelled."""
    dlg = ColourPicker(parent, initial, title, reference, contrast_against, reference_name)
    return dlg.colour() if dlg.exec() else None

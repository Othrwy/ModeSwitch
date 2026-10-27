"""
Custom theme editor.

The base colours are picked by hand; everything else is worked out from them
(theme.DERIVED_TOKENS) so the theme stays consistent. Each worked-out colour has
an Auto tick: untick it to choose that colour yourself.

A custom theme is stored as {"base": "dark" | "light", "tokens": {token: "#rrggbb"}}:
the preset it started from, plus whatever was changed.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget
)

from modeswitch import theme as theme_mod
from modeswitch.dialogs.colour_picker import pick_colour

# Tokens that are drawn as text on the background: show readability when picking them
TEXT_TOKENS = {"text", "muted", "faint", "credit", "debit"}


class ThemeEditor(QDialog):
    def __init__(self, parent, custom: dict):
        super().__init__(parent)
        self.setWindowTitle("Custom colours")
        self.setModal(True)
        self.resize(460, 620)
        self._base = custom.get("base", "dark")
        self._tokens: dict[str, str] = dict(custom.get("tokens", {}))

        root = QVBoxLayout(self)
        start = QHBoxLayout()
        label = QLabel("Start again from")
        label.setProperty("role", "muted")
        start.addWidget(label)
        for key, name in (("dark", "Dark"), ("light", "Light")):
            b = QPushButton(name)
            b.setToolTip(f"Reset every colour to the {name.lower()} theme")
            b.clicked.connect(lambda _, k=key: self._restart(k))
            start.addWidget(b)
        start.addStretch()
        root.addLayout(start)

        self._readability = QLabel()
        self._readability.setProperty("role", "muted")
        root.addWidget(self._readability)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._grid = QGridLayout(body)
        self._grid.setColumnStretch(0, 1)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)

        self._rebuild()

    def result_theme(self) -> dict:
        return {"base": self._base, "tokens": self._tokens}

    def _resolved(self) -> dict:
        return theme_mod.resolve(self._tokens, self._base)

    # ------------------------------------------------------------------
    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        resolved = self._resolved()
        row = 0
        group = None
        for key, label, grp in theme_mod.BASE_TOKENS:
            if grp != group:
                row = self._heading(grp, row)
                group = grp
            self._grid.addWidget(QLabel(label), row, 0)
            self._grid.addWidget(self._swatch(key, resolved[key]), row, 1)
            row += 1

        row = self._heading("Worked out from the colours above", row)
        for key, (label, _) in theme_mod.DERIVED_TOKENS.items():
            self._grid.addWidget(QLabel(label), row, 0)
            self._grid.addWidget(self._swatch(key, resolved[key]), row, 1)
            auto = QCheckBox("Auto")
            auto.setChecked(key not in self._tokens)
            auto.setToolTip("Work this colour out from the ones above. Untick to pick it"
                            " yourself")
            auto.toggled.connect(lambda on, k=key: self._set_auto(k, on))
            self._grid.addWidget(auto, row, 2)
            row += 1
        self._grid.setRowStretch(row, 1)

        ratio = theme_mod.contrast(resolved["text"], resolved["bg"])
        verdict = "easy to read" if ratio >= 4.5 else "hard to read; pick more contrast"
        self._readability.setText(f"Text on background: contrast {ratio:.1f} : 1, {verdict}")

    def _heading(self, text: str, row: int) -> int:
        label = QLabel(text)
        label.setProperty("role", "muted")
        label.setStyleSheet("font-weight: 600; padding-top: 8px;")
        self._grid.addWidget(label, row, 0, 1, 3)
        return row + 1

    def _swatch(self, key: str, colour: str) -> QPushButton:
        b = QPushButton()
        b.setFixedSize(56, 22)
        b.setToolTip(f"{colour}, click to change")
        b.setStyleSheet(f"background: {colour}; border: 1px solid #888; border-radius: 3px;")
        b.clicked.connect(lambda: self._pick(key))
        return b

    def _pick(self, key: str) -> None:
        resolved = self._resolved()
        against = resolved["bg"] if key in TEXT_TOKENS else (
            resolved["text"] if key in ("bg", "surface") else None)
        # Harmonies are offered around the accent; for the accent itself, around the background
        reference = resolved["bg"] if key == "accent" else resolved["accent"]
        ref_name = "the background" if key == "accent" else "the accent colour"
        colour = pick_colour(self, resolved[key], f"Colour: {key}", reference, against, ref_name)
        if colour:
            self._tokens[key] = colour
            self._rebuild()

    def _set_auto(self, key: str, on: bool) -> None:
        if on:
            self._tokens.pop(key, None)
        else:
            self._tokens[key] = self._resolved()[key]
        self._rebuild()

    def _restart(self, base: str) -> None:
        self._base = base
        self._tokens = {}
        self._rebuild()

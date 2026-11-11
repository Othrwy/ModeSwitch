"""
TimeInputWidget — a QLineEdit that parses shorthand time entry.

Rules:
  "9"    → 09:00
  "10"   → 10:00
  "930"  → 09:30
  "1730" → 17:30
  "0930" → 09:30

Emits time_changed(str) with a validated "HH:MM" string.
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLineEdit


def parse_time_input(text: str) -> str | None:
    """
    Convert shorthand text to 'HH:MM'. Returns None if unparseable or invalid.
    """
    t = text.strip().replace(":", "")
    if not t.isdigit():
        return None

    if len(t) == 1:
        hh, mm = int(t), 0
    elif len(t) == 2:
        hh, mm = int(t), 0
    elif len(t) == 3:
        hh, mm = int(t[0]), int(t[1:3])
    elif len(t) == 4:
        hh, mm = int(t[:2]), int(t[2:])
    else:
        return None

    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None

    return f"{hh:02d}:{mm:02d}"


class TimeInputWidget(QLineEdit):
    time_changed = pyqtSignal(str)   # emits validated "HH:MM"

    def __init__(self, parent=None, placeholder: str = "HH:MM"):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMaxLength(5)
        self.setFixedWidth(70)
        self.returnPressed.connect(self._commit)
        self.editingFinished.connect(self._commit)

    # ------------------------------------------------------------------
    def set_time(self, hhmm: str | None) -> None:
        """Set the displayed value without triggering time_changed."""
        self.blockSignals(True)
        self.setText(hhmm or "")
        self.blockSignals(False)

    def get_time(self) -> str | None:
        """Return current text as 'HH:MM' or None if blank/invalid."""
        t = self.text().strip()
        if not t:
            return None
        return parse_time_input(t) or t  # return as-is if already HH:MM

    # ------------------------------------------------------------------
    def _commit(self) -> None:
        t = self.text().strip()
        if not t:
            return
        parsed = parse_time_input(t)
        if parsed:
            self.blockSignals(True)
            self.setText(parsed)
            self.blockSignals(False)
            self.time_changed.emit(parsed)
        else:
            # Highlight invalid input
            self.setStyleSheet("border: 1px solid red;")

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selectAll()

    def focusOutEvent(self, event):
        self._commit()
        super().focusOutEvent(event)

    def focusInEvent(self, event):
        self.setStyleSheet("")  # clear any error highlight
        super().focusInEvent(event)
        # Select all after the focus event is fully processed
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)

"""
Getting started — what ModeSwitch is for, what it does, how to drive it, and the
first things to set up. Shown once on a brand-new user's first launch, and from the
tray menu and Settings after that.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout

from modeswitch.theme import current as theme


def guide_html() -> str:
    t = theme
    return f"""
<style>
  body {{ color: {t.text}; font-family: 'Segoe UI'; font-size: 10pt; }}
  h2 {{ margin: 0 0 4px 0; }}
  h3 {{ margin: 14px 0 4px 0; color: {t.text}; }}
  p, li {{ margin: 2px 0; }}
  .muted {{ color: {t.muted}; }}
  td {{ padding: 2px 10px 2px 0; vertical-align: top; }}
  td.key {{ color: {t.muted}; white-space: nowrap; }}
</style>
<h2>ModeSwitch</h2>
<p>ModeSwitch logs which project your attention is on through the working day, so
your timesheet can be read straight off at the end of the day or week. It sits as a
thin ribbon down the edge of your screen.</p>

<h3>How it works</h3>
<p>Your day is a vertical timeline, from when the laptop came on at the top to the end
of your working day at the bottom. It is split into <b>sections</b>, each with a
project code. There are no gaps and no overlaps: one thing at a time, every minute
accounted for. Your Outlook meetings are drawn faintly behind it, as a guide to draw
against. They are not the log; what you actually spent the time on is.</p>

<h3>What it does</h3>
<ul>
  <li><b>Start and end of day.</b> The start comes from when the laptop was switched
      on. The end sits on your hours plus lunch, and follows the clock if you stay
      late.</li>
  <li><b>Credit.</b> Time over or under your working day, as a running balance.</li>
  <li><b>Outlook meetings</b> behind the timeline, pulsing red 30 minutes before they
      start.</li>
  <li><b>Smart defaults.</b> Give a meeting's section a project once, and meetings with
      that title get it automatically from then on.</li>
  <li><b>Subtasks</b> under each project, for finer detail.</li>
  <li><b>Lunch, commute and work from home</b> toggles, and Break projects that do not
      count as work.</li>
  <li><b>Review</b> panel: the last four weeks, all editable, with your projects and
      a tracker chart of credit, one project, or all projects by week, fortnight,
      month or an average day.</li>
  <li>Docks to the left or right edge of any monitor and keeps that strip to itself.
      Minimises to a thin slider: click the top corner or the very edge of the
      screen.</li>
  <li>Dark, light or your own colours.</li>
</ul>

<h3>Driving the timeline</h3>
<table>
  <tr><td class="key">Drag a dot</td><td>Move a start or end time. Hold Alt to jump to
      meeting starts and ends.</td></tr>
  <tr><td class="key">Drag a section</td><td>Slide it, keeping its length.</td></tr>
  <tr><td class="key">Double-click</td><td>Split a section in two.</td></tr>
  <tr><td class="key">Click a code box</td><td>Pick the project.</td></tr>
  <tr><td class="key">Right-click</td><td>Subtask, split, delete, and unlocking the end
      of day to leave early.</td></tr>
  <tr><td class="key">Click a time</td><td>Type it: <span class="muted">930</span> means
      09:30.</td></tr>
  <tr><td class="key">Hover a meeting</td><td>See its title (every title, where meetings
      overlap).</td></tr>
</table>
<p class="muted">Rest the mouse on any button for a moment to see what it does.</p>

<h3>First steps</h3>
<ol>
  <li><b>Settings</b> (tray icon, or ⚙ in Review): your working days, hours, lunch and
      commute.</li>
  <li><b>Connect to Outlook</b>, so your meetings show.</li>
  <li>In <b>Review</b>, <b>+ Add project</b> for each project code you book time to.</li>
  <li>Through the day, split the timeline where you switch tasks and pick a code for
      each section.</li>
</ol>
<p class="muted">Everything is stored on this computer only, in
%LOCALAPPDATA%\\ModeSwitch.</p>
"""


class GuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Getting started with ModeSwitch")
        self.resize(560, 640)
        layout = QVBoxLayout(self)
        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(guide_html())
        layout.addWidget(text, stretch=1)

        buttons = QHBoxLayout()
        outlook = QPushButton("Connect to Outlook…")
        outlook.setToolTip("Set up reading your calendar")
        outlook.clicked.connect(self._open_outlook)
        buttons.addWidget(outlook)
        settings = QPushButton("⚙ Settings")
        settings.setToolTip("Working days, hours, lunch, commute and appearance")
        settings.clicked.connect(self._open_settings)
        buttons.addWidget(settings)
        buttons.addStretch()
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _open_outlook(self) -> None:
        from modeswitch.dialogs.outlook_setup import OutlookSetupDialog
        OutlookSetupDialog(self).exec()

    def _open_settings(self) -> None:
        from modeswitch.windows.settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

# ModeSwitch

Read [SPEC.md](SPEC.md) before doing any work in this repo. It is the source of truth for requirements, decisions and open questions.

- Items marked **[decided]** in the spec come from Patrick; do not change them without asking.
- When Patrick makes a decision or states a preference, update the relevant section of SPEC.md and add a line to its decision log in the same change.
- When an open question is answered, remove it from the open questions list and update the requirement it relates to.

Run the app with `.venv\Scripts\python.exe main.py`. It uses the real database in `%LOCALAPPDATA%\ModeSwitch`; set `MODESWITCH_DB` to a scratch file when testing.

To check UI changes without touching the screen, run with `QT_QPA_PLATFORM=offscreen` and `QT_QPA_FONTDIR=C:\Windows\Fonts`, then save `widget.grab()` to a PNG and look at it.

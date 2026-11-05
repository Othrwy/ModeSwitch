# ModeSwitch

ModeSwitch logs which project your attention is on through the working day, so your timesheet can be read straight off at the end of the day or week. It sits as a thin ribbon down the edge of your screen, with your Outlook meetings drawn behind the day as a guide.

## What it does

- **A day timeline.** Your day runs top to bottom, split into sections, each with a project code. Drag, split and assign as you go. There are no gaps and no overlaps.
- **Start and end of day.** The start comes from when the laptop was switched on. The end sits on your hours plus lunch, and follows the clock if you stay late.
- **Credit.** Time over or under your working day, kept as a running balance.
- **Outlook meetings** behind the timeline, pulsing red 30 minutes before they start. This reads through classic Outlook, so it needs no admin approval.
- **Smart defaults.** Give a meeting's section a project once, and meetings with that title get it automatically from then on.
- **Subtasks**, **lunch / commute / work-from-home** toggles, and **Break** projects that do not count as work.
- **Review panel.** The last four weeks, all editable, with a tracker chart: credit, one project, or all projects by week, fortnight, month or an average day.
- Docks to any monitor edge and keeps that strip to itself. Minimises to a thin slider.

## Install

You need Windows 10 or 11, [Python 3.11](https://www.python.org/downloads/) and Git. For the calendar you also need classic Outlook (it comes with Microsoft 365 Apps), signed in once.

```
git clone https://github.com/PatMoore-Othrwy/ModeSwitch.git
cd ModeSwitch
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw.exe main.py
```

ModeSwitch appears as a ribbon on the right edge of your main screen, with an icon in the system tray.

## First steps

1. **Getting started** opens by itself on first launch. It is also in the tray menu, and in Settings.
2. **Settings** (tray icon, or ⚙ in Review): set your working days, hours, lunch and commute. The defaults are one person's week (Monday to Thursday), so check them.
3. **Connect to Outlook** (in Settings): it checks each step, says how to fix anything missing, and tests the connection.
4. In **Review**, click **+ Add project** for each project code you book time to.
5. **Launch when Windows starts** is in Settings. It also starts ModeSwitch when you unlock or wake the laptop.

Rest the mouse on any button for a moment to see what it does.

## Your data

Your log stays on your computer, in `%LOCALAPPDATA%\ModeSwitch\modeswitch.db`, and is never sent anywhere.

For how it is meant to behave in detail, see [SPEC.md](SPEC.md).

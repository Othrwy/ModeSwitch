# ModeSwitch — Specification

**Status:** v2 ribbon, timeline and review panel built (2026-10-13). Minimise, per-day project totals in review, and autostart added (2026-10-20). Ribbon reserves its screen space and can be dragged to any monitor edge (2026-10-21). Outlook sync working through classic Outlook (2026-10-22); Microsoft Graph route built but waiting on IT admin consent. Themes, fuller Settings and a multi-purpose tracker chart added (2026-10-27). End of day locked to the 8h mark, with a hollow node marking the mark, and Break projects that count like lunch (2026-11-02). Autostart on wake and unlock (2026-11-03). Minimise from the screen corner and edge; tracker bar view and all-projects view; overlapping meetings, Connect to Outlook page and Getting started guide (2026-11-05). Last updated 2026-11-05.

This file is the source of truth for what ModeSwitch is meant to do. Read it before changing the code. When a decision is made or a preference stated, record it here (section 11) in the same change as the code.

Markers used below:

- **[decided]** — stated by Patrick. Do not change without asking.
- **[assumed]** — a gap filled in by Claude. Safe to build on, but Patrick has not confirmed it.
- **[open]** — needs an answer before that part is built. Collected in section 10.

---

## 1. Purpose

ModeSwitch is a personal Windows desktop tool for logging which project Patrick's attention is on through the working day, so that time per project code can be read off at the end of the day or week. It also tracks arrival, lunch, departure, and the running credit or debit against an 8-hour day.

It records what the time was **actually spent on**. Only one thing can be logged at any moment, so sections never overlap **[decided]**. The calendar is a guide to draw against, not the log itself.

What carries over from v1 **[decided]**: the principle — a day made of time blocks, each assigned to a project, with in / lunch / out times and credits — and any v1 functions and fields that still apply (section 12).

What changes in v2 **[decided]**: the UI becomes a vertical ribbon with a draggable day timeline, and Outlook meetings are shown behind it.

## 2. Platform and stack

- Windows 11, single user, single machine.
- Python 3.11, PyQt6, SQLite, pywin32 (also reads the calendar through classic Outlook), msal (Microsoft sign-in, for the dormant Graph route). Packaged with PyInstaller. **[assumed: v2 keeps this stack]**
- Database at `%LOCALAPPDATA%\ModeSwitch\modeswitch.db`.
- Runs from the system tray. **[decided]** The tray and window icon is two green triangles, drawn from Patrick's reference picture. The top one sits against the right edge pointing left, the bottom one against the left edge pointing right, and the dark gap between them makes a rough S. **[assumed]** Green `#26e600` with rounded corners on a dark (`#191a1b`) rounded tile, so it shows on light and dark taskbars. Drawn in code at each size, so it stays sharp at any display scaling.
- **[decided]** Starts automatically when Patrick logs in to Windows, and also when the laptop is unlocked or wakes from sleep or hibernation, if it is not already running (added 2026-11-03: the laptop often sleeps instead of shutting down, so there is no fresh logon). Starting on wake must not change how the start of day is found (D1); it does not, because the start time comes from the event log, not from when the app opens. Toggled in Settings. **[assumed]** Done with a Windows scheduled task named `ModeSwitch` for this user (logon, unlock and Power-Troubleshooter event 1 triggers; ignores a trigger while already running; runs on battery). It replaced the Startup-folder shortcut, and an old shortcut is swapped for the task on launch. A named mutex makes any second copy exit at once. When run from source the task launches `.venv\Scripts\pythonw.exe main.py`, so no console window is left open.

## 3. The ribbon window

- **R1 [decided]** A vertical ribbon docked along the left or right edge of a monitor (right edge of the main screen by default), about 160px wide.
- **R2 [decided]** It reserves its strip of the screen, as if its inner edge were the edge of the screen: other windows snap to it instead of going behind it, and when it is minimised or expanded, maximised and snapped windows on that monitor shrink or grow with it.
- **R2a [assumed]** Done by registering as a Windows app bar (`SHAppBarMessage`), the same mechanism as the taskbar. Windows resizes maximised and snapped windows when the reserved space changes; ordinary free-floating windows are not moved. Frameless, full height of the work area, always on top, but it steps behind full-screen apps (presentations, full-screen video). The space is given back when the ribbon is hidden from the tray or the app exits.
- **R8 [decided]** The ribbon can be moved to the left or right edge of any monitor by dragging it by its header. On release it snaps to the nearest vertical edge.
- **R8a [assumed]** The nearest edge is whichever side of the monitor under the cursor the cursor is on. A highlighted outline shows where it will land while dragging. The chosen monitor and edge are remembered (`dock_screen`, `dock_edge` settings); if that monitor is not connected, it docks on the main screen and moves back when the monitor returns. It cannot be dragged while minimised, because the header is hidden. The minimise arrow points toward the edge.
- **R3 [decided]** Top-left: a small house-icon button toggling "working from home" for the day (section 6).
- **R3a [decided]** Beside it, a small sandwich-icon button toggling lunch on or off for the day (T21b). The icon is a sandwich wedge drawn from Patrick's reference picture: a peach triangle of bread on top, then the crust, lettuce, a sliver of filling with tomato on the right, and the bottom slice.
- **R4 [decided]** Main area: the day timeline (section 4).
- **R5 [decided]** Below the timeline: the project summary (section 7).
- **R6 [decided]** Very bottom: a Review button (section 8), with an arrow pointing the way the review panel opens (`◀ Review` when docked on the right, `Review ▶` on the left).
- **R7 [decided]** A minimise button collapses the ribbon to just the slider's width, still docked up the right edge. Clicking anywhere on the slider expands it again.
- **R7a [decided]** The minimise button is a small arrow at the top right, beside the date, pointing into the screen edge: `→` when docked on the right, `←` on the left. **[assumed]** Collapsed, the ribbon is 24px wide and shows sections, meetings, nodes and the now-line, with no text or boxes; hover tooltips still work, but nothing can be edited. Collapsing closes the review panel, and opening Review from the tray expands the ribbon. The collapsed state is remembered across restarts (`ribbon_collapsed` setting).
- **R7b [decided]** The minimise button works all the way up to the top corner of the screen, so it can be hit by throwing the mouse into the corner. The outermost column of pixels down the screen edge also minimises the ribbon when clicked. **[assumed]** The corner area is the button stretched up to the ribbon's top and out to its edge. The edge column toggles, so it also expands a minimised ribbon; while minimised, a click anywhere on the ribbon expands it. Docked on the left, the button stays at the top right (R7a), so its corner area is the ribbon's top-right corner, not the screen's; the edge column still works.
- **R9 [decided]** Every button and setting shows a short explanation of what it does when the mouse rests on it for a moment. **[assumed]** Qt's standard tooltip delay (about 0.7 s). **[decided]** The house button's tip is "Working From Home (Commute Toggle)" and the sandwich's is "Lunch Toggle". **[assumed]** The sun button describes its current state and what clicking will do; colour swatches show the colour's hex code.

Layout sketch (not to scale):

```
┌──────────────────────┐
│ [⌂]                  │
│                      │
│  08:30 ●             │
│  30m   │ [0000]      │
│  Daily │ [A]         │
│  09:00 ●             │
│  3h    │ [1234]      │
│        │ [A]         │
│  12:00 ●             │
│  1h    │             │
│  Lunch │             │
│  13:00 ●             │
│  ...   │             │
│  17:30 ●             │
│                      │
│ 0000 | 0h 30m | A    │
│ 1234 | 7h 30m | A    │
│ [      Review      ] │
└──────────────────────┘
```

## 4. The day timeline

### 4.1 Two layers

- **T1 [decided]** A vertical slider running top (start of day) to bottom (end of day).
- **T2 [decided]** **Background layer: Outlook meetings.** Meetings are drawn behind the slider as a guide. They are not sections, cannot be dragged or edited, and may overlap each other.
- **T3 [decided]** **Foreground layer: sections.** Sections are drawn by Patrick over the top of the background and are the actual time log.

### 4.2 Nodes and sections

- **T4 [decided]** **Nodes** mark the start and end times of sections. The top node of a section is its start time, the bottom node its end time.
- **T5 [decided]** A **section** is the span between two nodes: project time, lunch, or commute.
- **T6 [decided]** The timeline has no gaps and no overlaps. Time between the day's start node and end node that is not lunch or commute is a blank section that can be assigned to a project.
- **T7 [assumed]** Because there are no gaps, adjacent sections share a node. Moving it shortens one and lengthens the other.
- **T8 [assumed]** A new day starts as: (commute,) one blank section, lunch, one blank section (, commute). Patrick splits and drags from there.

### 4.3 What is drawn

- **T9 [decided]** Left of each node: the time at that node (HH:MM).
- **T10 [decided]** Left of each section: its duration (e.g. `1h 30m`), plus "Lunch" or "Commute" for those sections. Text wraps to fit within the section's height. Titles are **not** shown here (changed 2026-10-22; see T11).
- **T11 [decided]** Event titles only appear when the mouse is over the event, and only on the half of the timeline away from the screen edge (the left half when docked on the right, the right half when docked on the left). **[assumed]** The title appears instantly, in a small box drawn over the text column at the top of the meeting. Overlapping meetings are listed together (T15b). A section with a hand-typed title (from before subtasks replaced Set title, P2a) but no meeting shows that title the same way. Hover tooltips still give times, project and subtask anywhere, but no titles. When collapsed, titles come from the tooltip, on the inner half only.
- **T12 [decided]** Right of each section: a narrower column, just wide enough for a 4-digit project code in a small box.
- **T13 [decided]** ~~Below the code box: a small square box holding a single letter, A–D.~~ Replaced 2026-10-27 by subtasks (P2a). There is no box under the code box. **[assumed]** A section's subtask name is written in small muted text under the code box, cut short with … if it does not fit, and in full in the hover tooltip.
- **T14 [assumed]** A section's title comes from the background meeting it lines up with (same start and end, or the meeting covering most of the section). Sections with no matching meeting have no title.
- **T15 [assumed]** Sections are filled with the project's colour (the `color` field already exists on projects). Background meetings are drawn as translucent bands so the two layers are easy to tell apart.
- **T15a [decided]** Meeting colours: **grey** once a meeting has ended, **dark red** for later meetings, and a **pulsing red** for one starting within 30 minutes (T22). **[assumed]** A meeting that is on right now is a steady, brighter red. Every meeting on a past day is grey.
- **T15b [decided]** Overlapping meetings on busy days are shown by their translucency stacking, without adding clutter, and hovering must never let one meeting hide another. **[assumed]**
  - The overlap reads as a deeper band. Days without overlaps look the same as before.
  - A faint hairline marks each overlapping meeting's start and end, which would otherwise be lost inside the deeper band.
  - On the ribbon, the coloured strips down the meetings' left sides sit side by side in lanes (like a calendar's columns), showing how many there are and how far each runs.
  - Hovering picks meetings by the time under the mouse, not by which is drawn on top, so every meeting there is listed, earliest first. Each title has its start time on a muted line above it **[decided]**; where they overlap, that line gives the start and end, and each hovered meeting is outlined, nested a step in per lane, so its full extent shows.
- **T16 [assumed]** If a section is too short for the code box and the subtask name, the name is dropped and shown on hover. Below about 12px the code box is dropped too.
- **T16b [decided]** Today's timeline runs half an hour past the end of the day or the current time, whichever is later, so there is room to drag the end node down. **[assumed]** Past days in the review panel have no extra room; they share one time scale (V6).
- **T16a [decided]** A **white** tick on the slider marks the current time. **[assumed]** In the light theme it is near-black, so it stays visible; in a custom theme it is the "Current time line" colour.

### 4.4 Interactions

| Action | Result | Status |
|---|---|---|
| Drag a node | Moves that node only; the section's duration changes. The end-of-day node cannot be dragged while it is locked (D2b). Snaps to a grid (**5 min**), to the start or end of a background meeting when within **5 min** of it, and to the current time (T17a). Both distances are set in Settings. | decided |
| Drag a section body | Moves both its nodes together; duration stays fixed. Snaps to **15 min**. Neighbouring sections stretch or shrink to fit. | decided |
| Click the project code box | Dropdown to pick a project code. | decided |
| Double-click the section line | Splits the section in two. The existing project code stays on the **top** half. | decided |
| Right-click a section | Menu with Delete. The section **above** expands to fill the space. | decided |
| Right-click a section, including its project code box | **Assign subtask**: pick one of the project's subtasks from a dropdown, or **New subtask…** and type a name (P2a). The menu also offers Split here. | decided |
| Click a node's time | Type a time directly, using v1's shorthand entry (`930` → `09:30`). | assumed |

- **T17 [assumed]** When a meeting edge and the grid both apply, the meeting edge wins. Meeting snap applies to node drags only, not section-body drags. **[decided]** Holding **Alt** while dragging snaps only to meeting starts and ends from the calendar: the node jumps to whichever is nearest, however far away, ignoring the grid and the current time. **[assumed]** On a day with no meetings, Alt makes no difference. To place a node near a meeting edge without it jumping there, set the meeting-edge snap to Off in Settings.
- **T17a [decided]** On today's timeline, a node dragged near the current time snaps to the current time rather than the grid marks either side of it. **[assumed]** The current time is treated as one more snap point, and the node goes to whichever of the nearest grid mark and the current time is closer.
- **T17b [decided]** The grid step and the meeting-edge snap distance are set in Settings ("Dragging nodes"), both defaulting to **5 min**. The meeting-edge distance can be set to Off. **[assumed]** Section-body drags still snap to 15 min, as decided in the table above. The grid step also sets where a split lands.
- **T18 [assumed]** A split happens at the point clicked, snapped to 5 min. The new bottom half is unassigned, with no subtask.
- **T19 [assumed]** A node cannot be dragged past its neighbouring node; the minimum section length is 5 min.
- **T20 [assumed]** Deleting the first section of the day makes the section below expand instead, since there is nothing above (a commute above does not count). The last remaining project section cannot be deleted.
- **T20a [assumed]** Dragging the start-of-work or end-of-work node on a commute day carries the commute section with it at its current length. Dragging the commute's outer node changes the commute's length.
- **T21 [decided]** Lunch can be moved and resized. It cannot be split, or deleted from the right-click menu.
- **T21b [decided]** The sandwich button (R3a) takes lunch off a day, or puts it back. **[assumed]** Taken off, its time goes to the section above, the same as Delete (T20). Put back, it is a `lunch_minutes` block (1h) at 12:00, cut out of whatever sections are there. It is moved inside the working day if 12:00 does not fit. While the end time is still the computed default (D2), the end moves an hour earlier or later with it.
- **T21a [decided]** Moving lunch's start node moves its end node too, so the whole lunch slides and keeps its length. The end node still changes lunch's length. **[assumed]** This applies to typing a time into the start node as well as dragging it.

### 4.5 Upcoming-meeting alert

- **T22 [decided]** A meeting that starts within the next 30 minutes glows and pulses slightly to catch the eye, in red.
- **T23 [assumed]** The pulse is on the background meeting and stops once its start time has passed.

## 5. Day start, end, lunch and credits

- **D1 [decided]** Start time is auto-populated from when the laptop was turned on.
- **D2 [decided]** Once the start time is known, the day defaults to a 1-hour lunch and an 8-hour working day excluding lunch and breaks, so end = start + 8h + lunch + breaks (the **8h mark**). The end node updates as start, lunch or breaks change. Breaks are sections on a project that does not count as work (P10).
- **D2b [decided]** The end node is **locked** to the 8h mark by default, and stays on it as lunch and breaks change. Locked, it cannot be dragged or typed over. Past the mark it follows the clock (D2a). It can be unlocked to leave early, but must not be moved by accident. **[assumed]**
  - Lock and unlock with **Lock end of day to 8h mark** at the bottom of the timeline's right-click menu (today only). Locked, a small padlock shows beside the end node, and clicking or hovering the node explains how to unlock it.
  - Unlocked, the end behaves as a hand-set end (`manual` or `held`, D2a).
  - Whenever the end is not on the 8h mark (unlocked, or running over), a **hollow node** marks where the 8h mark is, with its time in faint text. Hovering it gives the time.
  - Dragging the end node near the hollow node snaps it there (within the larger of the grid step and the meeting-edge distance). Dropping it there, or typing that time, locks it again. The exception is when the mark has already passed: then dropping it there records stopping work at the mark (`held`).
  - Locked is stored as the existing `computed` end-time source. Other edits that would move a locked end, such as sliding the last section, leave the end on the mark.
  - When the app opens, or Settings or the Break tick box change, today's locked end is moved to the new mark.
- **D2a [decided]** If the current time goes past today's end node, the end node follows the clock: still at the computer means still working. The day's credit counts the extra time as it happens. This applies whether the end is locked (D2b) or was set by hand to a later time. **[assumed]** An end set by hand to a time already past (dragged or typed earlier than now, or saved on Exit) is **held**: it stays put, so "I stopped at 17:00" can be recorded while the laptop stays on. The end-time source is stored as `computed`, `manual` (set by hand, follows once passed), `held` or `detected`.
- **D3 [decided]** If Patrick does not set the end time himself, it is filled in from when the laptop was turned off.
- **D4 [assumed]** Precedence for the end time: set by hand > detected turn-off > computed default (D2). Dragging or typing the end node counts as setting it by hand, and so does answering Yes to "Save out time?" on Exit. Exit only asks when the end is not already held (D2a).
- **D5 [decided]** Leaving earlier or later than the 8-hour target is tracked as credits: credit = time worked − 8h, positive or negative.
- **D5a [decided]** The working-day length is set in Settings: one length for every day ("Same length every day", 8h by default), or, with that unticked, a length for each working day. A day's credit, its computed end time (D2) and the credit chart (V9a) all use that day's own length. **[assumed]** Changing the lengths re-reckons past days' credit too. It does not move past days' end times. Today's end moves only if it is locked (D2b).
- **D6 [decided]** Time worked = end − start − lunch − breaks. Commute does not count as work. Breaks are time on a project that does not count as work (P10).
- **D7 [decided]** Credits are tracked as a running balance on a chart in the review panel (V9a). The ribbon still shows today's time left, or today's credit once the end is real.

How on/off times are detected **[assumed]**:

- Start: the earliest boot, wake-from-sleep or logon in the Windows System event log for today, ignoring anything before 05:00 (the `day_floor` setting). If the log has nothing, the time the app launched.
- End: while running, the app stamps the day with a last-seen time every minute. On the next launch, any earlier day still on its computed end time gets its last-seen time as the end.
- While the end is still ahead of the clock, the ribbon shows "time left". Once the end is following the clock it shows "overtime: +…" (or the credit, if that is still negative). A held or detected end shows the day's credit.
- Whether sleep and lid-close count as "off" is **[open Q3]**. As built, the last-seen stamp simply stops when the machine sleeps.

## 6. Working from home and commute

- **W1 [decided]** The house button toggles WFH for the day. WFH means no commute sections.
- **W2 [decided]** Defaults: WFH on Monday, Tuesday and Thursday; commute on Wednesday.
- **W3 [decided]** Commute sections default to 1 hour each. The usual commute time (each way) is set in Settings, and so is the usual lunch length. **[assumed]** Both apply to new days and when a commute or lunch is added back to a day, not to days already logged.
- **W4 [decided]** On a commute day there are two commute sections: one ending at the day's start node, one beginning at the day's end node. They sit outside the 8 working hours.
- **W5 [assumed]** Working days are Monday to Thursday (the v1 `working_days` setting is `1,2,3,4`, and the review panel hides Friday to Sunday).

## 7. Projects, subtasks and the summary

- **P1 [decided]** Projects are identified by a 4-digit code (e.g. `0000`).
- **P2 [decided]** Each section carries one project code and, optionally, one subtask of that project (P2a). This replaced the letters A–D on 2026-10-27.
- **P2a [decided]** Subtasks are assigned by right-clicking a section's project code and choosing **Assign subtask**: pick an existing subtask of that project from a dropdown, or create one and type its name. They replace both the A–D letter box and the hand-typed section titles (Set title… is gone). **[assumed]**
  - A subtask belongs to one project, so changing a section's project clears its subtask. Assign subtask is greyed out on unassigned sections.
  - "None" in the dropdown takes the subtask off.
  - Subtasks can also be added, renamed and deleted in the review panel's project table (V7b). Deleting one leaves its sections on the project with no subtask.
  - Existing letters were converted once: B, C and D became subtasks of that name on their project, and A became no subtask. On this machine only A had been used, so nothing was converted.
- **P3 [decided]** ~~The letters A–D have no fixed meaning.~~ Superseded by subtasks (P2a), which are free text.
- **P4 [decided]** Smart defaults: the tool should know, for example, that the morning meeting titled "Daily" is `0000`.
- **P5 [assumed]** Smart defaults work as title rules: a case-insensitive match on a section's title (T14) maps to a project code and subtask. When Patrick assigns a code or subtask to a titled section by hand, that title is remembered and reused next time. **[decided]** There is no table for editing rules; they are only learned this way. Assigning a different project to the same title overwrites the rule.
- **P6 [assumed]** The code dropdown lists most recently used projects first (v1's `last_used` ordering).
- **P7 [decided]** Below the timeline: a summary of projects worked on today and time spent on each, in the form `0000 | 2h 35m`. **[assumed]** Under a project, one indented row per subtask worked on: `⤷ Calcs | 1h 20m`. Time on the project with no subtask is only in the project's total. Subtask names are cut short with … to fit the ribbon.
- **P7a [decided]** ~~If every row has the same letter, the letter column is left off.~~ No longer needed: the summary has no letter column (P7).
- **P7b [decided]** Each project row in the summary starts with a small ✦ in the project's colour: `✦ 0000 | 2h 35m`. **[assumed]** Unassigned time gets the theme's unassigned-track colour.
- **P8 [assumed]** The summary excludes lunch and commute. Break projects (P10) are still listed, like any project.
- **P10 [decided]** A project can be marked as not counting as work, such as Patrick's "Break" project (`OUT`). Its sections behave like lunch: they are taken off time worked (D6) and push the 8h mark later (D2). Unlike lunch, they are put in wherever needed by assigning the project to a section. **[assumed]** Marked with the **Work** tick box in the review panel's project table (V7), stored in the projects table's existing `counts_as_work` column. If a break is the last section of the day, it does not push the mark later, since the end decides its length.
- **P9 [open Q4]** v1 has built-in projects with non-numeric codes (`LNCH`, `COMM`, `OW`). Lunch and commute become section types in v2; what happens to `OW` (Other Way) is undecided.

## 8. Review panel

- **V1 [decided]** The Review button expands the window, or opens a pop-out, to the **left** of the ribbon. **[assumed]** When the ribbon is docked on a left edge, it opens to the right instead. Days still run oldest to newest, left to right.
- **V2 [decided]** It shows the day sliders for this week, last week and the two weeks before that (four weeks; V2b condenses the older ones), **past days only**. Today is left out, because it is already on the ribbon.
- **V2a [decided]** Each week is set apart by a thin line between one week's last day and the next week's Monday, and by its background, which gets a step darker (light theme) or lighter (dark theme) for each week back. **[assumed]** The newest week is plain. The step is the theme's "Last week's shading" colour, so a custom theme can change it.
- **V2b [decided]** Older weeks are condensed. The newest week shown keeps full-width days. One other week, last week by default, has narrower days: node times, code boxes, the day's total and per-project totals, but no durations or space for hover titles. The rest are just the slider, with no annotations, and narrower still. **[decided]** Each slider-only week has a small **+** at the bottom, where the totals would be; clicking it shows that week narrow and returns the previously narrow week to slider only. The newest week is not affected. **[assumed]**
  - Narrow days are 100px; slider-only days are 24px, like the collapsed ribbon.
  - Narrow days can still be edited. Their summaries leave out subtask rows, and meeting titles move into the hover tooltip.
  - Slider-only days are read-only, with times, projects and titles in the hover tooltip. The header is just the day of the month (full date on hover).
  - "Newest" means the newest week shown, so on a Monday last week is full width.
  - Reopening the panel goes back to the default weeks and last week narrow.
- **V2c [assumed]** Background meetings have no coloured strip down their left side in the review panel (the ribbon keeps it).
- **V3 [decided]** Friday, Saturday and Sunday are not shown.
- **V4 [decided]** It can scroll further back in time.
- **V5 [decided]** It contains the table for editing project codes and related settings, and a **⚙ Settings** button next to "+ Add project" that opens Settings (V9).
- **V6 [assumed]** Each day is a column using the same vertical timeline widget as the ribbon, fully editable, with the day's total and credit beneath it. Columns run oldest to newest, left to right, so yesterday sits nearest the ribbon when it is docked on the right. All columns share one time scale.
- **V6b [decided]** Beneath each day's slider, the total time per project for that day, in the same `✦ 0000 | 2h 35m` form, with subtask rows, as the ribbon summary (P7).
- **V6c [assumed]** Every column reserves room for as many summary rows as the longest day, so the timelines stay level on the shared time scale.
- **V6a [decided]** "Earlier" adds every older week back to the first day with anything logged, all at once, in a sideways-scrolling strip. It is greyed out when there is nothing older to show. The panel never grows wider than its default width (wide enough for the default four weeks); extra weeks scroll. **[assumed]** A day with nothing logged shows "Add day", which creates it starting at 08:30.
- **V7 [assumed]** The project table covers code, name, **Work** (ticked if the project counts as work, unticked for a break, P10) and colour. It replaces the v1 Edit Modes dialog and the projects part of Settings.
- **V7a [decided]** Lunch and Commute are listed at the top of the project table so their colours can be changed. They cannot be deleted or renamed. **[assumed]** Their colours are stored as the `lunch_color` and `commute_color` settings.
- **V7b [decided]** Each project in the table has a small ⤷ arrow that expands the table to show that project's subtasks underneath it. **[assumed]** The arrow is faint when the project has no subtasks yet. Expanded, each subtask can be renamed in place or deleted (✕), and a "+ Add subtask" row adds one. Which projects are expanded is not remembered between sessions.
- **V9a [decided]** Beside the project table, in place of the old title rules table, is a credit chart. A solid line shows the nominal day (8h, Mon–Thu), and a dashed line plots the hours actually worked each day, so Patrick can see whether he needs to make time up. **[assumed]**
  - It covers the same past days as the columns above, so "Earlier" lengthens it.
  - Above the chart is the running balance ("1h 15m in credit", "30m to make up", or "On target") and how many days it covers.
  - Points are credit-coloured at or above the day's length and debit-coloured below. Hovering shows the day's hours and credit.
  - Holidays and days with nothing logged are on the axis but not counted.
  - Where day lengths differ (D5a), the solid line steps to each day's own length.
- **V9b [decided]** A "Track" dropdown above the chart switches it between Credit, Lunch, Commute and any one project. **[assumed]**
  - For a project, lunch or commute, the dashed line is the time spent each day in that thing's colour, and the headline is the total and the average per day.
  - Lunch also shows the usual lunch length as the solid line; commute and projects have no solid line.
  - The choice is remembered (`chart_series` setting).
- **V9c [decided]** The chart can switch between a line and a bar chart. **[assumed]** A second dropdown beside Track picks Line or Bars. Bars start from zero and are credit- or debit-coloured (Credit) or in the thing's colour; the nominal line is drawn over them. Remembered (`chart_style`).
- **V9d [decided]** Track has an **All projects** view: every project together, as stacked bars or pies, summarised by week, fortnight, month or all time (an average day). **[assumed]**
  - It covers every logged day before today, not just the columns shown, leaving out holidays. Lunch and commute are left out; Break projects and unassigned time are included, like the summary (P8).
  - Week, fortnight and month show each period's total; all time shows an average day (total ÷ days logged). The newest fortnight is this week and last week.
  - Bars: one stack per period, the biggest project overall at the foot. Pies: one per period, as many of the newest as fit. Empty periods between logged ones show as gaps.
  - A legend on the right lists the projects; hovering a segment or slice gives its time, share and average a day.
  - The style and period are remembered (`chart_mix_style`, `chart_period`).
- **V8 [assumed]** The v1 "Holiday" marking for a day moves into the review panel. **[decided]** Its button on each day is a small sun icon, gold when the day is a holiday.
- **V9 [decided]** Settings opens from the tray menu and from the review panel. It holds:
  - **Getting started:** Connect to Outlook (O3e) and a short guide to ModeSwitch (V10).
  - **Appearance:** dark, light or custom (section 13).
  - **Working days:** seven round toggles, M T W T F S S. **[assumed]** Work-from-home default days use the same toggles.
  - **Working-day length:** see D5a.
  - **Usual commute time and lunch length:** see W3.
  - **Dragging nodes:** grid step and meeting-edge snap distance; see T17b.
  - **Launch at startup.**

  **[assumed]** Saving applies everything straight away, with no restart. Number and time boxes have no arrow buttons: type a value or use the mouse wheel.
- **V10 [decided]** A brief top-level feature list and explainer, for colleagues. **[assumed]** A **Getting started** window: what ModeSwitch is for, how the timeline works, what it does, the mouse controls, and the first steps to set up, with buttons to Connect to Outlook and open Settings. It opens from Settings and the tray menu, and by itself once on a brand-new user's first launch (nothing logged yet; `guide_seen` setting). The README carries the same feature list and the install steps.

## 9. Outlook calendar integration

- **O1 [decided]** Patrick's Outlook calendar auto-populates into the timeline's background layer (T2), with meeting titles.
- **O2 [decided]** This machine runs the **new Outlook** app, which has no COM interface.
- **O2a** Classic Outlook (`OUTLOOK.EXE`) is still installed alongside it, with a working mail profile named "Outlook", and it does have COM. Found 2026-10-22.
- **O3 [decided]** Calendar must work **without admin approval**. Method: read the calendar through classic Outlook's COM interface with pywin32. No app registration or consent is needed.
- **O3a [assumed]** Classic Outlook is kept open in the background (no window) between syncs, because its local copy only updates while it runs. On a fresh start its copy can be stale for a minute or so: the first test found 8 meetings for the fortnight, and 20 a few minutes later. Outlook's date filter reads dates in the Windows regional format (`dd/MM/yyyy` here), so dates are formatted by Windows rather than hard-coded.
- **O3b [assumed]** Microsoft Graph is kept as a second route. Patrick registered an app in the company's Entra ID tenant (single tenant, public client, redirect `http://localhost`, delegated `Calendars.Read`; client ID `389ea0da-4306-471d-bddc-e4f19a2807fe`, tenant ID `c5bab71a-cd6b-46b8-99b8-1e019a84b9ed`, identifiers not secrets). Signing in shows "Need admin approval", because the tenant does not let users consent themselves. If IT ever grants consent, run `python -m modeswitch.calendar_sync --graph` once to sign in. From then on the app uses Graph instead of classic Outlook. The token cache is `%LOCALAPPDATA%\ModeSwitch\msal_cache.bin`, encrypted with Windows DPAPI.
- **O3c [assumed]** The tray menu has "Sync calendar now", which pops up how many meetings were found, or why it failed. Background syncs only update the tray tooltip.
- **O3d [assumed]** Classic Outlook logs on with the mail profile chosen on the Connect to Outlook page (`outlook_profile` setting), or the Windows default profile when none is chosen. It used to be hard-coded to "Outlook", which is the default profile on Patrick's machine, so nothing changes there.
- **O3e [decided]** ModeSwitch is to be shared with colleagues, so Settings has a **Connect to Outlook** setup page with a guide for the steps that cannot be done automatically. **[assumed]**
  - Three checked steps, each with a ✓, ✗ or ○ and how to fix it: classic Outlook installed (from the registry's App Paths), opened and signed in once (a mail profile exists, with a profile picker), and **Test connection**, which reads today's meetings on a fresh connection and reports the count or a plain-words error. **Sync now** starts a normal sync, reported from the tray.
  - It explains what is synced and when (O5), and offers Microsoft Graph as an optional route, with sign in and sign out, saying it needs IT approval first (O3b).
  - Settings shows a one-line calendar status above the button. Sync failures in the tray use the same plain-words errors.
- **O4** The ICS-link fallback is not needed.
- **O5 [assumed]** Sync on launch and every 5 minutes, covering Monday of last week through today. Skipped: all-day events, cancelled or declined meetings, and events marked Free.
- **O6 [assumed]** Meetings are cached locally per day so the review panel can show past days' backgrounds and the app works offline. Syncing never moves, resizes or adds sections. When a day's meetings change, its section titles are re-derived (T14) and unassigned titled sections pick up a project from the title rules (P5). Meetings crossing midnight are split per day.

## 10. Open questions

3. **On/off detection** — does sleep or closing the lid count as turning off? What if the laptop is left on overnight?
4. **`OW` project** — keep, or convert to a numeric code?

## 11. Decision log

Newest first. Add a line whenever a decision is made or an open question is answered, and update the section above to match.

| Date | Decision |
|---|---|
| 2026-11-10 | Hovering a meeting always shows its start time above the title, not only where meetings overlap (T15b). |
| 2026-11-05 | Overlapping meetings stack their translucency, with hairlines at their edges and side-by-side strips; hovering lists every meeting under the mouse with its times and outlines each, so none hides another (T15b). For sharing with colleagues: a Connect to Outlook setup page in Settings (O3e), a Getting started guide (V10) and a README with install steps. |
| 2026-11-05 | Minimise works from the top corner of the screen, and clicking the outermost pixel column of the screen edge minimises too (R7b). The tracker can show bars instead of a line (V9c), and has an All projects view as stacked bars or pies by week, fortnight, month or all time as an average day (V9d). |
| 2026-11-03 | Tray icon is two green triangles whose gap makes an S, from Patrick's picture. It replaced a first attempt drawn as a miniature timeline (section 2). |
| 2026-11-03 | ModeSwitch also starts on unlock and on wake, not only at logon. The start-of-day detection is unchanged (section 2). |
| 2026-11-02 | End of day is locked to the 8h mark by default and follows the clock past it. Lunch and breaks move it. It can be unlocked to leave early, and a hollow node always marks the 8h mark (D2, D2b). A project can be marked as not counting as work, so Patrick's Break project behaves like lunch (P10, D6). |
| 2026-10-27 | Today's end node follows the clock whenever the clock passes it, unless it was set by hand to a time already past (D2a). Slider-only review weeks have a + to show them narrow (V2b). Earlier adds all older logged weeks at once and scrolls, without widening the panel (V6a). New sandwich icon from Patrick's picture (R3a). |
| 2026-10-27 | Review opens on four weeks: this week, last week (narrow) and two more (slider only) (V2). In overtime, today's end follows the clock while it is still the computed default (D2a). Today's timeline runs 30 min past the end or the current time, whichever is later (T16b). |
| 2026-10-27 | Older review weeks get darker in the light theme and lighter in the dark theme (V2a); it was the other way round. |
| 2026-10-27 | Holding Alt while dragging a node snaps only to meeting starts and ends (T17). It used to switch the meeting and current-time snaps off. |
| 2026-10-27 | Review weeks condense with age: the newest full width, the week before narrow, older ones slider only; each week back shaded a step further (V2a, V2b). Minimise is an arrow into the screen edge (R7a). New tooltip text for the house and sandwich (R9). The sandwich icon is an angled triangle (R3a). |
| 2026-10-27 | **Subtasks replace the A–D letters and Set title.** Right-click a section's code for Assign subtask (pick or create). Summaries list subtasks under their project; the review project table expands with ⤷ to show them (P2a, P7, V7b). |
| 2026-10-27 | Hover tooltips explain every button and setting (R9). |
| 2026-10-27 | Nodes snap to the current time when that is nearer than the grid (T17a). Meeting-edge snap distance drops from 15 to 5 min, and it and the grid step are adjustable in Settings (T17b). |
| 2026-10-27 | **Themes:** dark, light and custom. A custom theme is a few hand-picked base colours, with everything else derived from them (and overridable). Every colour pick offers lighter/darker shades, colour-wheel matches and a readability check (section 13). |
| 2026-10-27 | **Settings** opens from the review panel too. It now covers appearance, working days (seven M–S toggles), working-day length (same every day, or per day), usual commute and lunch (V9, D5a, W3). Day lengths feed credit and the chart. |
| 2026-10-27 | Review panel: weeks set apart by alternate shading and a line between them; no left strip on meetings (V2a). Lunch and Commute in the project table for their colours (V7a). Summary rows start with a ✦ in the project's colour (P7b). The chart can track a project, lunch or commute (V9b). |
| 2026-10-22 | **Open Q2 answered:** credits are a running balance, shown as a chart in the review panel: nominal 8h line, dashed line of hours worked each day (D7, V9a). It replaces the title rules table; rules are still learned automatically (P5). |
| 2026-10-22 | Review panel shows past days only; today is on the ribbon (V2). The Review button has an arrow showing which way the panel opens (R6). The minimise button is `−` (R7a). |
| 2026-10-22 | Holiday button is a sun icon (V8). Summaries leave the letter off when every row has the same one (P7a). New sandwich button takes lunch off a day or puts it back (R3a, T21b). |
| 2026-10-22 | Meetings are coloured by time: grey once ended, dark red later on, pulsing red when starting within 30 min. The now-line is white (T15a, T16a). |
| 2026-10-22 | Titles are no longer written on the timeline. They show only while the mouse is over the event, on the half away from the screen edge (T10, T11). |
| 2026-10-22 | **Calendar must work without admin approval.** It reads through classic Outlook's COM interface, which is installed alongside the new Outlook (O3). Graph stays as a dormant second route (O3b). |
| 2026-10-22 | **Open Q5 answered:** Patrick registered the Graph app himself, but signing in hit "Need admin approval", so Graph needs IT consent (O3b). |
| 2026-10-22 | Moving lunch's start node moves the whole lunch (T21a). |
| 2026-10-21 | **Open Q1 answered:** the ribbon reserves its screen space, so other windows snap to it, and maximised and snapped windows resize when it is minimised or expanded (R2). |
| 2026-10-21 | The ribbon can be dragged by its header to the left or right edge of any monitor and snaps to the nearest edge (R8). |
| 2026-10-20 | Ribbon gets a minimise button that collapses it to the slider's width; clicking the slider expands it (R7). |
| 2026-10-20 | Review panel shows each day's time per project beneath its slider (V6b). |
| 2026-10-20 | ModeSwitch starts automatically at login. Startup shortcut switched to `pythonw.exe` and turned on. |
| 2026-10-13 | v2 built: ribbon, vertical timeline, review panel, start/end detection. Build-time choices are marked [assumed] in sections 4, 5 and 8. Retired v1 UI files moved to `legacy_v1/` rather than deleted, because v1 was never committed. |
| 2026-10-13 | **Meetings are background, not sections.** The tool logs what time was actually spent on, so overlap is impossible. Outlook meetings are drawn behind the slider; Patrick draws sections over the top. Node drags snap to a meeting's start or end when within 15 min. |
| 2026-10-13 | This machine uses the new Outlook app, so COM is ruled out. |
| 2026-10-13 | Letters A–D mean whatever Patrick wants; the tool gives them no meaning. |
| 2026-10-13 | Titles that do not fit are cropped, with the full title on hover. |
| 2026-10-13 | Commute sections sit outside the start and end nodes and do not count toward the 8 hours (confirmed). |
| 2026-10-13 | v2 is a new UI, but should borrow v1 functions and fields where they apply (shorthand time typing, extra fields). See section 12. |
| 2026-10-13 | The sentence cut off at "there needs to be" in the original brief is dropped; nothing is missing. |
| 2026-10-13 | v2 brief given by Patrick: vertical 160px ribbon on the right, node-and-section timeline, project code and A–D letter per section, permanent lunch, WFH toggle, commute defaults, auto start and end times, credits, 30-minute meeting pulse, project summary, review panel, Outlook integration. |
| 2026-10-13 | This file created as the source of truth. |

## 12. Code map

| File | Role |
|---|---|
| `main.py`, `modeswitch/app.py` | Entry point, tray icon (Show / Hide / Review / Sync calendar now / Settings / Exit), background calendar sync, applying settings changes, save-out-time prompt on exit |
| `modeswitch/theme.py` | Colour themes: the tokens, dark and light presets, derived colours, colour maths (shades, harmonies, contrast), and the app-wide stylesheet |
| `modeswitch/day_model.py` | The rules of the timeline: nodes, sections, move, split, delete, commute, credits, titles, title rules. No Qt, no database |
| `modeswitch/days.py` | Loads, creates and saves whole days; backfills forgotten end times |
| `modeswitch/system_times.py` | Reads power-on time from the Windows event log |
| `modeswitch/app_icon.py` | The tray and window icon, drawn in code |
| `modeswitch/autostart.py` | Starts the app at logon, unlock and wake (scheduled task), and keeps it to one running copy |
| `modeswitch/appbar.py` | Registers the ribbon as a Windows app bar so it reserves its strip of the screen |
| `modeswitch/calendar_sync.py` | Reads meetings from classic Outlook (COM), or from Graph once signed in. Run `python -m modeswitch.calendar_sync` to print today's meetings |
| `modeswitch/timeutil.py` | Time formatting, snapping, contrast colour |
| `modeswitch/db/schema.py`, `models.py` | SQLite tables and CRUD helpers |
| `modeswitch/widgets/day_timeline.py` | The vertical timeline widget: painting and all mouse interaction. Used by both the ribbon and the review panel |
| `modeswitch/widgets/house_button.py` | The WFH toggle |
| `modeswitch/widgets/icon_buttons.py` | The holiday (sun) and lunch (sandwich) toggles |
| `modeswitch/widgets/time_input.py` | Shorthand time parsing (`930` → `09:30`), from v1 |
| `modeswitch/windows/ribbon.py` | The ribbon window: docking, dragging to another edge, minimise, heartbeat, summary and time-left readouts |
| `modeswitch/windows/review_panel.py` | Review panel: day columns grouped by week, projects table (with Lunch and Commute, and expandable subtasks), tracker chart |
| `modeswitch/widgets/credit_chart.py` | The tracker chart: credit against the nominal day, or time on a project, lunch or commute, as a line or bars |
| `modeswitch/widgets/mix_chart.py` | The tracker's All projects view: stacked bars or pies per period |
| `modeswitch/windows/settings_dialog.py` | Settings: appearance, working days, day lengths, usual lunch and commute, autostart |
| `modeswitch/dialogs/colour_picker.py` | Colour picker with shades, colour-wheel matches, colours in use and a readability check |
| `modeswitch/dialogs/theme_editor.py` | Custom theme editor |
| `modeswitch/dialogs/add_project.py` | New-project dialog, from v1 |
| `modeswitch/dialogs/outlook_setup.py` | Connect to Outlook: setup checks, guide, connection test, Graph sign-in |
| `modeswitch/dialogs/guide.py` | Getting started: explainer, feature list, controls, first steps |
| `legacy_v1/` | Retired v1 UI files, kept for reference only. They no longer run. Safe to delete |

### 12.1 Carried over from v1

- Shorthand time typing, now used when clicking a node's time.
- End time computed as start + 8h + lunch, recalculated when start or lunch change.
- "Time left" / "overtime" readout, refreshed every minute.
- Per-project colour, with black or white text chosen for contrast.
- Projects listed most recently used first.
- `is_holiday` flag on days.
- Working-days setting and target minutes (480) stored in `settings`.
- Tray icon, launch at Windows startup, and the prompt to save the out time on exit.

### 12.2 Data model

- Database: `%LOCALAPPDATA%\ModeSwitch\modeswitch.db`. Set the `MODESWITCH_DB` environment variable to point the app at a different file for testing.
- `days`: date, `in_time` / `out_time` (start and end of work, excluding commute), `in_source` (manual / detected), `out_source` (manual / detected / computed), `wfh`, `last_seen`, `is_holiday`.
- `time_blocks`: one row per section — `kind` (work / lunch / commute), start, end, nullable `project_id`, nullable `subtask_id`, `title`, `title_manual`. The old `category` column (A–D) is left in place but no longer used; `title_manual` is only set on titles typed before Set title was removed. A day's rows are replaced as a set on every save.
- `meetings`: cached calendar events per day.
- `subtasks`: `project_id`, `name`, unique per project. Deleted with their project.
- `title_rules`: lower-case text, project, subtask. Matched anywhere in a section's title; the longest match wins. Assigning a project to a titled section adds or updates a rule. There is no UI for them.
- `settings`: `working_days`, `wfh_days`, `target_minutes`, `target_same`, `target_by_day` (`1:480,2:450,…`), `lunch_minutes`, `commute_minutes`, `node_snap`, `meeting_snap`, `day_floor`, `lunch_color`, `commute_color`, `theme` (dark / light / custom), `theme_custom` (JSON: `{"base": "dark", "tokens": {…}}`), `chart_series`, `chart_style`, `chart_mix_style`, `chart_period`, `outlook_profile`, `guide_seen`, plus the ribbon's `ribbon_collapsed`, `dock_screen`, `dock_edge`.
- Lunch and commute are section kinds, not projects; the v1 `LNCH` and `COMM` projects are gone. `OW` is still seeded (open Q4).
- A v1-shaped database, if one is found, is renamed to `modeswitch.v1.bak` and a fresh one started. None existed on this machine at build time.

## 13. Colours and themes

- **C1 [decided]** Three themes, chosen in Settings: **dark** (the original look), **light**, and **custom**.
- **C2 [decided]** In a custom theme every colour can be picked with a colour picker. Picking should make it easy to choose colours that go together, following good UI practice and colour theory rather than one fixed "shadow of" button.
- **C3 [assumed]** How that is done:
  - **Base and derived colours.** Only the base colours are picked by hand: background, panels, text, accent, credit, debit, now-line, nodes, and the four meeting states. Secondary and faint text, borders, hover and pressed buttons, chart grid lines, the unassigned track and the alternate-week shading are derived from them. That way the whole theme stays consistent when one base colour changes. Each derived colour has an **Auto** tick; untick it to pick that colour by hand.
  - **The picker** offers four things:
    - nine lighter-to-darker shades of the current colour, for borders, shadows and highlights; this is the "shadow of" idea;
    - colour-wheel matches to the accent colour: complementary, analogous, triadic and split-complementary;
    - colours already in use by projects and the theme;
    - a readability check (WCAG contrast ratio) when the colour is text on the background.

    "More…" opens the full Windows colour dialog.
  - **Starting point.** A custom theme starts as a copy of the dark or light preset, with a button to start again from either. The theme editor also shows the readability of text on the background.
- **C4 [assumed]** The same picker is used for project colours and the Lunch and Commute colours. Those belong to the projects, not the theme, so they stay the same across themes.
- **C5 [assumed]** Changing the theme applies at once, with no restart. The house, sun and sandwich icons keep their own "on" colours in every theme.

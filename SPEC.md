# ModeSwitch — Specification

**Status:** v2 ribbon, timeline and review panel built (2026-10-13). Minimise, per-day project totals in review, and autostart added (2026-10-20). Ribbon reserves its screen space and can be dragged to any monitor edge (2026-10-21). Outlook sync working through classic Outlook (2026-10-22); Microsoft Graph route built but waiting on IT admin consent. Last updated 2026-10-22.

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
- Runs from the system tray.
- **[decided]** Starts automatically when Patrick logs in to Windows. Done with a shortcut in the user's Startup folder, toggled in Settings. **[assumed]** When run from source the shortcut launches `.venv\Scripts\pythonw.exe main.py` so no console window is left open.

## 3. The ribbon window

- **R1 [decided]** A vertical ribbon docked along the left or right edge of a monitor (right edge of the main screen by default), about 160px wide.
- **R2 [decided]** It reserves its strip of the screen, as if its inner edge were the edge of the screen: other windows snap to it instead of going behind it, and when it is minimised or expanded, maximised and snapped windows on that monitor shrink or grow with it.
- **R2a [assumed]** Done by registering as a Windows app bar (`SHAppBarMessage`), the same mechanism as the taskbar. Windows resizes maximised and snapped windows when the reserved space changes; ordinary free-floating windows are not moved. Frameless, full height of the work area, always on top, but it steps behind full-screen apps (presentations, full-screen video). The space is given back when the ribbon is hidden from the tray or the app exits.
- **R8 [decided]** The ribbon can be moved to the left or right edge of any monitor by dragging it by its header. On release it snaps to the nearest vertical edge.
- **R8a [assumed]** The nearest edge is whichever side of the monitor under the cursor the cursor is on. A highlighted outline shows where it will land while dragging. The chosen monitor and edge are remembered (`dock_screen`, `dock_edge` settings); if that monitor is not connected, it docks on the main screen and moves back when the monitor returns. It cannot be dragged while minimised, because the header is hidden. The minimise arrow points toward the edge.
- **R3 [decided]** Top-left: a small house-icon button toggling "working from home" for the day (section 6).
- **R3a [decided]** Beside it, a small sandwich-icon button toggling lunch on or off for the day (T21b). The same button is in each day's header in the review panel.
- **R4 [decided]** Main area: the day timeline (section 4).
- **R5 [decided]** Below the timeline: the project summary (section 7).
- **R6 [decided]** Very bottom: a Review button (section 8), with an arrow pointing the way the review panel opens (`◀ Review` when docked on the right, `Review ▶` on the left).
- **R7 [decided]** A minimise button collapses the ribbon to just the slider's width, still docked up the right edge. Clicking anywhere on the slider expands it again.
- **R7a [decided]** The minimise button is a small `−` at the top right, beside the date. **[assumed]** Collapsed, the ribbon is 24px wide and shows sections, meetings, nodes and the now-line, with no text or boxes; hover tooltips still work, but nothing can be edited. Collapsing closes the review panel, and opening Review from the tray expands the ribbon. The collapsed state is remembered across restarts (`ribbon_collapsed` setting).

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
- **T11 [decided]** Event titles only appear when the mouse is over the event, and only on the half of the timeline away from the screen edge (the left half when docked on the right, the right half when docked on the left). **[assumed]** The title appears instantly, in a small box drawn over the text column at the top of the meeting. Overlapping meetings are listed together. A section with a hand-typed title but no meeting shows that title the same way. Hover tooltips still give times, project and letter anywhere, but no titles. When collapsed, titles come from the tooltip, on the inner half only.
- **T12 [decided]** Right of each section: a narrower column, just wide enough for a 4-digit project code in a small box.
- **T13 [decided]** Below the code box: a small square box holding a single letter, A, B, C or D. Defaults to A.
- **T14 [assumed]** A section's title comes from the background meeting it lines up with (same start and end, or the meeting covering most of the section). Sections with no matching meeting have no title.
- **T15 [assumed]** Sections are filled with the project's colour (the `color` field already exists on projects). Background meetings are drawn as translucent bands so the two layers are easy to tell apart.
- **T15a [decided]** Meeting colours: **grey** once a meeting has ended, **dark red** for later meetings, and a **pulsing red** for one starting within 30 minutes (T22). **[assumed]** A meeting that is on right now is a steady, brighter red. Every meeting on a past day is grey.
- **T16 [assumed]** If a section is too short for both boxes, the letter box is dropped and shown on hover with the title. Below about 12px the code box is dropped too.
- **T16a [decided]** A **white** tick on the slider marks the current time.

### 4.4 Interactions

| Action | Result | Status |
|---|---|---|
| Drag a node | Moves that node only; the section's duration changes. Snaps to **5 min**, and to the start or end of a background meeting when within **15 min** of it. | decided |
| Drag a section body | Moves both its nodes together; duration stays fixed. Snaps to **15 min**. Neighbouring sections stretch or shrink to fit. | decided |
| Click the project code box | Dropdown to pick a project code. | decided |
| Click the letter box | Dropdown to pick A / B / C / D. | decided |
| Double-click the section line | Splits the section in two. The existing project code stays on the **top** half. | decided |
| Right-click a section | Menu with Delete. The section **above** expands to fill the space. | decided |
| Right-click a section | The same menu also offers Split here and Set title… (a hand-typed title, which sticks even if the section moves off a meeting). | assumed |
| Click a node's time | Type a time directly, using v1's shorthand entry (`930` → `09:30`). | assumed |

- **T17 [assumed]** When a meeting edge and the 5-min grid both apply, the meeting edge wins. Meeting snap applies to node drags only, not section-body drags. Holding **Alt** while dragging switches the meeting snap off, so a node can be placed near a meeting edge without jumping to it.
- **T18 [assumed]** A split happens at the point clicked, snapped to 5 min. The new bottom half is unassigned, letter A.
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
- **D2 [decided]** Once the start time is known, the day defaults to a 1-hour lunch and an 8-hour working day excluding lunch, so end = start + 8h + lunch. The end node updates as start or lunch change.
- **D3 [decided]** If Patrick does not set the end time himself, it is filled in from when the laptop was turned off.
- **D4 [assumed]** Precedence for the end time: set by hand > detected turn-off > computed default (D2). Dragging or typing the end node counts as setting it by hand, and so does answering Yes to "Save out time?" on Exit.
- **D5 [decided]** Leaving earlier or later than the 8-hour target is tracked as credits: credit = time worked − 8h, positive or negative.
- **D6 [decided]** Time worked = end − start − lunch. Commute does not count as work.
- **D7 [decided]** Credits are tracked as a running balance on a chart in the review panel (V9a). The ribbon still shows today's time left, or today's credit once the end is real.

How on/off times are detected **[assumed]**:

- Start: the earliest boot, wake-from-sleep or logon in the Windows System event log for today, ignoring anything before 05:00 (the `day_floor` setting). If the log has nothing, the time the app launched.
- End: while running, the app stamps the day with a last-seen time every minute. On the next launch, any earlier day still on its computed end time gets its last-seen time as the end.
- While the end is still the computed default the ribbon shows "time left" / "overtime"; once it is real it shows the day's credit.
- Whether sleep and lid-close count as "off" is **[open Q3]**. As built, the last-seen stamp simply stops when the machine sleeps.

## 6. Working from home and commute

- **W1 [decided]** The house button toggles WFH for the day. WFH means no commute sections.
- **W2 [decided]** Defaults: WFH on Monday, Tuesday and Thursday; commute on Wednesday.
- **W3 [decided]** Commute sections default to 1 hour each.
- **W4 [decided]** On a commute day there are two commute sections: one ending at the day's start node, one beginning at the day's end node. They sit outside the 8 working hours.
- **W5 [assumed]** Working days are Monday to Thursday (the v1 `working_days` setting is `1,2,3,4`, and the review panel hides Friday to Sunday).

## 7. Projects, letters and the summary

- **P1 [decided]** Projects are identified by a 4-digit code (e.g. `0000`).
- **P2 [decided]** Each section carries one project code and one letter A–D.
- **P3 [decided]** The letters A–D have no fixed meaning. They are free tags for Patrick to use however he likes; the tool attaches no labels or behaviour to them.
- **P4 [decided]** Smart defaults: the tool should know, for example, that the morning meeting titled "Daily" is `0000`.
- **P5 [assumed]** Smart defaults work as title rules: a case-insensitive match on a section's title (T14) maps to a project code and letter. When Patrick assigns a code to a titled section by hand, that title is remembered and reused next time. **[decided]** There is no table for editing rules; they are only learned this way. Assigning a different project to the same title overwrites the rule.
- **P6 [assumed]** The code dropdown lists most recently used projects first (v1's `last_used` ordering).
- **P7 [decided]** Below the timeline: a summary of projects worked on today and time spent on each, in the form `0000 | 2h 35m | A`.
- **P7a [decided]** If every row in a summary has the same letter (all A, say), the letter column is left off: `0000 | 2h 35m`. This applies to each day's summary in the review panel separately.
- **P8 [assumed]** The summary has one row per code-and-letter pair and excludes lunch and commute.
- **P9 [open Q4]** v1 has built-in projects with non-numeric codes (`LNCH`, `COMM`, `OW`). Lunch and commute become section types in v2; what happens to `OW` (Other Way) is undecided.

## 8. Review panel

- **V1 [decided]** The Review button expands the window, or opens a pop-out, to the **left** of the ribbon. **[assumed]** When the ribbon is docked on a left edge, it opens to the right instead. Days still run oldest to newest, left to right.
- **V2 [decided]** It shows the day sliders for this week and all of last week, **past days only**. Today is left out, because it is already on the ribbon.
- **V3 [decided]** Friday, Saturday and Sunday are not shown.
- **V4 [decided]** It can scroll further back in time.
- **V5 [decided]** It contains the table for editing project codes and related settings.
- **V6 [assumed]** Each day is a column using the same vertical timeline widget as the ribbon, fully editable, with the day's total and credit beneath it. Columns run oldest to newest, left to right, so yesterday sits nearest the ribbon when it is docked on the right. All columns share one time scale.
- **V6b [decided]** Beneath each day's slider, the total time per project for that day, in the same `0000 | 2h 35m | A` form as the ribbon summary (P7).
- **V6c [assumed]** Every column reserves room for as many summary rows as the longest day, so the timelines stay level on the shared time scale.
- **V6a [assumed]** "Earlier" adds one more week on the left. A day with nothing logged shows "Add day", which creates it starting at 08:30.
- **V7 [assumed]** The project table covers code, name and colour. It replaces the v1 Edit Modes dialog and the projects part of Settings.
- **V9a [decided]** Beside the project table, in place of the old title rules table, is a credit chart. A solid line shows the nominal day (8h, Mon–Thu), and a dashed line plots the hours actually worked each day, so Patrick can see whether he needs to make time up. **[assumed]**
  - It covers the same past days as the columns above, so "Earlier" lengthens it.
  - Above the chart is the running balance ("1h 15m in credit", "30m to make up", or "On target") and how many days it covers.
  - Points are orange at or above 8h and red below. Hovering shows the day's hours and credit.
  - Holidays and days with nothing logged are on the axis but not counted.
- **V8 [assumed]** The v1 "Holiday" marking for a day moves into the review panel. **[decided]** Its button on each day is a small sun icon, gold when the day is a holiday.
- **V9 [assumed]** Working days, default WFH days and launch-at-startup are in Settings, on the tray icon's menu.

## 9. Outlook calendar integration

- **O1 [decided]** Patrick's Outlook calendar auto-populates into the timeline's background layer (T2), with meeting titles.
- **O2 [decided]** This machine runs the **new Outlook** app, which has no COM interface.
- **O2a** Classic Outlook (`OUTLOOK.EXE`) is still installed alongside it, with a working mail profile named "Outlook", and it does have COM. Found 2026-10-22.
- **O3 [decided]** Calendar must work **without admin approval**. Method: read the calendar through classic Outlook's COM interface with pywin32. No app registration or consent is needed.
- **O3a [assumed]** Classic Outlook is kept open in the background (no window) between syncs, because its local copy only updates while it runs. On a fresh start its copy can be stale for a minute or so: the first test found 8 meetings for the fortnight, and 20 a few minutes later. Outlook's date filter reads dates in the Windows regional format (`dd/MM/yyyy` here), so dates are formatted by Windows rather than hard-coded.
- **O3b [assumed]** Microsoft Graph is kept as a second route. Patrick registered an app in the company's Entra ID tenant (single tenant, public client, redirect `http://localhost`, delegated `Calendars.Read`; client ID `389ea0da-4306-471d-bddc-e4f19a2807fe`, tenant ID `c5bab71a-cd6b-46b8-99b8-1e019a84b9ed`, identifiers not secrets). Signing in shows "Need admin approval", because the tenant does not let users consent themselves. If IT ever grants consent, run `python -m modeswitch.calendar_sync --graph` once to sign in. From then on the app uses Graph instead of classic Outlook. The token cache is `%LOCALAPPDATA%\ModeSwitch\msal_cache.bin`, encrypted with Windows DPAPI.
- **O3c [assumed]** The tray menu has "Sync calendar now", which pops up how many meetings were found, or why it failed. Background syncs only update the tray tooltip.
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
| `main.py`, `modeswitch/app.py` | Entry point, tray icon (Show / Hide / Review / Sync calendar now / Settings / Exit), background calendar sync, dark stylesheet, save-out-time prompt on exit |
| `modeswitch/day_model.py` | The rules of the timeline: nodes, sections, move, split, delete, commute, credits, titles, title rules. No Qt, no database |
| `modeswitch/days.py` | Loads, creates and saves whole days; backfills forgotten end times |
| `modeswitch/system_times.py` | Reads power-on time from the Windows event log |
| `modeswitch/appbar.py` | Registers the ribbon as a Windows app bar so it reserves its strip of the screen |
| `modeswitch/calendar_sync.py` | Reads meetings from classic Outlook (COM), or from Graph once signed in. Run `python -m modeswitch.calendar_sync` to print today's meetings |
| `modeswitch/timeutil.py` | Time formatting, snapping, contrast colour |
| `modeswitch/db/schema.py`, `models.py` | SQLite tables and CRUD helpers |
| `modeswitch/widgets/day_timeline.py` | The vertical timeline widget: painting and all mouse interaction. Used by both the ribbon and the review panel |
| `modeswitch/widgets/house_button.py` | The WFH toggle |
| `modeswitch/widgets/icon_buttons.py` | The holiday (sun) and lunch (sandwich) toggles |
| `modeswitch/widgets/time_input.py` | Shorthand time parsing (`930` → `09:30`), from v1 |
| `modeswitch/windows/ribbon.py` | The ribbon window: docking, dragging to another edge, minimise, heartbeat, summary and time-left readouts |
| `modeswitch/windows/review_panel.py` | Review panel: day columns, projects table, credit chart |
| `modeswitch/widgets/credit_chart.py` | The credit chart: hours worked per day against the nominal day, and the running balance |
| `modeswitch/windows/settings_dialog.py` | Working days, WFH days, autostart |
| `modeswitch/dialogs/add_project.py` | New-project dialog, from v1 |
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
- `time_blocks`: one row per section — `kind` (work / lunch / commute), start, end, nullable `project_id`, `category` (A–D), `title`, `title_manual`. A day's rows are replaced as a set on every save.
- `meetings`: cached calendar events per day.
- `title_rules`: lower-case text, project, letter. Matched anywhere in a section's title; the longest match wins. Assigning a project to a titled section adds or updates a rule. There is no UI for them.
- `settings`: `working_days`, `wfh_days`, `target_minutes`, `lunch_minutes`, `commute_minutes`, `day_floor`.
- Lunch and commute are section kinds, not projects; the v1 `LNCH` and `COMM` projects are gone. `OW` is still seeded (open Q4).
- A v1-shaped database, if one is found, is renamed to `modeswitch.v1.bak` and a fresh one started. None existed on this machine at build time.

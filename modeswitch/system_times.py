"""
Works out when the laptop was turned on today, from the Windows System event log.
"""
from __future__ import annotations

import re
from datetime import datetime, date, timezone
from typing import Optional

# provider → event id that marks the machine coming on or the user arriving
_ON_EVENTS = {
    "Microsoft-Windows-Kernel-General": "12",        # boot
    "Microsoft-Windows-Power-Troubleshooter": "1",   # wake from sleep
    "Microsoft-Windows-Winlogon": "7001",            # user logon
}

_PROVIDER_RE = re.compile(r"<Provider Name='([^']+)'")
_EVENT_ID_RE = re.compile(r"<EventID[^>]*>(\d+)</EventID>")
_TIME_RE = re.compile(r"<TimeCreated SystemTime='([^']+)'")


def first_on_time(day: date, floor: str = "05:00") -> Optional[str]:
    """Earliest boot, wake or logon on the given day at or after `floor`, as HH:MM.

    Returns None if the log cannot be read or holds nothing for that day.
    """
    try:
        import win32evtlog
    except ImportError:
        return None

    midnight = datetime.combine(day, datetime.min.time())
    window_ms = int((datetime.now() - midnight).total_seconds() * 1000)
    if window_ms <= 0:
        return None
    query = ("*[System[(EventID=1 or EventID=12 or EventID=7001) and "
             f"TimeCreated[timediff(@SystemTime) <= {window_ms}]]]")

    times: list[datetime] = []
    try:
        handle = win32evtlog.EvtQuery("System", win32evtlog.EvtQueryChannelPath, query)
        while True:
            events = win32evtlog.EvtNext(handle, 64)
            if not events:
                break
            for ev in events:
                xml = win32evtlog.EvtRender(ev, win32evtlog.EvtRenderEventXml)
                provider = _PROVIDER_RE.search(xml)
                event_id = _EVENT_ID_RE.search(xml)
                stamp = _TIME_RE.search(xml)
                if not (provider and event_id and stamp):
                    continue
                if _ON_EVENTS.get(provider.group(1)) != event_id.group(1):
                    continue
                times.append(_to_local(stamp.group(1)))
    except Exception:
        return None

    floor_h, floor_m = map(int, floor.split(":"))
    floor_dt = midnight.replace(hour=floor_h, minute=floor_m)
    same_day = [t for t in times if t.date() == day and t >= floor_dt]
    return min(same_day).strftime("%H:%M") if same_day else None


def _to_local(system_time: str) -> datetime:
    """'2026-10-13T07:42:10.1234567Z' (UTC) → naive local datetime."""
    trimmed = system_time.rstrip("Z")[:26]
    utc = datetime.fromisoformat(trimmed).replace(tzinfo=timezone.utc)
    return utc.astimezone().replace(tzinfo=None)

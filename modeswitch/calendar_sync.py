"""
Reading the user's Outlook calendar. Two sources:

  • Classic Outlook, through COM (the default). The new Outlook app has no COM
    interface, but classic Outlook is installed alongside it with a working profile,
    and reading through it needs no app registration or admin approval.
  • Microsoft Graph (/me/calendarView), used instead once signed in. The company
    tenant needs IT to grant admin consent first, so this is dormant for now.

Also the checks the Connect to Outlook page runs: is classic Outlook installed, which
mail profiles exist, and a test read of today's meetings.

No Qt and no database writes in here: fetch_meetings() runs on a background thread
and returns meetings per day for the main thread to store.

    python -m modeswitch.calendar_sync              print today's meetings
    python -m modeswitch.calendar_sync --graph      sign in to Graph (browser), then print
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from modeswitch.db.models import Meeting

# (start, end, title, id) in local time, naive
Event = tuple[datetime, datetime, str, Optional[str]]


def sync_range(today: Optional[date] = None) -> tuple[date, date]:
    """Monday of last week to today: the days the review panel opens on."""
    today = today or date.today()
    return today - timedelta(days=today.weekday() + 7), today


def _split_by_day(events: list[Event], first: date, last: date) -> dict[str, list[Meeting]]:
    """Meetings per day from first to last inclusive. Every day in the range is present,
    so a day whose meetings were all cancelled comes back empty. A meeting crossing
    midnight is cut into one piece per day."""
    out: dict[str, list[Meeting]] = {}
    d = first
    while d <= last:
        out[d.isoformat()] = []
        d += timedelta(days=1)

    for ev_start, ev_end, title, ev_id in events:
        d = ev_start.date()
        while d <= ev_end.date():
            day_start = datetime.combine(d, datetime.min.time())
            s = max(ev_start, day_start)
            e = min(ev_end, day_start + timedelta(days=1))
            key = d.isoformat()
            if e > s and key in out:
                s_min = s.hour * 60 + s.minute
                e_min = 24 * 60 - 1 if e.date() > d else e.hour * 60 + e.minute
                out[key].append(Meeting(
                    id=None, date=key, outlook_id=ev_id, title=title or "(no title)",
                    start_time=f"{s_min // 60:02d}:{s_min % 60:02d}",
                    end_time=f"{e_min // 60:02d}:{e_min % 60:02d}"))
            d += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# Classic Outlook (COM)
# ---------------------------------------------------------------------------

OL_FOLDER_CALENDAR = 9
OL_FREE = 0
OL_RESPONSE_DECLINED = 4
OL_MEETING_CANCELED = (5, 7)


class _SYSTEMTIME(ctypes.Structure):
    _fields_ = [(n, wintypes.WORD) for n in
                ("wYear", "wMonth", "wDayOfWeek", "wDay", "wHour", "wMinute", "wSecond", "wMs")]


def _short_date(d: date) -> str:
    """The date in Windows' own short format (dd/mm/yyyy here), which Outlook's
    Restrict() filter expects."""
    buf = ctypes.create_unicode_buffer(64)
    ctypes.windll.kernel32.GetDateFormatEx(
        None, 1, ctypes.byref(_SYSTEMTIME(d.year, d.month, 0, d.day, 0, 0, 0, 0)),
        None, buf, 64, None)
    return buf.value


def _naive(t) -> datetime:
    """Outlook hands back local times; drop whatever tzinfo pywin32 attached."""
    return datetime(t.year, t.month, t.day, t.hour, t.minute)


OFFICE_KEY = r"Software\Microsoft\Office\16.0\Outlook"   # Office 2016 onwards, and 365


def classic_outlook_path() -> Optional[str]:
    """Where OUTLOOK.EXE (classic Outlook) is installed, or None."""
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion"
                                      r"\App Paths\OUTLOOK.EXE") as key:
                path = winreg.QueryValue(key, None)
                if path and Path(path.strip('"')).exists():
                    return path.strip('"')
        except OSError:
            continue
    return None


def outlook_profiles() -> tuple[list[str], Optional[str]]:
    """(mail profile names, the default one). Empty until classic Outlook has been
    opened and signed in once."""
    import winreg
    names, default = [], None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OFFICE_KEY + r"\Profiles") as key:
            i = 0
            while True:
                try:
                    names.append(winreg.EnumKey(key, i))
                except OSError:
                    break
                i += 1
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OFFICE_KEY) as key:
            default = winreg.QueryValueEx(key, "DefaultProfile")[0]
    except OSError:
        pass
    return names, default if default in names else (names[0] if names else None)


def explain_error(e: Exception) -> str:
    """A COM error from Outlook, in words someone can act on."""
    text = str(e)
    if "Invalid class string" in text:
        return "Classic Outlook is not installed, so there is nothing to read the calendar through."
    if "Server execution failed" in text or "-2146959355" in text:
        return ("Windows could not start classic Outlook in the background. Open "
                "Outlook (classic) once from the Start menu, let it finish loading, close it, "
                "and try again.")
    if "-2147221233" in text or "profile" in text.lower():
        return "Outlook could not open that mail profile. Pick another profile above."
    return text


class OutlookReader:
    """Holds classic Outlook open between syncs so its local copy keeps syncing.
    Use it from one thread only, the one that created it.

    `profile` is the mail profile to log on with; empty means the default one."""

    def __init__(self, profile: str = ""):
        import pythoncom
        pythoncom.CoInitialize()
        self._ns = None
        self.profile = profile

    def use_profile(self, profile: str) -> None:
        if profile != self.profile:
            self.profile = profile
            self._ns = None

    def _namespace(self):
        if self._ns is None:
            import win32com.client
            ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
            # No dialog. Ignored if Outlook is already running with a profile.
            ns.Logon(self.profile or outlook_profiles()[1] or "", "", False, False)
            self._ns = ns
        return self._ns

    def events(self, first: date, last: date) -> list[Event]:
        try:
            return self._events(first, last)
        except Exception:
            self._ns = None   # Outlook was closed or restarted: reconnect next time
            raise

    def _events(self, first: date, last: date) -> list[Event]:
        items = self._namespace().GetDefaultFolder(OL_FOLDER_CALENDAR).Items
        items.IncludeRecurrences = True
        items.Sort("[Start]")
        after = _short_date(first)
        before = _short_date(last + timedelta(days=1))
        found = items.Restrict(f"[Start] < '{before} 00:00' AND [End] > '{after} 00:00'")
        events = []
        for it in found:
            if (it.AllDayEvent or it.BusyStatus == OL_FREE
                    or it.ResponseStatus == OL_RESPONSE_DECLINED
                    or it.MeetingStatus in OL_MEETING_CANCELED):
                continue
            events.append((_naive(it.Start), _naive(it.End), (it.Subject or "").strip(),
                           it.EntryID))
        return events


# ---------------------------------------------------------------------------
# Microsoft Graph
# ---------------------------------------------------------------------------

# The ModeSwitch app registration in the company's Entra ID tenant. Not secrets.
CLIENT_ID = "389ea0da-4306-471d-bddc-e4f19a2807fe"
TENANT_ID = "c5bab71a-cd6b-46b8-99b8-1e019a84b9ed"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Calendars.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"

# Kept beside the real database, even when MODESWITCH_DB points elsewhere for testing
CACHE_PATH = Path.home() / "AppData" / "Local" / "ModeSwitch" / "msal_cache.bin"


class NotSignedIn(Exception):
    pass


def _load_cache():
    """The token cache, encrypted with Windows DPAPI for the current user."""
    import msal
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        try:
            import win32crypt
            _, data = win32crypt.CryptUnprotectData(CACHE_PATH.read_bytes(), None, None, None, 0)
            cache.deserialize(data.decode("utf-8"))
        except Exception:
            pass   # unreadable cache: sign in again
    return cache


def _save_cache(cache) -> None:
    if not cache.has_state_changed:
        return
    import win32crypt
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = win32crypt.CryptProtectData(cache.serialize().encode("utf-8"), "ModeSwitch", None, None, None, 0)
    CACHE_PATH.write_bytes(data)


def is_signed_in() -> bool:
    """Whether a Graph account is cached. Local only, no network."""
    if not CACHE_PATH.exists():
        return False
    import msal
    return bool(_load_cache().find(msal.TokenCache.CredentialType.ACCOUNT))


def get_token(interactive: bool) -> str:
    """A Graph access token. interactive=True may open the browser to sign in."""
    import msal
    cache = _load_cache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result and interactive:
        try:
            result = app.acquire_token_interactive(SCOPES, prompt="select_account", timeout=300)
        except msal.oauth2cli.oauth2.BrowserInteractionTimeoutError:
            raise NotSignedIn("Sign-in was not finished within 5 minutes")
    _save_cache(cache)
    if not result:
        raise NotSignedIn("Not signed in to Microsoft Graph")
    if "access_token" not in result:
        raise NotSignedIn(result.get("error_description") or result.get("error") or "Sign-in failed")
    return result["access_token"]


def sign_out() -> None:
    CACHE_PATH.unlink(missing_ok=True)


def _graph_local(stamp: dict) -> datetime:
    """Graph returns UTC unless asked otherwise; convert to local, naive."""
    utc = datetime.fromisoformat(stamp["dateTime"][:19]).replace(tzinfo=timezone.utc)
    return utc.astimezone().replace(tzinfo=None)


def _graph_keep(event: dict) -> bool:
    """Skip all-day, cancelled, declined and free events."""
    if event.get("isAllDay") or event.get("isCancelled"):
        return False
    if event.get("showAs") == "free":
        return False
    return (event.get("responseStatus") or {}).get("response") != "declined"


def graph_events(first: date, last: date, interactive: bool = False) -> list[Event]:
    import requests
    token = get_token(interactive)
    start = datetime.combine(first, datetime.min.time()).astimezone()
    end = datetime.combine(last + timedelta(days=1), datetime.min.time()).astimezone()
    url = f"{GRAPH}/me/calendarView"
    params = {
        "startDateTime": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "$select": "id,subject,start,end,isAllDay,isCancelled,showAs,responseStatus",
        "$orderby": "start/dateTime",
        "$top": "200",
    }
    headers = {"Authorization": f"Bearer {token}"}
    raw = []
    while url:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        raw.extend(body.get("value", []))
        url, params = body.get("@odata.nextLink"), None   # nextLink carries the query
    return [(_graph_local(ev["start"]), _graph_local(ev["end"]),
             (ev.get("subject") or "").strip(), ev.get("id"))
            for ev in raw if _graph_keep(ev)]


# ---------------------------------------------------------------------------

def fetch_meetings(first: date, last: date,
                   outlook: OutlookReader) -> tuple[str, dict[str, list[Meeting]]]:
    """(source name, meetings per day). Graph if signed in, otherwise classic Outlook."""
    if is_signed_in():
        return "Microsoft Graph", _split_by_day(graph_events(first, last), first, last)
    return "Outlook", _split_by_day(outlook.events(first, last), first, last)


def test_outlook(profile: str = "") -> int:
    """Read today's meetings through classic Outlook on a fresh connection; returns how
    many there are. Run it on its own thread: it opens its own COM link."""
    today = date.today()
    return len(_split_by_day(OutlookReader(profile).events(today, today),
                             today, today)[today.isoformat()])


if __name__ == "__main__":
    today = date.today()
    if "--graph" in sys.argv:
        events = graph_events(today, today, interactive=True)
    else:
        events = OutlookReader().events(today, today)
    meetings = _split_by_day(events, today, today)[today.isoformat()]
    for m in meetings:
        print(f"{m.start_time}-{m.end_time}  {m.title}")
    print(f"{len(meetings)} meetings today")

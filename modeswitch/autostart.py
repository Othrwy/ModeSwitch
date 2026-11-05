"""
Starting ModeSwitch automatically, and making sure only one copy runs.

Autostart is a Windows scheduled task for this user, triggered at logon, on unlock
and on waking from sleep or hibernation. A Startup-folder shortcut only runs at
logon, and a laptop that sleeps overnight can go days without one. The task is set
to ignore a trigger while it is already running, and single_instance() covers copies
started any other way.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "ModeSwitch"
STARTUP_SHORTCUT = Path(os.environ.get("APPDATA", "")) / \
    "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "ModeSwitch.lnk"
MUTEX_NAME = "Local\\ModeSwitch.SingleInstance"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_mutex = None   # held for the life of the process


def single_instance() -> bool:
    """True if this is the only copy running. Claims the name for this process."""
    global _mutex
    if sys.platform != "win32":
        return True
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() != 183   # ERROR_ALREADY_EXISTS


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True,
                          creationflags=_NO_WINDOW)


def is_enabled() -> bool:
    return _schtasks("/Query", "/TN", TASK_NAME).returncode == 0


def _command() -> tuple[str, str, str]:
    """(program, arguments, working directory) that launch the app with no console."""
    if getattr(sys, "frozen", False):
        return sys.executable, "", str(Path(sys.executable).parent)
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    project = Path(__file__).parent.parent
    return str(pythonw if pythonw.exists() else exe), f'"{project / "main.py"}"', str(project)


def _user_sid() -> str:
    import win32api, win32con, win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    return win32security.ConvertSidToStringSid(sid)


def _task_xml() -> str:
    program, arguments, workdir = _command()
    sid = _user_sid()
    wake = ("<QueryList><Query Id=\"0\" Path=\"System\"><Select Path=\"System\">"
            "*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1]]"
            "</Select></Query></QueryList>")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Starts ModeSwitch at logon, on unlock and on waking, unless it is already running.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{sid}</UserId></LogonTrigger>
    <SessionStateChangeTrigger>
      <Enabled>true</Enabled><StateChange>SessionUnlock</StateChange><UserId>{sid}</UserId>
    </SessionStateChangeTrigger>
    <EventTrigger><Enabled>true</Enabled><Subscription>{escape(wake)}</Subscription></EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{sid}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(program)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(workdir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def enable() -> None:
    """Register the task (replacing any older Startup-folder shortcut). Raises on failure."""
    fd, path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(_task_xml())
        result = _schtasks("/Create", "/TN", TASK_NAME, "/XML", path, "/F")
    finally:
        os.unlink(path)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    if STARTUP_SHORTCUT.exists():
        STARTUP_SHORTCUT.unlink()


def disable() -> None:
    if is_enabled():
        _schtasks("/Delete", "/TN", TASK_NAME, "/F")
    if STARTUP_SHORTCUT.exists():
        STARTUP_SHORTCUT.unlink()


def migrate_shortcut() -> None:
    """Swap an autostart shortcut from before the scheduled task for the task."""
    if STARTUP_SHORTCUT.exists() and not is_enabled():
        try:
            enable()
        except Exception:
            pass   # the shortcut still works at logon

"""
Windows app bar — reserves a strip down one edge of a monitor, the same way the
taskbar does, so maximised and snapped windows stop at the ribbon instead of
going underneath it.

All rectangles here are physical pixels (Win32 coordinates).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

ABM_NEW, ABM_REMOVE, ABM_QUERYPOS, ABM_SETPOS = 0, 1, 2, 3
ABN_POSCHANGED, ABN_FULLSCREENAPP = 1, 2
ABE_LEFT, ABE_RIGHT = 0, 2

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
MONITOR_DEFAULTTONEAREST = 2

EDGES = {"left": ABE_LEFT, "right": ABE_RIGHT}


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT),
                ("rc", wintypes.RECT),
                ("lParam", wintypes.LPARAM)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


_shell32 = ctypes.windll.shell32
_user32 = ctypes.windll.user32
_shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
_shell32.SHAppBarMessage.restype = ctypes.c_size_t
_user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
_user32.RegisterWindowMessageW.restype = wintypes.UINT
_user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
_user32.MonitorFromPoint.restype = wintypes.HMONITOR
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]

CALLBACK_MSG = _user32.RegisterWindowMessageW("ModeSwitchAppBar")
TASKBAR_CREATED_MSG = _user32.RegisterWindowMessageW("TaskbarCreated")

Rect = tuple[int, int, int, int]   # left, top, right, bottom


def monitor_rects(x: int, y: int) -> tuple[Rect, Rect]:
    """(whole monitor, work area) of the monitor containing the physical point."""
    hmon = _user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    _user32.GetMonitorInfoW(hmon, ctypes.byref(info))
    m, w = info.rcMonitor, info.rcWork
    return (m.left, m.top, m.right, m.bottom), (w.left, w.top, w.right, w.bottom)


class AppBar:
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.registered = False

    def _data(self) -> APPBARDATA:
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self.hwnd
        abd.uCallbackMessage = CALLBACK_MSG
        return abd

    def register(self) -> bool:
        if not self.registered:
            self.registered = bool(_shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(self._data())))
        return self.registered

    def remove(self) -> None:
        if self.registered:
            _shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(self._data()))
            self.registered = False

    def dock(self, monitor: Rect, edge: str, width: int) -> Optional[Rect]:
        """Reserve `width` pixels down `edge` of `monitor`. Returns the rect granted."""
        if not self.register():
            return None
        abd = self._data()
        abd.uEdge = EDGES[edge]
        abd.rc = wintypes.RECT(*monitor)

        def fit_width():
            if edge == "left":
                abd.rc.right = abd.rc.left + width
            else:
                abd.rc.left = abd.rc.right - width

        fit_width()
        _shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))   # step past other bars
        fit_width()
        _shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        rc = abd.rc
        return rc.left, rc.top, rc.right, rc.bottom

    def set_topmost(self, topmost: bool) -> None:
        _user32.SetWindowPos(self.hwnd, HWND_TOPMOST if topmost else HWND_NOTOPMOST,
                             0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

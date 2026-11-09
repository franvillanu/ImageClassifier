"""Leave fullscreen straight back to maximized, without a visible shrink (SPEC-001 FS-9).

Qt on Windows leaves fullscreen for maximized by passing through the window's *normal* placement
(measured: fullscreen -> 1024x768 at (100, 100) -> maximized), so the app visibly shrinks and
grows back. While the window is still maximized, the normal placement is set to the monitor's
work area, which is invisible; the pass-through then has the maximized size. Afterwards the
user's real normal placement is put back, again while maximized, so un-maximizing later still
returns to the size the user had.
"""
import sys


def _api():
    import ctypes
    import ctypes.wintypes as wt

    class WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [("length", wt.UINT), ("flags", wt.UINT), ("showCmd", wt.UINT),
                    ("ptMinPosition", wt.POINT), ("ptMaxPosition", wt.POINT), ("rcNormalPosition", wt.RECT)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    return ctypes, wt, ctypes.windll.user32, WINDOWPLACEMENT, MONITORINFO


def _placement(hwnd):
    ctypes, wt, user32, WINDOWPLACEMENT, _ = _api()
    placement = WINDOWPLACEMENT()
    placement.length = ctypes.sizeof(WINDOWPLACEMENT)
    if not user32.GetWindowPlacement(wt.HWND(hwnd), ctypes.byref(placement)):
        return None
    return placement


def get_normal_rect(hwnd):
    """The window's normal (restored) rectangle in workspace coordinates, or None."""
    if sys.platform != "win32":
        return None
    placement = _placement(hwnd)
    if placement is None:
        return None
    r = placement.rcNormalPosition
    return (r.left, r.top, r.right, r.bottom)


def set_normal_rect(hwnd, rect) -> bool:
    """Change only the normal rectangle; the current show state is kept (no visible change
    while the window is maximized)."""
    if sys.platform != "win32" or rect is None:
        return False
    ctypes, wt, user32, _, _ = _api()
    placement = _placement(hwnd)
    if placement is None:
        return False
    placement.rcNormalPosition = wt.RECT(*rect)
    return bool(user32.SetWindowPlacement(wt.HWND(hwnd), ctypes.byref(placement)))


def work_area_rect(hwnd):
    """The work area of the window's monitor in workspace coordinates (origin at the work area)."""
    if sys.platform != "win32":
        return None
    ctypes, wt, user32, _, MONITORINFO = _api()
    user32.MonitorFromWindow.restype = wt.HMONITOR
    monitor = user32.MonitorFromWindow(wt.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    w = info.rcWork
    return (0, 0, w.right - w.left, w.bottom - w.top)

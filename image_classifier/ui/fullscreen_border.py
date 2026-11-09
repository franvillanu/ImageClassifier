"""Keep fullscreen OpenGL windows composited on Windows (SPEC-001 FS-7).

A borderless popup that covers the whole monitor with an OpenGL surface is switched by
Windows/DWM into direct fullscreen presentation. Every switch in or out of that mode blacks the
screen for a moment and redraws everything ("black wall"), and it happens again each time another
window (a dialog, the slideshow player) appears over it or replaces it.

Qt's Windows plugin avoids that with a 1-pixel border in fullscreen (``HasBorderInFullScreen``),
while keeping its own fullscreen state correct. PyQt6 does not expose the C++ setter, but the plugin
honours the window property below. It is only read when the native window is created, so the
native window is created, given the property and recreated, before the widget is first shown.
Setting ``WS_BORDER`` by hand instead makes Qt think the window left fullscreen (measured).

Windows draws that border in the classic frame colour (grey ``#646464``), which made fullscreen
look like a window (SPEC-001 FS-8). ``handle_frame_message`` paints it in the background colour
instead, from the window's ``nativeEvent``, only while fullscreen.
"""
from PyQt6.QtGui import QGuiApplication

BORDER_IN_FULLSCREEN_PROPERTY = "_q_has_border_in_fullscreen"


def enable_border_in_fullscreen(widget) -> bool:
    """Call on a top-level widget before its first show. Returns True when applied."""
    if QGuiApplication.platformName() != "windows":
        return False
    if widget.isVisible():
        raise RuntimeError("enable_border_in_fullscreen must run before the window is shown")
    widget.winId()  # create the QWindow and its native window (hidden)
    handle = widget.windowHandle()
    if handle is None:
        return False
    handle.setProperty(BORDER_IN_FULLSCREEN_PROPERTY, True)
    handle.destroy()  # the plugin reads the property only at creation
    handle.create()
    return True


def has_border_in_fullscreen(widget) -> bool:
    handle = widget.windowHandle()
    return bool(handle is not None and handle.property(BORDER_IN_FULLSCREEN_PROPERTY))


WM_NCPAINT = 0x0085
WM_NCACTIVATE = 0x0086
RDW_INVALIDATE = 0x0001
RDW_FRAME = 0x0400


def colorref(hex_color: str) -> int:
    """'#RRGGBB' to a Win32 COLORREF (0x00BBGGRR)."""
    value = hex_color.lstrip("#")
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return (b << 16) | (g << 8) | r


def paint_frame(hwnd: int, hex_color: str) -> None:
    """Fill the 1-pixel window frame with ``hex_color``."""
    import ctypes
    import ctypes.wintypes as wt

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetWindowDC.restype = wt.HDC
    user32.GetWindowDC.argtypes = [wt.HWND]
    user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]
    gdi32.CreateSolidBrush.restype = wt.HBRUSH
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    rect = wt.RECT()
    user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    dc = user32.GetWindowDC(wt.HWND(hwnd))
    if not dc:
        return
    brush = gdi32.CreateSolidBrush(colorref(hex_color))
    try:
        for edge in (wt.RECT(0, 0, width, 1), wt.RECT(0, height - 1, width, height),
                     wt.RECT(0, 0, 1, height), wt.RECT(width - 1, 0, width, height)):
            user32.FillRect(dc, ctypes.byref(edge), brush)
    finally:
        gdi32.DeleteObject(brush)
        user32.ReleaseDC(wt.HWND(hwnd), dc)


def handle_frame_message(widget, message, hex_color, painter=paint_frame):
    """For ``nativeEvent``: a (handled, result) tuple for frame messages while fullscreen, or None
    to let Qt handle the message. Never raises: an exception here would kill the app."""
    try:
        if not widget.isFullScreen():
            return None
        import ctypes.wintypes as wt

        msg = wt.MSG.from_address(int(message))
        if msg.message == WM_NCPAINT:
            painter(int(widget.winId()), hex_color)
            return True, 0
        if msg.message == WM_NCACTIVATE:
            painter(int(widget.winId()), hex_color)
            return True, 1  # TRUE: allow the activation change, frame already painted
    except Exception:
        return None
    return None


def refresh_frame(widget) -> None:
    """Ask Windows to repaint the frame (after a theme change while fullscreen)."""
    try:
        import ctypes

        ctypes.windll.user32.RedrawWindow(int(widget.winId()), None, None, RDW_FRAME | RDW_INVALIDATE)
    except Exception:
        pass

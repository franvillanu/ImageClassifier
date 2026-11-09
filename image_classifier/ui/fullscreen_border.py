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

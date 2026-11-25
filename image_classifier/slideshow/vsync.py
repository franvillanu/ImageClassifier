"""Frame pacing from the Windows desktop compositor (SPEC-002 SG-2).

Timer-driven frames drift against the screen refresh: measured on a 60 Hz 4K screen, the
slideshow's even 16 ms frames reached the screen as a still refresh followed by a double jump
about 7 times per second. ``DwmFlush`` returns once per composition, so a thread that loops on
it gives one tick per refresh, just after the compositor took the previous frame.
"""
import sys
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QGuiApplication


def _dwm_flush():
    """Return the DwmFlush function, or None where DWM pacing is not available."""
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
        return None
    try:
        import ctypes
        dwmapi = ctypes.WinDLL("dwmapi")
        enabled = ctypes.c_int(0)
        if dwmapi.DwmIsCompositionEnabled(ctypes.byref(enabled)) != 0 or not enabled.value:
            return None
        return dwmapi.DwmFlush
    except (OSError, AttributeError):
        return None


class VBlankPacer(QObject):
    """Emits ``tick`` on the GUI thread once per desktop composition while running."""

    tick = pyqtSignal()

    def __init__(self, parent=None, flush=None):
        super().__init__(parent)
        self._flush = flush if flush is not None else _dwm_flush()
        self._running = False
        self._thread = None
        self._pending = threading.Event()  # a tick is queued and not yet handled: never pile up ticks
        self.tick.connect(self._delivered)

    @property
    def available(self):
        return self._flush is not None

    @property
    def running(self):
        return self._running

    def start(self):
        if self._flush is None or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="slideshow-vblank", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(0.2)

    def _delivered(self):
        self._pending.clear()

    def _loop(self):
        while self._running:
            started = time.perf_counter()
            failed = self._flush() != 0
            if failed or time.perf_counter() - started < 0.001:
                # no composition happened (error, minimised, screen off): do not spin the CPU
                time.sleep(0.008)
            if self._running and not self._pending.is_set():
                self._pending.set()
                self.tick.emit()

"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, frame pacing (SG-2)."""
import threading
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication

from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings
from image_classifier.slideshow.vsync import VBlankPacer

REQUIRES = ["SG-2"]


def _run(qapp, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.002)


@pytest.fixture
def player(qapp, tmp_path):
    QStandardPaths.setTestModeEnabled(True)
    paths = []
    for index in range(2):
        path = tmp_path / f"v{index}.jpg"
        Image.new("RGB", (800, 400), (60 + index * 80, 90, 140)).save(path)
        paths.append(str(path))
    win = PlayerWindow(paths, paths[0], SlideshowSettings(30, 100, False, True, False), raster=True)
    win.resize(1000, 600)
    win.show()
    end = time.monotonic() + 5
    while time.monotonic() < end and (win.surface.pixmap is None or win.surface.entry is None):
        qapp.processEvents()
        time.sleep(0.004)
    yield win
    win.close()


class _RunningPacer:
    running = True

    def stop(self):
        self.running = False


def test_sg2_with_the_pacer_only_the_refresh_tick_advances_and_paints(player, qapp, monkeypatch):
    """SG-2: while the compositor pacer runs, the 16 ms timers neither tick the motion nor request
    paints; each refresh tick advances the motion clock and the view glide and paints once."""
    _run(qapp, 0.1)
    player.pacer.stop()
    player.pacer = _RunningPacer()
    ticks, paints = [], []
    monkeypatch.setattr(player.controller, "tick", lambda: ticks.append(1))
    player.surface.framePainted.connect(lambda: paints.append(1))
    player._start_view_animation()
    _run(qapp, 0.15)  # timers keep firing, but stand down
    assert ticks == [] and paints == []
    player._on_vblank()
    qapp.processEvents()
    assert ticks == [1] and len(paints) == 1


def test_sg2_timers_drive_frames_where_the_pacer_is_unavailable(player, qapp):
    """SG-2: on the offscreen test platform there is no compositor pacer; the timers drive the show."""
    assert not player.pacer.available and not player.pacer.running
    before = player.controller.progress
    _run(qapp, 0.2)
    assert player.controller.progress > before


def test_sg2_pacer_ticks_once_per_composition_on_the_gui_thread_without_piling_up(qapp):
    """SG-2: one tick per DwmFlush return, delivered on the GUI thread; ticks never queue up while
    the GUI is busy; stop ends the thread."""
    flushes = []

    def flush():
        time.sleep(0.005)
        flushes.append(1)
        return 0

    pacer = VBlankPacer(flush=flush)
    seen = []
    pacer.tick.connect(lambda: seen.append(threading.current_thread() is threading.main_thread()))
    pacer.start()
    time.sleep(0.1)  # GUI busy: ~20 compositions, but at most one tick may wait
    qapp.processEvents()
    assert len(seen) == 1 and seen[0]
    _run(qapp, 0.1)
    assert len(seen) > 5 and all(seen)
    pacer.stop()
    count = len(flushes)
    time.sleep(0.05)
    assert len(flushes) <= count + 1 and not pacer.running


def test_sg2_pacer_does_not_spin_when_no_composition_happens(qapp):
    """SG-2: DwmFlush failing (or returning at once: minimised, screen off) must not burn a CPU core."""
    calls = []
    pacer = VBlankPacer(flush=lambda: calls.append(1) or 1)
    pacer.start()
    time.sleep(0.2)
    pacer.stop()
    assert len(calls) <= 30  # ~8 ms back-off per failed call


def test_sg2_closing_stops_the_pacer(player, qapp):
    """SG-2: the pacer stops with the slideshow."""
    stub = _RunningPacer()
    player.pacer = stub
    player.close()
    assert stub.running is False


def _make_player(tmp_path, name):
    paths = []
    for index in range(2):
        path = tmp_path / f"{name}{index}.jpg"
        Image.new("RGB", (400, 200), (90, 90, 140)).save(path)
        paths.append(str(path))
    return PlayerWindow(paths, paths[0], SlideshowSettings(30, 100, False, True, False), raster=True)


def test_sg2_swap_interval_zero_only_while_the_paced_slideshow_is_open(qapp, tmp_path, monkeypatch):
    """SG-2: with the pacer available, windows created for the slideshow get swap interval 0, and the
    app's previous default format comes back when it closes."""
    from PyQt6.QtGui import QSurfaceFormat
    import image_classifier.slideshow.vsync as vsync

    QStandardPaths.setTestModeEnabled(True)
    before = QSurfaceFormat.defaultFormat()
    assert before.swapInterval() != 0
    monkeypatch.setattr(vsync, "_dwm_flush", lambda: (lambda: time.sleep(0.005) or 0))
    win = _make_player(tmp_path, "s")
    assert win.pacer.available
    assert QSurfaceFormat.defaultFormat().swapInterval() == 0
    win.close()
    after = QSurfaceFormat.defaultFormat()
    assert after.swapInterval() == before.swapInterval() and after.version() == before.version()


def test_sg2_swap_interval_untouched_without_the_pacer(qapp, tmp_path):
    """SG-2: no pacer (offscreen, other platforms): the GL format is left as the app set it."""
    from PyQt6.QtGui import QSurfaceFormat

    QStandardPaths.setTestModeEnabled(True)
    before = QSurfaceFormat.defaultFormat().swapInterval()
    win = _make_player(tmp_path, "u")
    assert not win.pacer.available and QSurfaceFormat.defaultFormat().swapInterval() == before
    win.close()

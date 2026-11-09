"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, wheel zoom rows (SZ-1 .. SZ-5)."""
import inspect
import time
from types import SimpleNamespace

import pytest
from PIL import Image
from PyQt6.QtCore import QPoint, QPointF, QStandardPaths, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings
from image_classifier.slideshow.surface import panned_bounds

REQUIRES = ["SZ-1", "SZ-2", "SZ-3", "SZ-4", "SZ-5"]


def _wait(qapp, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.004)
    return False


@pytest.fixture
def player(qapp, tmp_path):
    QStandardPaths.setTestModeEnabled(True)
    paths = []
    for index in range(2):
        path = tmp_path / f"z{index}.jpg"
        Image.new("RGB", (800, 400), (60 + index * 80, 90, 140)).save(path)
        paths.append(str(path))
    win = PlayerWindow(paths, paths[0], SlideshowSettings(30, 0, False, True, False), raster=True)  # strength 0: still frame
    win.resize(1000, 600)
    win.show()
    assert _wait(qapp, lambda: win.surface.pixmap is not None and win.surface.entry is not None)
    yield win
    win.close()


def _wheel(player, notches=1, at=None, modifiers=Qt.KeyboardModifier.NoModifier):
    canvas = player.surface.canvas
    pos = at if at is not None else QPointF(canvas.width() / 2, canvas.height() / 2)
    event = QWheelEvent(pos, QPointF(canvas.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, int(120 * notches)),
                        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(canvas, event)


def _settled(qapp, player):
    assert _wait(qapp, lambda: not player.pan_timer.isActive())


def test_sz1_wheel_zooms_smoothly_by_125_percent_per_notch_within_range(player, qapp):
    """SZ-1: one notch -> x1.25 reached over several frames; never below 1x or above 5x; playback continues."""
    steps = []
    original = player.surface.set_zoom
    player.surface.set_zoom = lambda z: (steps.append(z), original(z))
    _wheel(player, 1)
    _settled(qapp, player)
    assert player.surface.zoom == pytest.approx(1.25, abs=0.003)
    assert len(steps) >= 5 and max(b - a for a, b in zip([1.0] + steps, steps)) < 0.2  # no jump
    for _ in range(20):
        _wheel(player, 1)
    _settled(qapp, player)
    assert player.surface.zoom == pytest.approx(5.0, abs=0.003)
    for _ in range(30):
        _wheel(player, -1)
    _settled(qapp, player)
    assert player.surface.zoom == pytest.approx(1.0, abs=0.003)
    assert player.controller.playing


def test_sz1_ctrl_wheel_does_the_same(player, qapp):
    """SZ-1: Ctrl+wheel zooms exactly like the wheel."""
    _wheel(player, 1, modifiers=Qt.KeyboardModifier.ControlModifier)
    _settled(qapp, player)
    assert player.surface.zoom == pytest.approx(1.25, abs=0.003)


def test_sz2_point_under_pointer_stays_under_pointer(player, qapp):
    """SZ-2: zooming at an off-centre point keeps that photo point under the pointer."""
    from image_classifier.slideshow.motion import EFFECTS

    surface = player.surface
    vw, vh = surface.width(), surface.height()
    entry = surface.entry
    frame = EFFECTS[entry.effect_id].evaluate(surface.progress, (surface.pixmap.width(), surface.pixmap.height()), (vw, vh), 0)
    pointer = QPointF(vw * 0.7, vh * 0.4)

    def photo_fraction_at(px, py):
        x, y, w, h = panned_bounds(frame.bounds, surface.pan, surface.zoom, (vw, vh))
        return (px - x) / w, (py - y) / h

    before = photo_fraction_at(pointer.x(), pointer.y())
    _wheel(player, 2, at=pointer)
    _settled(qapp, player)
    after = photo_fraction_at(pointer.x(), pointer.y())
    assert after == pytest.approx(before, abs=0.01)


def test_sz3_zoom_resets_on_next_photo_survives_rotation_and_full_frame(player, qapp):
    """SZ-3: zoom kept through R and the full-resolution frame, back to 1x on the next photo."""
    _wheel(player, 2)
    _settled(qapp, player)
    zoom = player.surface.zoom
    QTest.keyClick(player, Qt.Key.Key_R)
    player._frame_updated(SimpleNamespace(image=player.surface._source.toImage()))
    assert player.surface.zoom == zoom
    first = player.surface.entry.path
    player.controller.next()
    assert _wait(qapp, lambda: player.surface.entry is not None and player.surface.entry.path != first)
    assert player.surface.zoom == 1.0 and player._zoom_target == 1.0


def test_sz4_pan_limit_grows_with_zoom(player, qapp):
    """SZ-4: zoomed in, Ctrl+arrows can move further than the unzoomed half-window limit."""
    w = player.surface.width()
    for _ in range(8):
        _wheel(player, 1)
    _settled(qapp, player)
    QTest.keyPress(player, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    end = time.monotonic() + 2.5
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.004)
    QTest.keyRelease(player, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    _settled(qapp, player)
    assert player.surface.pan[0] < -w / 2  # beyond what 1x allows
    assert panned_bounds((0, 0, 100, 50), (-1000, 0), 2.0, (100, 50))[0] == -50 - 100  # clamp = half zoomed size


def test_sz5_wheel_listed_in_sheet_and_help_both_languages():
    """SZ-5: shortcut sheet and Help list the wheel zoom, EN and ES."""
    from image_classifier.i18n.translations import translations
    from image_classifier.slideshow import settings_dialog
    import image_classifier.app as app_module

    for lang in ("en", "es"):
        t = translations[lang]
        assert t["slideshow_key_wheel"] and t["slideshow_key_zoom"]
        assert t["shortcut_slideshow_zoom_key"] and t["shortcut_slideshow_zoom_desc"]
    assert "slideshow_key_zoom" in inspect.getsource(settings_dialog.SettingsDialog._shortcuts)
    assert "shortcut_slideshow_zoom_key" in inspect.getsource(app_module.PhotoViewer.open_help_overlay)

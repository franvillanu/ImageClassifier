"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, mouse drag rows (SM-1 .. SM-4)."""
import inspect
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QEvent, QPoint, QPointF, QStandardPaths, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings

REQUIRES = ["SM-1", "SM-2", "SM-3", "SM-4"]
LEFT = Qt.MouseButton.LeftButton
NONE = Qt.MouseButton.NoButton


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
        path = tmp_path / f"d{index}.jpg"
        Image.new("RGB", (800, 400), (60 + index * 80, 90, 140)).save(path)
        paths.append(str(path))
    win = PlayerWindow(paths, paths[0], SlideshowSettings(30, 0, False, True, False), raster=True)
    win.resize(1000, 600)
    win.show()
    assert _wait(qapp, lambda: win.surface.pixmap is not None and win.surface.entry is not None)
    yield win
    win.close()


def _mouse(player, kind, pos, button, buttons, target=None):
    widget = target or player.surface.canvas
    local = QPointF(pos)
    event = QMouseEvent(kind, local, QPointF(widget.mapToGlobal(local.toPoint())), button, buttons,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def _drag(player, start, end, steps=5):
    _mouse(player, QEvent.Type.MouseButtonPress, start, LEFT, LEFT)
    for k in range(1, steps + 1):
        point = QPointF(start.x() + (end.x() - start.x()) * k / steps, start.y() + (end.y() - start.y()) * k / steps)
        _mouse(player, QEvent.Type.MouseMove, point, NONE, LEFT)
    _mouse(player, QEvent.Type.MouseButtonRelease, end, LEFT, NONE)


def test_sm1_drag_moves_the_photo_one_to_one_and_keeps_playing(player, qapp):
    """SM-1: a drag of (+120, -40) moves the photo by exactly (+120, -40); playback continues."""
    _drag(player, QPointF(500, 300), QPointF(620, 260))
    assert player.surface.pan == pytest.approx((120, -40), abs=0.5)
    assert player.controller.playing


def test_sm1_drag_shows_closed_hand_then_restores_cursor(player, qapp):
    """SM-1: closed-hand cursor while dragging, normal cursor after release."""
    canvas = player.surface.canvas
    _mouse(player, QEvent.Type.MouseButtonPress, QPointF(400, 300), LEFT, LEFT)
    _mouse(player, QEvent.Type.MouseMove, QPointF(450, 300), NONE, LEFT)
    assert canvas.cursor().shape() == Qt.CursorShape.ClosedHandCursor
    _mouse(player, QEvent.Type.MouseButtonRelease, QPointF(450, 300), LEFT, NONE)
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_sm1_drag_is_limited_and_limit_grows_with_zoom(player, qapp):
    """SM-1/SZ-4: at 1x a huge drag stops at half the window; zoomed in it can go further."""
    w = player.surface.width()
    _drag(player, QPointF(100, 300), QPointF(100 + 3 * w, 300))
    assert player.surface.pan[0] == pytest.approx(w / 2, abs=0.5)
    player._zoom_target = 3.0
    player.surface.set_zoom(3.0)
    _drag(player, QPointF(100, 300), QPointF(100 + 3 * w, 300))
    assert player.surface.pan[0] > w / 2


def test_sm2_click_without_movement_changes_nothing_and_double_click_still_toggles(player, qapp):
    """SM-2: click leaves pan/zoom/playback alone; double-click toggles fullscreen as before."""
    _mouse(player, QEvent.Type.MouseButtonPress, QPointF(500, 300), LEFT, LEFT)
    _mouse(player, QEvent.Type.MouseButtonRelease, QPointF(500, 300), LEFT, NONE)
    assert player.surface.pan == (0.0, 0.0) and player.controller.playing
    called = []
    player.toggle_fullscreen = lambda: called.append(True)
    _mouse(player, QEvent.Type.MouseButtonDblClick, QPointF(500, 300), LEFT, LEFT)
    assert called == [True]


def test_sm2_dragging_from_the_control_bar_does_not_move_the_photo(player, qapp):
    """SM-2: press on a bar button and move: the photo does not move, the button still works."""
    button = player.buttons["play"]
    playing = player.controller.playing
    _mouse(player, QEvent.Type.MouseButtonPress, QPointF(5, 5), LEFT, LEFT, target=button)
    _mouse(player, QEvent.Type.MouseMove, QPointF(80, 5), NONE, LEFT, target=button)
    _mouse(player, QEvent.Type.MouseButtonRelease, QPointF(80, 5), LEFT, NONE, target=button)
    assert player.surface.pan == (0.0, 0.0)
    button.click()
    assert player.controller.playing != playing


def test_sm3_dragged_position_resets_on_the_next_photo(player, qapp):
    """SM-3: a dragged photo starts centred again when the next photo appears."""
    _drag(player, QPointF(500, 300), QPointF(600, 300))
    first = player.surface.entry.path
    player.controller.next()
    assert _wait(qapp, lambda: player.surface.entry is not None and player.surface.entry.path != first)
    assert player.surface.pan == (0.0, 0.0)


def test_sm4_drag_listed_in_sheet_and_help_both_languages():
    """SM-4: the sheet and Help mention dragging, EN and ES."""
    from image_classifier.i18n.translations import translations
    from image_classifier.slideshow import settings_dialog
    import image_classifier.app as app_module

    for lang in ("en", "es"):
        t = translations[lang]
        assert t["slideshow_key_drag"] and t["shortcut_slideshow_drag_key"] and t["shortcut_slideshow_drag_desc"]
    assert "slideshow_key_drag" in inspect.getsource(settings_dialog.SettingsDialog._shortcuts)
    assert "shortcut_slideshow_drag_key" in inspect.getsource(app_module.PhotoViewer.open_help_overlay)

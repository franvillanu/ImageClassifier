"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, pan rows (SP-1 .. SP-4)."""
import inspect
import time
from types import SimpleNamespace

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings
from image_classifier.slideshow.surface import panned_bounds

REQUIRES = ["SP-1", "SP-2", "SP-3", "SP-4"]


def _wait(qapp, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def player(qapp, tmp_path):
    QStandardPaths.setTestModeEnabled(True)
    paths = []
    for index in range(2):
        path = tmp_path / f"p{index}.jpg"
        Image.new("RGB", (800, 400), (60 + index * 80, 90, 140)).save(path)
        paths.append(str(path))
    win = PlayerWindow(paths, paths[0], SlideshowSettings(30, 100, False, True, False), raster=True)
    win.resize(1000, 600)
    win.show()
    assert _wait(qapp, lambda: win.surface.pixmap is not None and win.surface.entry is not None)
    yield win
    win.close()


def _key(player, key):
    QTest.keyClick(player, key, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()


def test_sp1_ctrl_arrows_pan_like_scrolling_by_a_tenth_without_pausing(player, qapp):
    """SP-1: Ctrl+Right moves the photo left by a tenth of the width; Ctrl+Down moves it up; playback continues."""
    w, h = player.surface.width(), player.surface.height()
    _key(player, Qt.Key.Key_Right)
    assert player.surface.pan == pytest.approx((-w * 0.1, 0))
    _key(player, Qt.Key.Key_Down)
    assert player.surface.pan == pytest.approx((-w * 0.1, -h * 0.1))
    _key(player, Qt.Key.Key_Left)
    _key(player, Qt.Key.Key_Up)
    assert player.surface.pan == pytest.approx((0, 0))
    assert player.controller.playing


def test_sp1_plain_arrows_keep_their_old_meaning(player, qapp):
    """SP-1: without Ctrl, arrows still step photos / change speed and do not pan."""
    duration = player.controller.active_settings.duration
    QTest.keyClick(player, Qt.Key.Key_Up)
    qapp.processEvents()
    assert player.surface.pan == (0.0, 0.0)
    assert player.controller.active_settings.duration != duration


def test_sp2_pan_is_clamped_to_half_the_drawn_size():
    """SP-2: whatever the requested pan, the photo moves at most half its drawn size."""
    assert panned_bounds((100, 50, 400, 200), (-10_000, 10_000)) == (100 - 200, 50 + 100, 400, 200)
    assert panned_bounds((100, 50, 400, 200), (30, -20)) == (130, 30, 400, 200)


def test_sp2_holding_the_key_does_not_build_up_a_hidden_offset(player, qapp):
    """SP-2: after many presses, one press the other way moves the photo back immediately."""
    for _ in range(40):
        _key(player, Qt.Key.Key_Right)
    assert player.surface.pan[0] >= -player.surface.width() / 2 - 1e-6
    before = player.surface.pan[0]
    _key(player, Qt.Key.Key_Left)
    assert player.surface.pan[0] > before


def test_sp3_pan_resets_on_the_next_photo_and_survives_rotation_and_full_frame(player, qapp):
    """SP-3: pan survives R and the full-resolution frame, and is gone when the next photo appears."""
    _key(player, Qt.Key.Key_Right)
    panned = player.surface.pan
    QTest.keyClick(player, Qt.Key.Key_R)
    qapp.processEvents()
    assert player.surface.pan == panned
    player._frame_updated(SimpleNamespace(image=player.surface._source.toImage()))
    assert player.surface.pan == panned
    first = player.surface.entry.path
    player.controller.next()
    assert _wait(qapp, lambda: player.surface.entry is not None and player.surface.entry.path != first)
    assert player.surface.pan == (0.0, 0.0)


def test_sp4_pan_keys_listed_in_sheet_and_help_in_both_languages():
    """SP-4: shortcut sheet and Help list mention Ctrl+arrows, EN and ES."""
    from image_classifier.i18n.translations import translations
    from image_classifier.slideshow import settings_dialog
    import image_classifier.app as app_module

    for lang in ("en", "es"):
        t = translations[lang]
        assert t["slideshow_key_pan"] and "Ctrl" in t["shortcut_slideshow_pan_key"] and t["shortcut_slideshow_pan_desc"]
    assert "slideshow_key_pan" in inspect.getsource(settings_dialog.SettingsDialog._shortcuts)
    assert "shortcut_slideshow_pan_key" in inspect.getsource(app_module.PhotoViewer.open_help_overlay)

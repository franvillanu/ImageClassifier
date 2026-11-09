"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, pan rows (SP-1 .. SP-4) and SD-4."""
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

REQUIRES = ["SP-1", "SP-2", "SP-3", "SP-4", "SD-4"]
CTRL = Qt.KeyboardModifier.ControlModifier


def _wait(qapp, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


def _run(qapp, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.003)


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


def _settled(qapp, player):
    assert _wait(qapp, lambda: not player.pan_timer.isActive())


def test_sp1_tap_glides_through_several_frames_to_five_percent(player, qapp):
    """SP-1: a tap of Ctrl+Right ends 5% of the width to the left, reached over several frames (no jump)."""
    steps = []
    original = player.surface.set_pan
    player.surface.set_pan = lambda pan: (steps.append(pan[0]), original(pan))
    QTest.keyClick(player, Qt.Key.Key_Right, CTRL)
    _settled(qapp, player)
    w = player.surface.width()
    assert player.surface.pan[0] == pytest.approx(-0.05 * w, abs=0.6)
    assert len(steps) >= 5
    assert max(abs(b - a) for a, b in zip([0.0] + steps, steps)) < 0.05 * w * 0.6  # no single big jump
    assert player.controller.playing


def test_sp1_holding_moves_continuously_and_stops_on_release(player, qapp):
    """SP-1: holding keeps moving (about half the window per second); after release it eases to a stop."""
    w = player.surface.width()
    QTest.keyPress(player, Qt.Key.Key_Right, CTRL)
    _run(qapp, 0.25)
    early = player.surface.pan[0]
    _run(qapp, 0.25)
    later = player.surface.pan[0]
    assert later < early < 0  # still moving left while held
    QTest.keyRelease(player, Qt.Key.Key_Right, CTRL)
    _settled(qapp, player)
    stopped = player.surface.pan[0]
    _run(qapp, 0.2)
    assert player.surface.pan[0] == stopped
    assert -0.5 * w <= stopped <= -0.2 * w  # 5% tap + ~0.5 s at 0.5 w/s, eased


def test_sp1_releasing_ctrl_first_still_stops(player, qapp):
    """SP-1: arrow released without Ctrl (Ctrl let go first) ends the hold."""
    QTest.keyPress(player, Qt.Key.Key_Down, CTRL)
    _run(qapp, 0.1)
    QTest.keyRelease(player, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    _settled(qapp, player)
    assert player._pan_held == set()


def test_sp1_plain_arrows_keep_their_old_meaning(player, qapp):
    """SP-1: without Ctrl, arrows still step photos / change speed and do not pan."""
    duration = player.controller.active_settings.duration
    QTest.keyClick(player, Qt.Key.Key_Up)
    qapp.processEvents()
    assert player.surface.pan == (0.0, 0.0) and not player.pan_timer.isActive()
    assert player.controller.active_settings.duration != duration


def test_sp2_pan_is_clamped_to_half_the_drawn_size():
    """SP-2: whatever the requested pan, the photo moves at most half its drawn size."""
    assert panned_bounds((100, 50, 400, 200), (-10_000, 10_000)) == (100 - 200, 50 + 100, 400, 200)
    assert panned_bounds((100, 50, 400, 200), (30, -20)) == (130, 30, 400, 200)


def test_sp2_long_hold_does_not_build_up_a_hidden_offset(player, qapp):
    """SP-2: after holding far past the limit, the other direction moves back immediately."""
    QTest.keyPress(player, Qt.Key.Key_Right, CTRL)
    _run(qapp, 1.5)
    QTest.keyRelease(player, Qt.Key.Key_Right, CTRL)
    _settled(qapp, player)
    assert player.surface.pan[0] >= -player.surface.width() / 2 - 1e-6
    before = player.surface.pan[0]
    QTest.keyClick(player, Qt.Key.Key_Left, CTRL)
    _settled(qapp, player)
    assert player.surface.pan[0] > before


def test_sp3_pan_resets_on_the_next_photo_and_survives_rotation_and_full_frame(player, qapp):
    """SP-3: pan survives R and the full-resolution frame, and is gone when the next photo appears."""
    QTest.keyClick(player, Qt.Key.Key_Right, CTRL)
    _settled(qapp, player)
    panned = player.surface.pan
    QTest.keyClick(player, Qt.Key.Key_R)
    qapp.processEvents()
    assert player.surface.pan == panned
    player._frame_updated(SimpleNamespace(image=player.surface._source.toImage()))
    assert player.surface.pan == panned
    first = player.surface.entry.path
    player.controller.next()
    assert _wait(qapp, lambda: player.surface.entry is not None and player.surface.entry.path != first)
    assert player.surface.pan == (0.0, 0.0) and player._pan_target == (0.0, 0.0)


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


def test_sd4_playback_dialog_has_no_next_slide_note(qapp):
    """SD-4: the dialog opened during playback shows no 'changes apply to the next slide' note."""
    from PyQt6.QtWidgets import QLabel
    from image_classifier.i18n.translations import translations
    from image_classifier.slideshow.settings_dialog import SettingsDialog

    for lang in ("en", "es"):
        dialog = SettingsDialog(SlideshowSettings(), lang, playback=True)
        texts = [label.text().lower() for label in dialog.findChildren(QLabel)]
        assert not any("next slide" in t or "siguiente foto" in t for t in texts)
        dialog.close()
        assert "slideshow_next_settings" not in translations[lang]

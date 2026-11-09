"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, rotation rows (SR-1 .. SR-4)."""
import json
import os
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings

REQUIRES = ["SR-1", "SR-2", "SR-3", "SR-4"]


def _wait(qapp, condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def photos(tmp_path):
    paths = []
    for index in range(2):
        path = tmp_path / f"wide{index}.jpg"
        Image.new("RGB", (800, 400), (60 + index * 80, 90, 140)).save(path)  # landscape 2:1
        paths.append(str(path))
    return paths


@pytest.fixture
def player(qapp, photos):
    QStandardPaths.setTestModeEnabled(True)
    win = PlayerWindow(photos, photos[0], SlideshowSettings(30, 100, False, True, False), raster=True)
    win.resize(900, 600)
    win.show()
    assert _wait(qapp, lambda: win.surface.pixmap is not None and win.controller.entry is not None)
    yield win
    win.close()


def _press_r(player):
    QTest.keyClick(player, Qt.Key.Key_R)
    QApplication.processEvents()


def test_sr1_r_rotates_clockwise_in_90_degree_steps_without_stopping(player, qapp):
    """SR-1: each R adds 90° clockwise (0, 90, 180, 270, 0); playing and progress are unaffected."""
    assert player.controller.playing
    seen = []
    for _ in range(4):
        before = player.controller.progress
        _press_r(player)
        seen.append(player.surface.rotation)
        assert player.controller.playing
        assert player.controller.progress >= before
    assert seen == [90, 180, 270, 0]


def test_sr1_rotation_is_clockwise(player, qapp):
    """SR-1: 'to the right' means the left edge of the photo ends up at the top."""
    source = player.surface._source.toImage()
    left_colour = source.pixelColor(0, source.height() // 2)
    _press_r(player)
    rotated = player.surface.pixmap.toImage()
    top_colour = rotated.pixelColor(rotated.width() // 2, 0)
    assert abs(left_colour.red() - top_colour.red()) <= 8


def test_sr2_rotation_stays_with_the_photo_for_this_run_only(player, qapp, photos):
    """SR-2: the photo keeps its rotation when shown again; the next photo starts unrotated."""
    first = player.surface.entry.path
    _press_r(player)
    player.controller.next()
    assert _wait(qapp, lambda: player.surface.entry is not None and player.surface.entry.path != first)
    assert player.surface.rotation == 0
    player.controller.previous()
    assert _wait(qapp, lambda: player.surface.entry.path == first and player.surface.rotation == 90)


def test_sr2_r_in_the_loading_gap_turns_the_photo_on_screen(player, qapp):
    """SR-2: right after Next, before the next photo appears, R turns the photo still on screen."""
    shown = player.surface.entry.path
    player.controller.next()
    _press_r(player)
    assert player._rotations == {shown: 90}


def test_sr2_rotation_never_touches_the_file_or_a_new_slideshow(player, qapp, photos):
    """SR-2: the file on disk is unchanged and a new slideshow starts unrotated."""
    before = (os.path.getmtime(photos[0]), os.path.getsize(photos[0]))
    _press_r(player)
    _press_r(player)
    qapp.processEvents()
    assert (os.path.getmtime(photos[0]), os.path.getsize(photos[0])) == before
    fresh = PlayerWindow(photos, photos[0], SlideshowSettings(30, 100, False, True, False), raster=True)
    fresh.show()
    assert _wait(qapp, lambda: fresh.surface.pixmap is not None)
    assert fresh.surface.rotation == 0 and fresh._rotations == {}
    fresh.close()


def test_sr2_classifier_rotation_and_config_untouched(qapp, tmp_path, photos, monkeypatch):
    """SR-2: rotating in the slideshow leaves the classifier's per-photo rotations and config alone."""
    import image_classifier.app as app_module

    config = tmp_path / "viewer_config.json"
    config.write_text(json.dumps({"last_seen_version": app_module.__version__}))
    monkeypatch.setattr(app_module, "get_config_file", lambda: str(config))
    win = app_module.PhotoViewer()
    win.load_directory(os.path.dirname(photos[0]), start_at_first=True)
    win.slideshow_settings = SlideshowSettings(30, 100, False, True, False)
    rotations_before = dict(win.image_rotations)
    monkeypatch.setattr(app_module.QDialog, "exec", lambda self: app_module.QDialog.DialogCode.Accepted)
    win.open_slideshow()
    player = win._slideshow_player
    assert _wait(qapp, lambda: player.surface.pixmap is not None)
    config_before = config.read_text()
    _press_r(player)
    assert win.image_rotations == rotations_before
    assert config.read_text() == config_before
    player.close()
    win._cancel_preloads()
    win.image_viewer._cancel_pending_loads()
    win._marked_save_timer.stop()
    win.close()


def test_sr3_rotated_photo_is_fitted_with_swapped_proportions(player, qapp):
    """SR-3: a landscape photo turned 90° is fitted as portrait (taller than wide on screen)."""
    from image_classifier.slideshow.motion import EFFECTS

    w0, h0 = player.surface.pixmap.width(), player.surface.pixmap.height()
    assert w0 > h0
    _press_r(player)
    w1, h1 = player.surface.pixmap.width(), player.surface.pixmap.height()
    assert (w1, h1) == (h0, w0)
    entry = player.surface.entry
    frame = EFFECTS[entry.effect_id].evaluate(0.5, (w1, h1), (900, 600), 0)
    assert frame.bounds[3] > frame.bounds[2]


def test_sr3_rotation_survives_the_full_resolution_frame(player, qapp):
    """SR-3: when the sharper frame for the same photo arrives, the rotation is kept."""
    _press_r(player)
    from types import SimpleNamespace

    frame = SimpleNamespace(image=player.surface._source.toImage())
    player._frame_updated(frame)
    assert player.surface.rotation == 90
    assert player.surface.pixmap.height() > player.surface.pixmap.width()


def test_sr4_r_is_listed_in_the_settings_sheet_and_help_in_both_languages():
    """SR-4: the shortcut appears in the slideshow settings sheet and the Help list (EN and ES)."""
    import inspect

    from image_classifier.i18n.translations import translations
    from image_classifier.slideshow import settings_dialog
    import image_classifier.app as app_module

    for lang in ("en", "es"):
        t = translations[lang]
        assert t["slideshow_key_rotate"]
        assert t["shortcut_slideshow_rotate_key"] == "R"
        assert "90" in t["shortcut_slideshow_rotate_desc"]
    assert 'slideshow_key_rotate' in inspect.getsource(settings_dialog.SettingsDialog._shortcuts)
    assert 'shortcut_slideshow_rotate_key' in inspect.getsource(app_module.PhotoViewer.open_help_overlay)

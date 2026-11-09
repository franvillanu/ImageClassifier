"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, revisit (SV-1 .. SV-3) and exit (SX-1, SX-2)."""
import json
import random
import time
from dataclasses import replace

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QDialog

from image_classifier.slideshow.controller import SlideshowController
from image_classifier.slideshow.settings import SlideshowSettings
from tests.test_slideshow import Loader, present

REQUIRES = ["SV-1", "SV-2", "SV-3", "SX-1", "SX-2"]


def _controller(new_motion):
    loader = Loader()
    settings = SlideshowSettings(10, 100, False, True, False, new_motion_on_revisit=new_motion)
    c = SlideshowController(("a", "b", "c"), "a", settings, loader, clock=lambda: 0.0, rng=random.Random(7))
    c.start()
    present(c, loader)
    return c, loader


def _effects_on_revisits(c, loader, rounds=6):
    """Go a -> b and back to a several times; return the effect of 'a' at every visit."""
    seen = [c.entry.effect_id]
    for _ in range(rounds):
        c.next()
        present(c, loader)
        c.previous()
        present(c, loader)
        assert c.entry.path == "a"
        seen.append(c.entry.effect_id)
    return seen


def test_sv1_setting_defaults_off_round_trips_and_is_in_the_dialog(qapp):
    """SV-1: off by default, old configs load off, invalid values fall back, saved and editable in the dialog."""
    from image_classifier.slideshow.settings_dialog import SettingsDialog

    assert SlideshowSettings().new_motion_on_revisit is False
    assert SlideshowSettings.from_dict({"duration": 12}).new_motion_on_revisit is False  # config from older versions
    assert SlideshowSettings.from_dict({"new_motion_on_revisit": "yes"}).new_motion_on_revisit is False
    on = SlideshowSettings(new_motion_on_revisit=True)
    assert SlideshowSettings.from_dict(on.to_dict()) == on
    dialog = SettingsDialog(on, "es")
    assert dialog.switches["new_motion_on_revisit"].isChecked()
    dialog.switches["new_motion_on_revisit"].setChecked(False)
    assert dialog.settings().new_motion_on_revisit is False
    from image_classifier.i18n.translations import translations

    assert translations["en"]["slideshow_new_motion_on_revisit"] and translations["es"]["slideshow_new_motion_on_revisit"]


def test_sv2_revisit_plays_a_different_effect_each_time_when_on(qapp):
    """SV-2: with the setting on, every return to a photo uses a different effect than the visit before."""
    c, loader = _controller(True)
    seen = _effects_on_revisits(c, loader)
    assert all(a != b for a, b in zip(seen, seen[1:])), seen
    assert [e.path for e in c.history[:3]] == ["a", "b", "c"]  # order unchanged
    c.close()


def test_sv3_revisit_replays_the_same_effect_when_off(qapp):
    """SV-3: with the setting off, a revisited photo keeps its effect (previous behaviour)."""
    c, loader = _controller(False)
    seen = _effects_on_revisits(c, loader)
    assert len(set(seen)) == 1, seen
    c.close()


def test_sv2_first_visits_are_not_rerolled(qapp):
    """SV-2: only revisits change; a first visit plays the effect it was scheduled with."""
    c, loader = _controller(True)
    c._extend(2)
    scheduled = c.history[1].effect_id
    c.next()
    present(c, loader)
    assert c.entry.effect_id == scheduled
    c.close()


# ---------------------------------------------------------------- exit (SX)

def _wait(qapp, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def classifier(qapp, tmp_path, monkeypatch):
    import image_classifier.app as app_module
    import image_classifier.slideshow.player as player_module

    QStandardPaths.setTestModeEnabled(True)
    config = tmp_path / "viewer_config.json"
    config.write_text(json.dumps({"last_seen_version": app_module.__version__}))
    monkeypatch.setattr(app_module, "get_config_file", lambda: str(config))
    photos = tmp_path / "photos"
    photos.mkdir()
    for index in range(4):
        Image.new("RGB", (160, 120), (40 * index, 90, 140)).save(photos / f"p{index}.jpg")
    real_player = player_module.PlayerWindow
    monkeypatch.setattr(player_module, "PlayerWindow", lambda *a, **kw: real_player(*a, **kw, raster=True))
    monkeypatch.setattr(player_module.SettingsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    win = app_module.PhotoViewer()
    win.load_directory(str(photos), start_at_first=True)
    win.slideshow_settings = SlideshowSettings(30, 100, False, True, False)
    yield win
    player = getattr(win, "_slideshow_player", None)
    if player is not None:
        player.close()
    win._cancel_preloads()
    win.image_viewer._cancel_pending_loads()
    win._marked_save_timer.stop()
    win.close()


def test_sx1_closing_on_another_photo_selects_it_in_the_classifier(classifier, qapp):
    """SX-1: exit on photo X (not the starting one) -> the classifier shows X."""
    classifier.current_index = 1
    classifier.show_image()
    classifier.open_slideshow()
    player = classifier._slideshow_player
    assert _wait(qapp, lambda: player.surface.entry is not None)
    start = player.surface.entry.path
    player.controller.next()
    player.controller.next()
    assert _wait(qapp, lambda: player.surface.entry is not None and player.surface.entry.path != start
                 and player.surface.entry.path == player.controller.entry.path)
    watched = player.surface.entry.path
    player.close()
    assert _wait(qapp, lambda: classifier._slideshow_player is None)
    assert classifier.image_files[classifier.current_index] == watched
    assert classifier._current_path == watched


def test_sx2_closing_on_the_starting_photo_leaves_the_classifier_untouched(classifier, qapp):
    """SX-2: exit on the photo it started from -> selection, zoom and pan stay exactly as they were."""
    classifier.current_index = 2
    classifier.show_image()
    viewer = classifier.image_viewer
    assert _wait(qapp, lambda: viewer._shown_load_id == viewer.current_load_id)
    classifier.image_viewer.zoom_factor = 1.7
    classifier.image_viewer.setTransform(QTransform().scale(1.7, 1.7))
    classifier.open_slideshow()
    player = classifier._slideshow_player
    assert _wait(qapp, lambda: player.surface.entry is not None)
    player.close()
    assert _wait(qapp, lambda: classifier._slideshow_player is None)
    assert classifier.current_index == 2
    assert classifier.image_viewer.zoom_factor == 1.7
    assert classifier.image_viewer.transform().m11() == 1.7


def test_sx2_closing_before_any_photo_is_shown_leaves_the_classifier_untouched(classifier, qapp):
    """SX-2: closing before the first photo appears changes nothing."""
    classifier.current_index = 3
    classifier.open_slideshow()
    player = classifier._slideshow_player
    player.close()
    assert _wait(qapp, lambda: classifier._slideshow_player is None)
    assert classifier.current_index == 3

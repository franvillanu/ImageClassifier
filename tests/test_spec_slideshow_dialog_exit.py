"""Executable form of docs/specs/SPEC-002-slideshow-controls.md: exit handover (SX-3) and the
collapsible shortcut sheet (SD-1 .. SD-3)."""
import json
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog

from image_classifier.slideshow.settings import SlideshowSettings
from image_classifier.slideshow.settings_dialog import SettingsDialog

REQUIRES = ["SX-3", "SD-1", "SD-2", "SD-3"]


def _wait(qapp, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


# ---------------------------------------------------------------- SX-3

@pytest.fixture
def classifier(qapp, tmp_path, monkeypatch):
    import image_classifier.app as app_module
    import image_classifier.slideshow.player as player_module
    from image_classifier.imaging.loader import ImageLoaderRunnable

    QStandardPaths.setTestModeEnabled(True)
    ImageLoaderRunnable._full_cache.clear()
    ImageLoaderRunnable._preview_cache.clear()
    config = tmp_path / "viewer_config.json"
    config.write_text(json.dumps({"last_seen_version": app_module.__version__}))
    monkeypatch.setattr(app_module, "get_config_file", lambda: str(config))
    photos = tmp_path / "photos"
    photos.mkdir()
    for index in range(4):
        Image.new("RGB", (1600, 1200), (40 * index, 90, 140)).save(photos / f"p{index}.jpg")
    real_player = player_module.PlayerWindow
    monkeypatch.setattr(player_module, "PlayerWindow", lambda *a, **kw: real_player(*a, **kw, raster=True))
    monkeypatch.setattr(player_module.SettingsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    win = app_module.PhotoViewer()
    win.resize(900, 650)
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


def test_sx3_classifier_shows_the_photo_before_the_slideshow_window_goes(classifier, qapp):
    """SX-3: at the moment the player hides, the classifier already displays photo X (no old frame)."""
    from image_classifier.imaging.loader import ImageLoaderRunnable

    classifier.open_slideshow()
    player = classifier._slideshow_player
    assert _wait(qapp, lambda: player.surface.entry is not None)
    start = player.surface.entry.path
    player.controller.next()
    assert _wait(qapp, lambda: player.surface.entry is not None and player.surface.entry.path != start)
    watched = player.surface.entry.path
    # nothing about X may be in the classifier's caches: the handover must not depend on luck
    ImageLoaderRunnable._full_cache.clear()
    ImageLoaderRunnable._preview_cache.clear()
    seen_at_hide = {}

    painted = []
    from PyQt6.QtCore import QEvent, QObject

    class PaintWatch(QObject):
        def eventFilter(self, obj, event):
            if obj is classifier and event.type() == QEvent.Type.Paint and classifier._current_path == watched:
                painted.append(True)
            return False

    watch = PaintWatch()
    qapp.installEventFilter(watch)

    def on_hide():
        viewer = classifier.image_viewer
        seen_at_hide["path"] = classifier._current_path
        seen_at_hide["shown"] = viewer._shown_load_id == viewer.current_load_id and viewer.original_pixmap is not None
        seen_at_hide["painted_before_hide"] = bool(painted)  # rendered, not just loaded

    original_hide_event = player.hideEvent

    def hide_event(event):  # must return None: Qt rejects any other return value
        on_hide()
        original_hide_event(event)

    player.hideEvent = hide_event
    player.close()
    qapp.removeEventFilter(watch)
    assert seen_at_hide == {"path": watched, "shown": True, "painted_before_hide": True}


def test_sx3_handover_is_not_rotated(classifier, qapp):
    """SX-3: a photo turned with R in the slideshow arrives unrotated in the classifier (SR-2)."""
    classifier.open_slideshow()
    player = classifier._slideshow_player
    assert _wait(qapp, lambda: player.surface.entry is not None)
    start = player.surface.entry.path
    player.controller.next()
    assert _wait(qapp, lambda: player.surface.entry is not None and player.surface.entry.path != start)
    QTest.keyClick(player, Qt.Key.Key_R)
    player.close()
    assert _wait(qapp, lambda: classifier._slideshow_player is None)
    pixmap = classifier.image_viewer.original_pixmap
    assert pixmap.width() > pixmap.height()  # 4:3 landscape, not turned to portrait


# ---------------------------------------------------------------- SD

def _settle(qapp, dialog):
    assert _wait(qapp, lambda: dialog._shortcuts_anim.state() == dialog._shortcuts_anim.State.Stopped)


@pytest.fixture
def dialog(qapp):
    d = SettingsDialog(SlideshowSettings(), "en")
    d.show()
    qapp.processEvents()
    yield d
    d.close()


def test_sd1_shortcuts_collapsed_by_default_and_dialog_shorter(dialog, qapp):
    """SD-1: the sheet starts hidden behind a 'Keyboard shortcuts' row; expanding makes the dialog taller."""
    assert not dialog.shortcuts_card.isVisible()
    assert not dialog.shortcuts_toggle.isChecked()
    assert dialog.shortcuts_toggle.text() == "Keyboard shortcuts"
    collapsed = dialog.height()
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    assert dialog.shortcuts_card.isVisible()
    assert dialog.height() > collapsed + 80


def test_sd2_height_animates_and_settles_at_natural_size_and_back(dialog, qapp):
    """SD-2: intermediate heights during the animation, natural height when open, hidden when closed."""
    heights = []
    dialog._shortcuts_anim.valueChanged.connect(lambda value: heights.append(value))
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    natural = dialog.shortcuts_card.sizeHint().height()
    assert len(set(heights)) > 3 and heights[-1] == natural
    # limit released at the end (the offscreen test screen is only 800x600, so the real height can be capped)
    assert dialog.shortcuts_card.maximumHeight() == 16777215
    assert dialog._shortcuts_anim.duration() == 180
    assert dialog.shortcuts_toggle._angle == pytest.approx(90, abs=1)
    open_height = dialog.height()
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    assert not dialog.shortcuts_card.isVisible()
    assert dialog.height() < open_height
    assert _wait(qapp, lambda: abs(dialog.shortcuts_toggle._angle) < 1)


def test_sd3_toggle_is_keyboard_operable_and_named(dialog, qapp):
    """SD-3: focusable, Space toggles, accessible name set (EN and ES)."""
    toggle = dialog.shortcuts_toggle
    assert toggle.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert toggle.accessibleName() == "Keyboard shortcuts"
    toggle.setFocus()
    QTest.keyClick(toggle, Qt.Key.Key_Space)
    assert toggle.isChecked()
    spanish = SettingsDialog(SlideshowSettings(), "es")
    assert spanish.shortcuts_toggle.accessibleName() == "Atajos de teclado"
    spanish.close()

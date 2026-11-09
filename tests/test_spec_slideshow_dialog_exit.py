"""Executable form of docs/specs/SPEC-002-slideshow-controls.md: exit handover (SX-3) and the
shortcuts side panel (SD-1 .. SD-3, SD-5 .. SD-7)."""
import json
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QRect, QStandardPaths, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QLabel

from image_classifier.slideshow.settings import SlideshowSettings
from image_classifier.slideshow.settings_dialog import SettingsDialog

REQUIRES = ["SX-3", "SD-1", "SD-2", "SD-3", "SD-5", "SD-6", "SD-7"]


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


def test_sd1_shortcuts_hidden_by_default_and_dialog_compact(dialog, qapp):
    """SD-1: the panel starts hidden behind a 'Keyboard shortcuts' row; the dialog opens compact."""
    assert not dialog.shortcuts_card.isVisible()
    assert not dialog.shortcuts_toggle.isChecked()
    assert dialog.shortcuts_toggle.text() == "Keyboard shortcuts"
    assert dialog.width() < 700


def test_sd2_panel_opens_to_the_right_animated_without_changing_height(dialog, qapp):
    """SD-2: width animates, dialog grows sideways only, settles at natural width, chevron half turn, and back."""
    widths = []
    dialog._shortcuts_anim.valueChanged.connect(lambda value: widths.append(value))
    compact_width, compact_height = dialog.width(), dialog.height()
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    natural = dialog.shortcuts_card.sizeHint().width()
    assert len(set(widths)) > 3 and widths[-1] == natural
    assert dialog.shortcuts_card.maximumWidth() == 16777215  # limit released at the end
    assert dialog._shortcuts_anim.duration() == 180
    assert dialog.shortcuts_toggle._angle == pytest.approx(180, abs=1)
    assert dialog.shortcuts_card.isVisible()
    assert dialog.width() >= compact_width + natural - 2
    assert dialog.height() == compact_height
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    assert not dialog.shortcuts_card.isVisible()
    assert dialog.width() == compact_width and dialog.height() == compact_height
    assert _wait(qapp, lambda: abs(dialog.shortcuts_toggle._angle) < 1)


def test_sd5_one_column_grouped_in_english_and_spanish(dialog, qapp):
    """SD-5: every shortcut in one aligned column under two headings, action left and keycaps right."""
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)

    def rows(d):
        panel = d.shortcuts_card
        texts = panel.findChildren(QLabel, "keyText")
        chips = panel.findChildren(QLabel, "key")
        heads = [label.text() for label in panel.findChildren(QLabel, "group")]
        return texts, chips, heads

    texts, chips, heads = rows(dialog)
    assert heads == ["Viewer", "Photo"]
    colours = [label.styleSheet() for label in dialog.shortcuts_card.findChildren(QLabel, "group")]
    assert colours[0] != colours[1] and all("color: #" in c for c in colours)
    assert len(texts) == 11
    assert {label.text() for label in texts} >= {"Pause / resume", "Show controls", "Close", "Fullscreen"}
    assert len({label.mapTo(dialog, label.rect().topLeft()).x() for label in texts}) == 1
    # keycaps are right-aligned: the last chip of each row ends at the same x
    ends = {}
    for chip in chips:
        y = chip.mapTo(dialog, chip.rect().center()).y()
        near = [known for known in ends if abs(known - y) < 6]
        key = near[0] if near else y
        ends[key] = max(ends.get(key, 0), chip.mapTo(dialog, chip.rect().topRight()).x())
    assert len(ends) == 11 and max(ends.values()) - min(ends.values()) <= 1
    spanish = SettingsDialog(SlideshowSettings(), "es")
    spanish.show()
    spanish.shortcuts_toggle.click()
    assert _wait(qapp, lambda: spanish._shortcuts_anim.state() == spanish._shortcuts_anim.State.Stopped)
    s_texts, _chips, s_heads = rows(spanish)
    assert s_heads == ["Visor", "Foto"] and len(s_texts) == 11
    assert "Pausar / reanudar" in {label.text() for label in s_texts}
    spanish.close()


def test_sd6_stays_on_screen_and_returns_home(dialog, qapp):
    """SD-6: near the right edge the dialog shifts left just enough; closing puts it back."""
    area = QRect(0, 0, 1200, 800)
    dialog._available = lambda: area
    home_x = area.right() + 1 - dialog.frameGeometry().width() - 10
    dialog.move(home_x, 10)
    qapp.processEvents()
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    assert dialog.frameGeometry().right() <= area.right()
    assert dialog.frameGeometry().right() >= area.right() - 1  # shifted only as far as needed
    assert dialog.x() < home_x
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    assert dialog.x() == home_x


def test_sd6_settings_stay_put_when_there_is_room(qapp):
    """SD-6: with room on the right the settings column does not move."""
    d = SettingsDialog(SlideshowSettings(), "en")
    d._available = lambda: QRect(0, 0, 3000, 1500)
    d.show()
    d.move(100, 10)
    qapp.processEvents()
    d.shortcuts_toggle.click()
    assert _wait(qapp, lambda: d._shortcuts_anim.state() == d._shortcuts_anim.State.Stopped)
    assert d.x() == 100
    d.close()


def test_sd7_panel_close_button_and_escape(dialog, qapp):
    """SD-7: the panel's own close button closes it; Esc closes the dialog (EN/ES accessible name)."""
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    assert dialog.shortcuts_close.accessibleName() == "Close panel"
    dialog.shortcuts_close.click()
    _settle(qapp, dialog)
    assert not dialog.shortcuts_toggle.isChecked() and not dialog.shortcuts_card.isVisible()
    dialog.shortcuts_toggle.click()
    _settle(qapp, dialog)
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible() and dialog.result() == QDialog.DialogCode.Rejected
    spanish = SettingsDialog(SlideshowSettings(), "es")
    assert spanish.shortcuts_close.accessibleName() == "Cerrar panel"
    spanish.close()


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

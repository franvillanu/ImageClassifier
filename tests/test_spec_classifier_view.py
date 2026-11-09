"""Executable form of docs/specs/SPEC-003-classifier-view.md (CV-1)."""
import json
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtTest import QTest

REQUIRES = ["CV-1", "CV-2"]


def _wait(qapp, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    import image_classifier.app as app_module

    QStandardPaths.setTestModeEnabled(True)
    config = tmp_path / "viewer_config.json"
    config.write_text(json.dumps({"last_seen_version": app_module.__version__}))
    monkeypatch.setattr(app_module, "get_config_file", lambda: str(config))
    photos = tmp_path / "photos"
    photos.mkdir()
    Image.new("RGB", (1600, 1000), (90, 120, 150)).save(photos / "a.jpg")
    win = app_module.PhotoViewer()
    win.resize(900, 650)
    win.show()
    win.load_directory(str(photos), start_at_first=True)
    viewer = win.image_viewer
    assert _wait(qapp, lambda: viewer._shown_load_id == viewer.current_load_id and viewer.full_resolution_ready
                 and viewer.full_loader is None and not viewer._full_request_timer.isActive())
    yield win
    win.image_viewer._cancel_pending_loads()
    win._cancel_preloads()
    win._marked_save_timer.stop()
    win.close()


@pytest.mark.parametrize("key", [Qt.Key.Key_0, Qt.Key.Key_Backspace])
def test_cv1_zero_or_backspace_fits_the_photo_again(window, qapp, key):
    """CV-1: after zooming in and panning, 0 / Backspace restores the fitted, centred view."""
    viewer = window.image_viewer
    fit_scale = viewer.transform().m11()
    viewer._manual_zoom(zoom_in=True)
    viewer._manual_zoom(zoom_in=True)
    viewer.horizontalScrollBar().setValue(viewer.horizontalScrollBar().value() + 40)
    qapp.processEvents()
    assert viewer.transform().m11() > fit_scale * 1.1
    QTest.keyClick(window, key)
    qapp.processEvents()
    assert viewer.auto_fit
    assert viewer.transform().m11() == pytest.approx(fit_scale, rel=1e-3)
    rect = viewer.pixmap_item.sceneBoundingRect()
    centre = viewer.mapToScene(viewer.viewport().rect().center())
    assert abs(centre.x() - rect.center().x()) <= 2 and abs(centre.y() - rect.center().y()) <= 2


def test_cv1_help_lists_both_keys():
    """CV-1: Help shows Backspace and 0 for the fit action, EN and ES."""
    from image_classifier.i18n.translations import translations

    assert translations["en"]["shortcut_doubleclick_key"].startswith("Backspace / 0")
    assert translations["es"]["shortcut_doubleclick_key"].startswith("Retroceso / 0")


@pytest.mark.parametrize("key,mods,grows", [
    (Qt.Key.Key_Plus, Qt.KeyboardModifier.NoModifier, True),
    (Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier, True),
    (Qt.Key.Key_Plus, Qt.KeyboardModifier.KeypadModifier, True),
    (Qt.Key.Key_Minus, Qt.KeyboardModifier.NoModifier, False),
    (Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier, False),
    (Qt.Key.Key_Minus, Qt.KeyboardModifier.KeypadModifier, False),
])
def test_cv2_plus_minus_zoom_like_up_down(window, qapp, key, mods, grows):
    """CV-2: + zooms in and - zooms out in the classifier (also Ctrl and numpad)."""
    viewer = window.image_viewer
    viewer._manual_zoom(zoom_in=True)  # start zoomed so '-' has room to go out
    qapp.processEvents()
    before = viewer.transform().m11()
    QTest.keyClick(window, key, mods)
    qapp.processEvents()
    after = viewer.transform().m11()
    assert (after > before * 1.01) if grows else (after < before * 0.99)


def test_cv2_ctrl_zero_fits_and_arrows_still_zoom(window, qapp):
    """CV-2: Ctrl+0 fits like 0; Up still zooms in."""
    viewer = window.image_viewer
    fit = viewer.transform().m11()
    QTest.keyClick(window, Qt.Key.Key_Up)
    qapp.processEvents()
    assert viewer.transform().m11() > fit * 1.01
    QTest.keyClick(window, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
    qapp.processEvents()
    assert viewer.transform().m11() == pytest.approx(fit, rel=1e-3)

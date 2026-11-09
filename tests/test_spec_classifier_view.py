"""Executable form of docs/specs/SPEC-003-classifier-view.md (CV-1)."""
import json
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtTest import QTest

REQUIRES = ["CV-1"]


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

    assert translations["en"]["shortcut_doubleclick_key"] == "Backspace / 0"
    assert translations["es"]["shortcut_doubleclick_key"] == "Retroceso / 0"

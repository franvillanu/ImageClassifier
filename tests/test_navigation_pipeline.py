"""Behavioural tests for the image navigation pipeline (preview -> full resolution)."""
import os
import sys
import time
import types

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

if sys.platform != "win32":
    # shell_win binds Windows APIs at import time; nothing here uses it.
    _stub = types.ModuleType("image_classifier.shell_win")
    _stub.open_folder_and_select_item = lambda *args, **kwargs: None
    sys.modules.setdefault("image_classifier.shell_win", _stub)

from image_classifier.imaging.loader import (  # noqa: E402
    ImageLoaderRunnable,
    _read_with_pillow,
    preview_dimension_for,
    to_display_format,
)

FULL_SIZE = (3000, 2000)


def _wait_until(condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    app = QApplication.instance()
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


def _make_photos(directory, count, size=FULL_SIZE):
    paths = []
    for index in range(count):
        image = Image.new("RGB", size, (40 + index * 10, 90, 160))
        path = directory / f"photo_{index:02d}.jpg"
        image.save(path, quality=85)
        paths.append(path)
    return paths


@pytest.fixture
def viewer_window(qapp, tmp_path):
    # Keep config and the preview disk cache out of the user's real profile.
    QStandardPaths.setTestModeEnabled(True)
    ImageLoaderRunnable._full_cache.clear()
    ImageLoaderRunnable._preview_cache.clear()
    from image_classifier.app import PhotoViewer

    window = PhotoViewer()
    window.setWindowState(window.windowState() & ~window.windowState().__class__.WindowMaximized)
    window.resize(800, 600)
    qapp.processEvents()
    yield window
    window.image_viewer._cancel_pending_loads()
    window._cancel_preloads()
    ImageLoaderRunnable.thread_pool().waitForDone(10000)
    window._marked_save_timer.stop()
    window.hide()
    window.deleteLater()
    qapp.processEvents()
    ImageLoaderRunnable._full_cache.clear()
    ImageLoaderRunnable._preview_cache.clear()
    QStandardPaths.setTestModeEnabled(False)


def _open(window, directory):
    window.load_directory(str(directory), start_at_first=True)
    viewer = window.image_viewer
    assert _wait_until(lambda: viewer._shown_load_id == viewer.current_load_id)
    return viewer


def test_preview_dimension_matches_physical_viewport():
    assert preview_dimension_for(1920, 1080, 1.0) == 1920
    assert preview_dimension_for(2560, 1440, 1.5) == 3840
    assert preview_dimension_for(1900, 1000, 1.0) == 1920  # rounded up to the 128 px step
    assert preview_dimension_for(800, 600, 1.0) == 1024  # floor
    assert preview_dimension_for(5000, 3000, 2.0) == 4096  # ceiling


def test_display_format_is_native_for_qpixmap(qapp, tmp_path):
    gray = QImage(8, 8, QImage.Format.Format_Grayscale8)
    gray.fill(128)
    assert to_display_format(gray).format() == QImage.Format.Format_RGB32

    rgba = QImage(8, 8, QImage.Format.Format_RGBA8888)
    rgba.fill(0x80FF0000)
    assert to_display_format(rgba).format() == QImage.Format.Format_ARGB32_Premultiplied

    opaque = tmp_path / "opaque.png"
    Image.new("RGB", (8, 6), (1, 2, 3)).save(opaque)
    loaded = _read_with_pillow(str(opaque))
    assert loaded.format() == QImage.Format.Format_RGB32
    assert loaded.pixelColor(0, 0).getRgb()[:3] == (1, 2, 3)

    transparent = tmp_path / "transparent.png"
    Image.new("RGBA", (8, 6), (10, 20, 30, 0)).save(transparent)
    loaded = _read_with_pillow(str(transparent))
    assert loaded.format() == QImage.Format.Format_ARGB32_Premultiplied
    assert loaded.pixelColor(0, 0).alpha() == 0


def test_full_resolution_attaches_without_rerender(viewer_window, tmp_path):
    _make_photos(tmp_path, 3)
    viewer = _open(viewer_window, tmp_path)

    preview_dimension = viewer.preview_dimension()
    assert max(viewer.original_pixmap.width(), viewer.original_pixmap.height()) == preview_dimension
    assert not viewer.full_resolution_ready
    displayed_key = viewer.pixmap_item.pixmap().cacheKey()

    assert _wait_until(lambda: viewer.full_resolution_ready)
    assert (viewer.original_pixmap.width(), viewer.original_pixmap.height()) == FULL_SIZE
    # The on-screen frame was kept: no second render, no visible swap.
    assert viewer.pixmap_item.pixmap().cacheKey() == displayed_key
    # Saving/editing sees the real pixels.
    assert viewer.renderFullResolution().width() == FULL_SIZE[0]


def test_zoom_before_full_resolution_keeps_view_stable(viewer_window, tmp_path):
    _make_photos(tmp_path, 2)
    viewer = _open(viewer_window, tmp_path)
    assert not viewer.full_resolution_ready

    for _ in range(6):
        viewer.zoom_in()  # keyboard zoom: also requests full resolution immediately
    on_screen_scale = viewer.transform().m11() * viewer.pixmap_item.pixmap().width()
    centre_fraction = (
        viewer.mapToScene(viewer.viewport().rect().center()).x()
        / viewer.pixmap_item.pixmap().width()
    )

    assert _wait_until(lambda: viewer.full_resolution_ready)
    assert viewer.pixmap_item.pixmap().width() == FULL_SIZE[0]
    after_scale = viewer.transform().m11() * viewer.pixmap_item.pixmap().width()
    after_fraction = (
        viewer.mapToScene(viewer.viewport().rect().center()).x()
        / viewer.pixmap_item.pixmap().width()
    )
    assert after_scale == pytest.approx(on_screen_scale, rel=0.01)
    assert after_fraction == pytest.approx(centre_fraction, abs=0.01)


def test_undo_of_preview_snapshot_restores_full_resolution(viewer_window, tmp_path):
    _make_photos(tmp_path, 2)
    viewer = _open(viewer_window, tmp_path)
    assert not viewer.full_resolution_ready

    viewer_window.rotate_action()  # snapshot taken while only the preview exists
    assert _wait_until(lambda: viewer.full_resolution_ready)

    viewer_window.undo_action()
    assert viewer.full_resolution_ready
    assert (viewer.original_pixmap.width(), viewer.original_pixmap.height()) == FULL_SIZE


def test_undo_before_full_resolution_blocks_saving_until_loaded(viewer_window, tmp_path):
    _make_photos(tmp_path, 2)
    viewer = _open(viewer_window, tmp_path)
    viewer_window.rotate_action()
    viewer._cancel_pending_loads()
    ImageLoaderRunnable._full_cache.clear()

    viewer_window.undo_action()
    # Preview pixels must never be treated as the saveable original.
    if viewer.original_pixmap.width() != FULL_SIZE[0]:
        assert not viewer.full_resolution_ready
    assert _wait_until(lambda: viewer.full_resolution_ready)
    assert viewer.original_pixmap.width() == FULL_SIZE[0]


def test_small_image_is_full_resolution_on_first_frame(viewer_window, tmp_path):
    _make_photos(tmp_path, 2, size=(600, 400))
    viewer = _open(viewer_window, tmp_path)
    assert viewer.full_resolution_ready
    assert viewer.original_pixmap.width() == 600


def test_saved_brightness_survives_cached_navigation(viewer_window, tmp_path, monkeypatch):
    paths = _make_photos(tmp_path, 3)
    viewer = _open(viewer_window, tmp_path)
    # The GPU path needs a real OpenGL context, which the offscreen test platform lacks.
    monkeypatch.setattr(viewer, "applyBrightnessGPU", viewer.applyBrightness)
    second = viewer_window.image_files[1]
    assert _wait_until(
        lambda: ImageLoaderRunnable.get_cached_preview(second, viewer.preview_dimension())
        is not None
    )
    viewer_window.image_brightness[second] = 1.4

    viewer_window.show_next_image()
    assert viewer.brightness_factor == pytest.approx(1.4)
    assert _wait_until(lambda: viewer.full_resolution_ready)
    assert viewer.brightness_factor == pytest.approx(1.4)
    assert len(paths) == 3


def test_preloads_follow_direction_and_cancel_stale_work(viewer_window, tmp_path):
    _make_photos(tmp_path, 10)
    _open(viewer_window, tmp_path)
    files = viewer_window.image_files
    ImageLoaderRunnable.thread_pool().waitForDone(10000)
    ImageLoaderRunnable._preview_cache.clear()
    ImageLoaderRunnable._full_cache.clear()

    viewer_window.current_index = 5
    viewer_window._nav_direction = 1
    viewer_window._schedule_preloads()
    assert set(viewer_window._preload_inflight) == {files[6], files[4], files[7]}
    forward_two = viewer_window._preload_inflight[files[7]][1]

    viewer_window.current_index = 3
    viewer_window._nav_direction = -1
    viewer_window._schedule_preloads()
    assert set(viewer_window._preload_inflight) <= {files[2], files[4], files[1]}
    assert forward_two.cancelled

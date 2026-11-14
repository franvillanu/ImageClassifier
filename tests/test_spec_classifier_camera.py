"""Camera transitions in SPEC-003, including progressive-loading invariants."""
import pytest
from PIL import Image
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QWidget

from image_classifier.imaging.loader import ImageFrame, ImageLoaderRunnable
from image_classifier.ui.image_viewer import AdvancedGraphicsImageViewer
from tests.test_spec_classifier_view import window  # noqa: F401 (shared app fixture)

REQUIRES = ["CV-5", "CV-6", "CV-7", "CV-8", "CV-9"]


@pytest.fixture
def view(qapp):
    v = AdvancedGraphicsImageViewer()
    v.setViewport(QWidget())  # Geometry tests need no OpenGL context.
    v.resize(900, 650)
    v.show()
    qapp.processEvents()
    pix = QPixmap(3200, 2000)
    pix.fill(Qt.GlobalColor.gray)
    v.onImageLoaded(pix, True, False, v.current_load_id)
    yield v
    v._cancel_pending_loads()
    v.close()


def _wheel(v):
    pos = QPointF(v.viewport().rect().center())
    event = QWheelEvent(pos, pos, QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    v.wheelEvent(event)


def _centre(v):
    p = v.mapToScene(v.viewport().rect().center())
    return p.x(), p.y()


@pytest.mark.parametrize("input_method", ["keyboard", "wheel"])
def test_cv5_manual_camera_survives_resize_and_adjustments(view, qapp, input_method):
    """CV-5: both inputs leave fit; resize/brightness/rotation retain manual scale."""
    for _ in range(12):
        view.zoom_in() if input_method == "keyboard" else _wheel(view)
    assert not view.auto_fit
    view.centerOn(1300, 850)
    scale = view.transform().m11()
    centre = _centre(view)
    view.resize(940, 680)
    qapp.processEvents()
    assert view.transform().m11() == pytest.approx(scale)
    assert _centre(view) == pytest.approx(centre, abs=3)
    view.setBrightness(0.9)
    view._brightness_timer.stop()
    view._apply_pending_brightness()
    assert view.transform().m11() == pytest.approx(scale)
    assert _centre(view) == pytest.approx(centre, abs=3)
    view.rotate_clockwise()
    assert view.transform().m11() == pytest.approx(scale)
    assert _centre(view) == pytest.approx((2000 - centre[1], centre[0]), abs=4)
    view.mouseDoubleClickEvent(None)
    assert view.auto_fit
    view.resize(980, 710)
    qapp.processEvents()
    assert view.transform().m11() == pytest.approx(view.fit_zoom_factor)


@pytest.mark.parametrize("orientation", [1, 6, 8])
def test_cv6_loader_retains_source_geometry_in_memory_and_disk(qapp, tmp_path, monkeypatch, orientation):
    """CV-6: reduced frames retain EXIF-oriented source dimensions, including disk hits."""
    path = tmp_path / "oriented.jpg"
    photo = Image.new("RGB", (2400, 1600), "blue")
    exif = Image.Exif()
    exif[274] = orientation
    photo.save(path, exif=exif)
    monkeypatch.setattr(ImageLoaderRunnable, "_disk_cache_dir", classmethod(lambda cls: str(tmp_path)))
    monkeypatch.setattr(ImageLoaderRunnable, "_disk_cache_enabled", True)
    expected = (2400, 1600) if orientation == 1 else (1600, 2400)
    for disk_hit in (False, True):
        ImageLoaderRunnable.drop_cached_pixmap(str(path))
        worker = ImageLoaderRunnable(str(path), 600, progressive=True, load_full=False)
        if disk_hit:
            monkeypatch.setattr(worker, "_read_qt_preview", lambda: pytest.fail("disk hit decoded source"))
        frames = []
        worker.signals.previewReady.connect(frames.append)
        worker.run()
        assert len(frames) == 1
        assert frames[0].source_size == expected
        assert max(frames[0].image.width(), frames[0].image.height()) <= 600


def test_cv6_cv8_preview_navigation_and_upgrade_share_source_coordinates(view, monkeypatch, tmp_path):
    """CV-6 CV-8: navigate before full decode, reject stale frames, keep preview speed."""
    full = QImage(3200, 2000, QImage.Format.Format_RGB32)
    full.fill(Qt.GlobalColor.gray)
    paths = [str(tmp_path / name) for name in ("a.jpg", "b.jpg")]
    for path in paths:
        assert ImageLoaderRunnable.seed_preview(path, view.preview_dimension(), full)
    monkeypatch.setattr(ImageLoaderRunnable, "get_cached_image", classmethod(lambda cls, path: None))
    jobs = []
    monkeypatch.setattr(ImageLoaderRunnable, "start", lambda worker, *args: jobs.append(worker))
    for _ in range(8):
        view.zoom_in()
    view.centerOn(1400, 900)
    scale, centre = view.transform().m11(), _centre(view)
    for path in paths * 3:
        old_id = view.current_load_id
        view.setImage(path, reset_zoom=False)
        assert view._shown_load_id == view.current_load_id  # Preview is shown synchronously.
        assert not jobs  # No full decode before dwell.
        assert view.pixmap_item.sceneBoundingRect().width() == pytest.approx(3200)
        assert view.transform().m11() == pytest.approx(scale)
        assert _centre(view) == pytest.approx(centre, abs=2)
        view._attach_full_resolution(QPixmap(80, 60), old_id)
        assert not view.full_resolution_ready
        view._attach_full_resolution(QPixmap.fromImage(full), view.current_load_id)
        assert view.transform().m11() == pytest.approx(scale)
        assert _centre(view) == pytest.approx(centre, abs=2)


def test_cv8_fit_upgrade_and_camera_actions_do_not_rebake(view, qapp, monkeypatch):
    """CV-8: fit upgrade keeps its display; zoom/pan/manual resize only change camera."""
    full = QPixmap(3200, 2000)
    full.fill(Qt.GlobalColor.gray)
    before = view.pixmap_item.pixmap().cacheKey()
    calls = []
    original = view._pixmapWithRotationAndBrightness
    monkeypatch.setattr(view, "_pixmapWithRotationAndBrightness", lambda: (calls.append(True), original())[1])
    view._attach_full_resolution(full, view.current_load_id)
    assert view.pixmap_item.pixmap().cacheKey() == before
    assert not calls
    view.zoom_in()
    assert len(calls) == 1  # One transition from the fit display to decoded full detail.
    detail = view.pixmap_item.pixmap().cacheKey()
    view.zoom_in()
    view.horizontalScrollBar().setValue(view.horizontalScrollBar().value() + 5)
    view.resize(920, 660)
    qapp.processEvents()
    assert view.pixmap_item.pixmap().cacheKey() == detail
    assert len(calls) == 1


def test_cv7_sharpen_undo_redo_preserve_camera_and_crop_fits(window, qapp):
    """CV-7: pixel replacements preserve camera except an explicit crop-to-fit."""
    v = window.image_viewer
    for _ in range(12):
        v.zoom_in()
    v.centerOn(700, 450)
    scale, centre = v.transform().m11(), _centre(v)
    window.push_undo_state()
    window.applySharpenResult(v.original_pixmap.copy())
    assert not v.auto_fit
    assert v.transform().m11() == pytest.approx(scale)
    assert _centre(v) == pytest.approx(centre, abs=2)
    window.undo_action()
    window.redo_action()
    assert v.transform().m11() == pytest.approx(scale)
    assert _centre(v) == pytest.approx(centre, abs=2)
    late_id = v.current_load_id
    crop = QPixmap(500, 400)
    crop.fill(Qt.GlobalColor.blue)
    window.applyCropResult(crop)
    assert v.auto_fit
    assert v.original_pixmap.size() == crop.size()
    v._attach_full_resolution(QPixmap(1600, 1000), late_id)
    assert v.original_pixmap.size() == crop.size()


def test_cv5_delayed_dock_layout_cannot_reset_manual_camera(window):
    """CV-5: a queued startup layout must not override zoom already chosen by the user."""
    v = window.image_viewer
    v.zoom_in()
    before = v.transform().m11()
    window.restore_dock_menu()
    assert not v.auto_fit
    assert v.transform().m11() == pytest.approx(before)


def test_cv7_rotation_undo_redo_keeps_the_same_source_detail(window, monkeypatch):
    """CV-7: undo/redo rotate the camera with the pixels and render only once."""
    v = window.image_viewer
    for _ in range(10):
        v.zoom_in()
    v.centerOn(650, 400)
    scale, before = v.transform().m11(), _centre(v)
    window.rotate_action()
    rotated = _centre(v)
    renders = []
    original = v._pixmapWithRotationAndBrightness
    monkeypatch.setattr(v, "_pixmapWithRotationAndBrightness", lambda: (renders.append(True), original())[1])
    window.undo_action()
    assert _centre(v) == pytest.approx(before, abs=3)
    assert len(renders) == 1
    window.redo_action()
    assert _centre(v) == pytest.approx(rotated, abs=3)
    assert v.transform().m11() == pytest.approx(scale)
    assert len(renders) == 2


def test_cv8_full_cache_does_not_delay_navigation_with_a_full_texture(view, tmp_path):
    """CV-8: cached full pixels are available for edits, but detail waits for dwell/zoom."""
    full = QImage(3200, 2000, QImage.Format.Format_RGB32)
    full.fill(Qt.GlobalColor.gray)
    path = str(tmp_path / "cached.jpg")
    ImageLoaderRunnable._full_cache.put(ImageLoaderRunnable._memory_source_key(path), full)
    ImageLoaderRunnable.seed_preview(path, view.preview_dimension(), full)
    view.zoom_in()
    scale = view.zoom_factor
    view.setImage(path, reset_zoom=False)
    assert view.full_resolution_ready
    assert view.original_pixmap.width() == 3200
    assert view.pixmap_item.pixmap().width() < 3200
    assert view._full_request_timer.isActive()
    assert view.zoom_factor == pytest.approx(scale)
    view.request_full_resolution()  # The same entry point as dwell/explicit zoom.
    assert view.pixmap_item.pixmap().width() == 3200
    assert view.zoom_factor == pytest.approx(scale)


def test_cv6_navigation_cancels_previous_photos_brightness(view, qapp, tmp_path):
    """CV-6: a queued brightness update must not leak onto the next photo."""
    from PyQt6.QtTest import QTest
    path = str(tmp_path / "brightness.jpg")
    full = QImage(3200, 2000, QImage.Format.Format_RGB32)
    full.fill(Qt.GlobalColor.gray)
    ImageLoaderRunnable.seed_preview(path, view.preview_dimension(), full)
    view.setBrightness(0.7)
    view.setImage(path, reset_zoom=False)
    QTest.qWait(30)
    assert view.brightness_factor == 1.0


def test_cv5_fit_mode_stays_centred_when_panning_is_attempted(view):
    """CV-5: scene margins used for camera precision do not make fitted photos draggable."""
    before = _centre(view)
    view.horizontalScrollBar().setValue(view.horizontalScrollBar().maximum())
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
    assert view.auto_fit
    assert _centre(view) == pytest.approx(before, abs=2)


def test_cv6_clear_invalidates_late_frames_and_source(view):
    """CV-6: clearing the playlist cannot resurrect the previous photo on a late frame."""
    view.zoom_in()
    old_id = view.current_load_id
    view.clear()
    view._attach_full_resolution(QPixmap(3200, 2000), old_id)
    assert view.original_pixmap is None
    assert view.pixmap_item.pixmap().isNull()
    assert not view.full_resolution_ready
    assert not view._full_request_timer.isActive()


def _shown_longest(v):
    pix = v.pixmap_item.pixmap()
    return max(pix.width(), pix.height())


def test_cv9_full_upgrade_after_window_grew_rerenders_fit_frame(view, qapp):
    """CV-9: startup shows a preview sized for the small window, the window then grows, and the
    full frame arrives: the fit display must be rebuilt, not left as the stretched preview."""
    preview = QPixmap(1024, 640)
    preview.fill(Qt.GlobalColor.gray)
    view.onImageLoaded(preview, True, False, view.current_load_id,
                       full_resolution=False, source_size=(3200, 2000))
    assert view.auto_fit and _shown_longest(view) == 1024
    view.resize(1800, 1100)  # saved window geometry applied after the first image
    qapp.processEvents()
    needed = view.preview_dimension()
    assert needed > 1100
    full = QPixmap(3200, 2000)
    full.fill(Qt.GlobalColor.gray)
    view._attach_full_resolution(full, view.current_load_id)
    assert _shown_longest(view) >= needed - 2
    assert view.auto_fit  # still fitted: no zoom involved


def test_cv9_resize_before_full_frame_does_not_leave_blur_on_screen(view, qapp):
    """CV-9: also when the full frame is decoded in the background after the resize."""
    preview = QPixmap(1024, 640)
    preview.fill(Qt.GlobalColor.gray)
    view.onImageLoaded(preview, True, False, view.current_load_id,
                       full_resolution=False, source_size=(3200, 2000))
    view.resize(1800, 1100)
    qapp.processEvents()
    full = QPixmap(3200, 2000)
    full.fill(Qt.GlobalColor.gray)
    view._on_full_frame(ImageFrame("x.jpg", full.toImage(), True), view.current_load_id)
    assert _shown_longest(view) >= view.preview_dimension() - 2

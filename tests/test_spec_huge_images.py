"""Executable form of docs/specs/SPEC-007-huge-images.md.

The real files are ~896 MP; the tests lower the "huge" threshold (``huge.HUGE_PIXELS``) so a 1.6 MP
photo takes the same code path.
"""
import json
import time

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QDialog

from image_classifier.imaging import huge
from image_classifier.imaging.loader import ImageLoaderRunnable
from image_classifier.workers.huge_worker import HugeRotateWorker

REQUIRES = ["HI-1", "HI-2", "HI-3", "HI-4", "HI-5", "HI-6", "HI-7", "HI-8"]


def _wait(qapp, cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


def _corner_jpeg(path, size=(300, 200), exif_orientation=None):
    """White photo with a red top-left and a blue bottom-left block (survive JPEG well)."""
    arr = np.full((size[1], size[0], 3), 255, np.uint8)
    arr[:40, :40] = (255, 0, 0)
    arr[-40:, :40] = (0, 0, 255)
    img = Image.fromarray(arr)
    kwargs = {"quality": 95}
    if exif_orientation:
        exif = Image.Exif()
        exif[huge.EXIF_ORIENTATION] = exif_orientation
        kwargs["exif"] = exif.tobytes()
    img.save(path, **kwargs)


def _is(pixel, colour, tol=40):
    return all(abs(a - b) <= tol for a, b in zip(pixel, colour))


# ------------------------------------------------------------------ HI-1
def test_hi1_huge_means_more_than_100_megapixels():
    """HI-1: the threshold is 100 MP; 32000 x 28000 is huge, 10000 x 10000 is not (and not exactly 100 MP)."""
    assert huge.HUGE_PIXELS == 100_000_000
    assert huge.is_huge(32000, 28000)
    assert huge.is_huge(10001, 10000)
    assert not huge.is_huge(10000, 10000)
    assert not huge.is_huge(6000, 4000)


# ------------------------------------------------------------------ HI-2
def test_hi2_decompression_bomb_reaches_the_viewer_as_an_error(tmp_path, monkeypatch, qapp):
    """HI-2: Pillow's DecompressionBombError used to escape the worker: no result, ever."""
    from image_classifier.imaging import loader

    path = tmp_path / "a.jpg"
    Image.new("RGB", (100, 100), "gray").save(path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)  # 100 x 100 > 2 x 10 -> DecompressionBombError
    monkeypatch.setattr(ImageLoaderRunnable, "_read_full", lambda self: loader._read_with_pillow(self.image_path))
    errors, frames = [], []
    worker = ImageLoaderRunnable(str(path), progressive=False)
    worker.signals.error.connect(errors.append)
    worker.signals.finished.connect(frames.append)
    worker.run()
    assert not frames
    assert len(errors) == 1


def test_hi2_any_failure_in_the_progressive_path_is_reported(tmp_path, monkeypatch):
    """HI-2: also for the screen-sized decode (an exception type the loader does not list)."""
    path = tmp_path / "a.jpg"
    Image.new("RGB", (100, 100), "gray").save(path)

    def boom(self):
        raise Image.DecompressionBombError("too big")

    monkeypatch.setattr(ImageLoaderRunnable, "_read_qt_preview", boom)
    ImageLoaderRunnable.drop_cached_pixmap(str(path))
    errors = []
    worker = ImageLoaderRunnable(str(path), progressive=True, load_full=False)
    worker.signals.error.connect(errors.append)
    worker.run()
    assert len(errors) == 1


# ------------------------------------------------------------------ viewer fixtures
@pytest.fixture
def huge_window(qapp, tmp_path, monkeypatch):
    import image_classifier.app as app_module

    QStandardPaths.setTestModeEnabled(True)
    config = tmp_path / "viewer_config.json"
    config.write_text(json.dumps({"last_seen_version": app_module.__version__}))
    monkeypatch.setattr(app_module, "get_config_file", lambda: str(config))
    monkeypatch.setattr(huge, "HUGE_PIXELS", 1_000_000)   # the 1.6 MP test photo counts as huge
    monkeypatch.setattr(huge, "DETAIL_DIMENSION", 1200)
    photos = tmp_path / "photos"
    photos.mkdir()
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 255, (1000, 1600, 3), dtype=np.uint8)  # noisy: the file is big enough to read in steps
    Image.fromarray(noise).save(photos / "map.jpg", quality=90)
    win = app_module.PhotoViewer()
    win.resize(900, 650)
    win.show()
    win.load_directory(str(photos), start_at_first=True)
    viewer = win.image_viewer
    assert _wait(qapp, lambda: viewer._shown_load_id == viewer.current_load_id)
    win.photos = photos
    yield win
    viewer._cancel_pending_loads()
    win._cancel_preloads()
    win._marked_save_timer.stop()
    win.close()


# ------------------------------------------------------------------ HI-3 / HI-4 / HI-5
def test_hi3_hi4_hi5_detail_frame_instead_of_full_decode(huge_window, qapp):
    """HI-3/HI-4/HI-5: no full decode; a reduced frame replaces the pixels, the camera stays, progress is reported."""
    viewer = huge_window.image_viewer
    events = []
    viewer.detailStatus.connect(lambda state, pct: events.append((state, pct)))
    assert viewer.is_huge
    viewer._full_request_timer.stop()
    viewer._zoom_camera(1.5)                       # manual camera: the swap must not move it
    camera = viewer._camera
    shown_before = viewer.original_pixmap.width()

    viewer.request_full_resolution()
    assert viewer.full_loader is None              # HI-3: never a full decode
    assert viewer.detail_loader is not None
    assert not viewer.full_resolution_ready

    assert _wait(qapp, lambda: viewer._detail_ready)
    assert not viewer.full_resolution_ready        # still true: the pixels are not all in memory
    assert viewer.source_size == (1600, 1000)      # HI-4: true source size kept
    assert viewer.original_pixmap.width() == 1200 != shown_before
    assert viewer._camera.scale == pytest.approx(camera.scale)
    assert viewer._camera.centre == pytest.approx(camera.centre, abs=0.5)

    states = [s for s, _ in events]
    assert states[0] == "loading" and states[-1] == "ready"            # HI-5
    percents = [p for s, p in events if s == "loading"]
    assert percents == sorted(percents) and percents[0] == 0 and len(set(percents)) >= 3


def test_hi5_progress_is_the_real_fraction_of_the_file_read(tmp_path):
    """HI-5: decode_reduced reports bytes consumed / file size: monotonic, ends at 100 %."""
    path = tmp_path / "n.jpg"
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(0, 255, (1500, 2000, 3), dtype=np.uint8)).save(path, quality=90)
    seen = []
    img, source = huge.decode_reduced(str(path), 500, progress=seen.append)
    assert source == (2000, 1500) and max(img.size) == 500
    assert seen == sorted(seen) and seen[-1] == 1.0 and len(set(seen)) >= 5


def test_hi5_status_text_names_what_is_loaded_and_how_far():
    """HI-5: the line shows size, megapixels and percentage, in both languages."""
    en = huge.status_text("loading", 42, (32000, 28000), 0, "en")
    es = huge.status_text("loading", 42, (32000, 28000), 0, "es")
    for text in (en, es):
        assert "32000" in text and "28000" in text and "896 MP" in text and "42 %" in text
    assert en != es
    assert "8192" in huge.status_text("ready", 100, (32000, 28000), 8192, "en")
    assert "boom" in huge.status_text("failed", 0, (32000, 28000), 0, "en", error="boom")


# ------------------------------------------------------------------ HI-6
@pytest.mark.parametrize("turns,red_corner,blue_corner", [
    (1, "top-right", "top-left"),        # clockwise: old top-left -> top-right, old bottom-left -> top-left
    (2, "bottom-right", "top-right"),
    (3, "bottom-left", "bottom-right"),
])
def test_hi6_rotate_file_turns_clockwise(tmp_path, turns, red_corner, blue_corner):
    """HI-6: quarter turns clockwise (R key direction), size swapped for odd turns."""
    src, dst = tmp_path / "s.jpg", tmp_path / "d.jpg"
    _corner_jpeg(src)                       # 300 x 200, red top-left, blue bottom-left
    huge.rotate_file(str(src), str(dst), turns, progress=lambda *_: None)
    with Image.open(dst) as out:
        w, h = out.size
        assert (w, h) == ((200, 300) if turns % 2 else (300, 200))
        spot = {"top-left": (10, 10), "top-right": (w - 10, 10),
                "bottom-left": (10, h - 10), "bottom-right": (w - 10, h - 10)}
        assert _is(out.getpixel(spot[red_corner]), (255, 0, 0))
        assert _is(out.getpixel(spot[blue_corner]), (0, 0, 255))


def test_hi6_exif_orientation_is_baked_in_and_reset(tmp_path):
    """HI-6: a photo stored sideways (EXIF 6) is written upright, with the orientation tag reset."""
    src, dst = tmp_path / "s.jpg", tmp_path / "d.jpg"
    _corner_jpeg(src, exif_orientation=6)
    huge.rotate_file(str(src), str(dst), 0, progress=lambda *_: None)
    with Image.open(dst) as out:
        assert out.size == (200, 300)
        assert out.getexif().get(huge.EXIF_ORIENTATION) == 1


def test_hi6_stages_are_reported_in_order(tmp_path):
    """HI-6: real percentage while reading, then rotate and write without an invented percentage."""
    src = tmp_path / "s.jpg"
    _corner_jpeg(src, (1200, 800))
    stages = []
    huge.rotate_file(str(src), str(src), 1, progress=lambda stage, f: stages.append((stage, f)))
    names = [s for s, _ in stages]
    assert names[0] == "read" and names[-2:] == ["rotate", "write"]
    reads = [f for s, f in stages if s == "read"]
    assert reads == sorted(reads) and reads[-1] == 1.0
    assert all(f is None for s, f in stages if s != "read")
    with Image.open(src) as out:
        assert out.size == (800, 1200)               # overwrite in place


def test_hi6_cancel_leaves_the_original_untouched(tmp_path):
    """HI-6: cancelling raises Cancelled and the source file is byte-identical."""
    src = tmp_path / "s.jpg"
    _corner_jpeg(src, (1200, 800))
    before = src.read_bytes()
    calls = {"n": 0}

    def cancelled():
        calls["n"] += 1
        return calls["n"] > 2

    with pytest.raises(huge.Cancelled):
        huge.rotate_file(str(src), str(src), 1, progress=lambda *_: None, cancelled=cancelled)
    assert src.read_bytes() == before
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".edit-")]


def test_hi6_worker_reports_failure_instead_of_ending_silently(tmp_path):
    """HI-2/HI-6: a missing file gives `failed`, never a silent end."""
    worker = HugeRotateWorker(str(tmp_path / "nope.jpg"), str(tmp_path / "out.jpg"), 1)
    failed, saved = [], []
    worker.failed.connect(failed.append)
    worker.saved.connect(saved.append)
    worker.run()
    assert len(failed) == 1 and not saved


def test_hi6_saving_a_rotated_huge_image_in_the_app(huge_window, qapp, monkeypatch):
    """HI-6: R then save-a-copy runs the worker with a progress dialog; the original is untouched."""
    win = huge_window
    viewer = win.image_viewer
    original = win.photos / "map.jpg"
    before = original.read_bytes()
    win.rotate_action()
    assert viewer.rotation_angle == 90
    win.saveModifiedImage(overwrite=False)
    assert win._huge_worker is not None
    dialog = win._huge_progress
    assert dialog is not None and dialog.isVisible()
    win._on_huge_progress("read", 40)
    assert (dialog.progressBar.minimum(), dialog.progressBar.maximum()) == (0, 100)
    assert dialog.progressBar.value() == 40 and "40 %" in dialog.messageLabel.text()
    win._on_huge_progress("write", -1)
    assert (dialog.progressBar.minimum(), dialog.progressBar.maximum()) == (0, 0)   # no invented percentage
    assert not dialog.cancelButton.isEnabled()
    assert _wait(qapp, lambda: win._huge_worker is None)
    copy = win.photos / "map_copy.jpg"
    assert copy.exists() and Image.open(copy).size == (1000, 1600)
    assert original.read_bytes() == before
    assert win._huge_progress is None


def test_hi6_overwrite_asks_first_and_replaces_the_file(huge_window, qapp, monkeypatch):
    """HI-6: overwrite keeps the usual confirmation; declining changes nothing."""
    win = huge_window
    original = win.photos / "map.jpg"
    before = original.read_bytes()
    win.rotate_action()
    monkeypatch.setattr(win, "show_custom_dialog", lambda *a, **k: QDialog.DialogCode.Rejected)
    win.saveModifiedImage(overwrite=True)
    assert win._huge_worker is None and original.read_bytes() == before
    monkeypatch.setattr(win, "show_custom_dialog", lambda *a, **k: QDialog.DialogCode.Accepted)
    win.saveModifiedImage(overwrite=True)
    assert _wait(qapp, lambda: win._huge_worker is None)
    assert Image.open(original).size == (1000, 1600)


# ------------------------------------------------------------------ HI-7
def test_hi7_pixel_actions_say_the_image_is_too_large(huge_window, qapp):
    """HI-7: no more "still loading" for ever: the message names the real reason and no decode is queued."""
    win = huge_window
    viewer = win.image_viewer
    assert win._full_resolution_gate() is False
    assert viewer.full_loader is None
    text = win.ephemeral_messages[0].text()
    assert "too large" in text and "2 MP" in text
    win.open_editor()
    assert getattr(win, "photo_editor", None) is None


def test_hi7_brightness_is_not_dropped_silently(huge_window, qapp):
    """HI-7: saving a rotation with brightness changed is refused with a message; nothing is written."""
    win = huge_window
    win.rotate_action()
    win.image_viewer.brightness_factor = 0.8
    try:
        win.saveModifiedImage(overwrite=False)
        assert win._huge_worker is None
        assert not (win.photos / "map_copy.jpg").exists()
        assert "Brightness" in win.ephemeral_messages[0].text()
    finally:
        # Offscreen there is no GL context: a repaint with brightness != 1 would crash in applyBrightnessGPU.
        win.image_viewer.brightness_factor = 1.0


def test_hi7_saving_without_a_rotation_says_so(huge_window, qapp):
    """HI-7: nothing to rotate -> a message, no 3 GB copy of the same file."""
    win = huge_window
    win.saveModifiedImage(overwrite=False)
    assert win._huge_worker is None and not (win.photos / "map_copy.jpg").exists()
    assert "Nothing to save" in win.ephemeral_messages[0].text()


# ------------------------------------------------------------------ HI-8
def test_hi8_rotating_on_screen_needs_no_decode(huge_window, qapp):
    """HI-8: R rotates the frame in memory at once; no loader is started."""
    win = huge_window
    viewer = win.image_viewer
    viewer._full_request_timer.stop()
    before = (viewer.loader, viewer.full_loader, viewer.detail_loader)
    win.rotate_action()
    assert viewer.rotation_angle == 90
    assert (viewer.loader, viewer.full_loader, viewer.detail_loader) == before
    rect = viewer.pixmap_item.sceneBoundingRect()
    assert rect.height() > rect.width()

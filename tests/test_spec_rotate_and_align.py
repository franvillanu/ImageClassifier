"""Executable form of docs/specs/SPEC-008-rotate-and-align.md."""
import json
import math
import time

import cv2
import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtTest import QTest

from image_classifier.config import DEFAULT_CONFIG
from image_classifier.editor import align
from image_classifier.imaging import huge

REQUIRES = ["RA-1", "RA-2", "RA-3", "RA-4", "RA-5", "RA-6", "RA-7", "RA-8"]


def _wait(qapp, cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    import image_classifier.app as app_module

    QStandardPaths.setTestModeEnabled(True)
    config = tmp_path / "viewer_config.json"
    config.write_text(json.dumps({"last_seen_version": app_module.__version__}))
    monkeypatch.setattr(app_module, "get_config_file", lambda: str(config))
    photos = tmp_path / "photos"
    photos.mkdir()
    arr = np.full((1000, 1600, 3), 120, np.uint8)
    cv2.rectangle(arr, (0, 0), (120, 120), (255, 0, 0), -1)       # red marker, top-left corner
    Image.fromarray(arr).save(photos / "a.png")
    window = app_module.PhotoViewer()
    window.resize(1000, 700)
    window.show()
    window.load_directory(str(photos), start_at_first=True)
    viewer = window.image_viewer
    assert _wait(qapp, lambda: viewer._shown_load_id == viewer.current_load_id and viewer.full_resolution_ready
                 and viewer.full_loader is None and not viewer._full_request_timer.isActive())
    window.photos = photos
    window.config_path = config
    yield window
    viewer._cancel_pending_loads()
    window._cancel_preloads()
    window._marked_save_timer.stop()
    window.close()


# ------------------------------------------------------------------ RA-3 geometry
@pytest.mark.parametrize("size,rot90,angle,expected", [
    ((640, 400), 0, 30.0, (754, 666)),     # 640cos30+400sin30, 640sin30+400cos30
    ((640, 400), 1, 0.0, (400, 640)),
    ((640, 400), 0, 0.0, (640, 400)),
    ((640, 400), 0, -30.0, (754, 666)),
    ((32000, 28000), 0, 2.0, (32000 * math.cos(math.radians(2)) + 28000 * math.sin(math.radians(2)),
                              32000 * math.sin(math.radians(2)) + 28000 * math.cos(math.radians(2)))),
])
def test_ra3_canvas_holds_the_whole_rotated_photo(size, rot90, angle, expected):
    """RA-3: canvas = W|cos a| + H|sin a| by W|sin a| + H|cos a| (after the 90-degree turns)."""
    got = align.canvas_size(size, rot90, angle)
    assert got == (round(expected[0]), round(expected[1]))
    state = align.align_state(size, rot90, angle)
    assert state.output_size == got


# ------------------------------------------------------------------ RA-4 file render
def _marked_png(path, size=(640, 400)):
    arr = np.full((size[1], size[0], 3), 140, np.uint8)
    cv2.rectangle(arr, (0, 0), (39, 39), (255, 0, 0), -1)           # 40 x 40 red top-left
    cv2.rectangle(arr, (size[0] - 40, size[1] - 40), (size[0] - 1, size[1] - 1), (0, 0, 255), -1)  # blue bottom-right
    Image.fromarray(arr).save(path)
    return arr


@pytest.mark.parametrize("rot90,angle", [(0, 20.0), (1, -12.5), (0, 44.0)])
def test_ra4_the_result_keeps_the_whole_photo_with_black_corners(tmp_path, rot90, angle):
    """RA-4: canvas-sized output, both corner markers fully inside, corners black, centre unchanged."""
    src, dst = tmp_path / "s.png", tmp_path / "d.png"
    _marked_png(src)
    state = align.align_state((640, 400), rot90, angle)
    huge.edit_file(str(src), str(dst), state, progress=lambda *_: None)
    with Image.open(dst) as out:
        got = np.asarray(out.convert("RGB")).astype(int)
    assert (got.shape[1], got.shape[0]) == align.canvas_size((640, 400), rot90, angle)
    red = (got[..., 0] > 200) & (got[..., 1] < 80) & (got[..., 2] < 80)
    blue = (got[..., 2] > 200) & (got[..., 0] < 80) & (got[..., 1] < 80)
    assert 1600 * 0.8 < red.sum() < 1600 * 1.2 and 1600 * 0.8 < blue.sum() < 1600 * 1.2   # nothing cropped
    assert got[1, 1].max() < 12 and got[-2, -2].max() < 12                                 # black corners
    assert abs(int(got[got.shape[0] // 2, got.shape[1] // 2, 0]) - 140) < 6                 # centre is the photo


def test_ra4_quarter_turns_alone_are_exact(tmp_path):
    """RA-4: no angle -> an exact 90-degree turn, no resampling loss."""
    src, dst = tmp_path / "s.png", tmp_path / "d.png"
    arr = _marked_png(src)
    huge.edit_file(str(src), str(dst), align.align_state((640, 400), 1, 0.0), progress=lambda *_: None)
    with Image.open(dst) as out:
        assert np.array_equal(np.asarray(out.convert("RGB")), np.rot90(arr, k=-1))


# ------------------------------------------------------------------ RA-1 / RA-2
def test_ra1_setting_is_off_by_default_and_saved(win):
    """RA-1: default off; the config carries it."""
    assert DEFAULT_CONFIG["advanced_rotation"] is False
    assert win.advanced_rotation is False
    win.set_advanced_rotation(True)
    assert json.loads(win.config_path.read_text())["advanced_rotation"] is True


def test_ra1_off_keeps_the_plain_90_degree_turn(win, qapp):
    """RA-1: with the setting off R rotates at once and opens nothing."""
    win.rotate_action()
    assert win.image_viewer.rotation_angle == 90
    assert getattr(win, "photo_editor", None) is None


def test_ra2_on_opens_the_screen_but_not_with_rotate_all(win, qapp):
    """RA-2: R opens the screen (no quick turn); with 'rotate all' it keeps turning immediately."""
    win.set_advanced_rotation(True)
    win.rotate_action()
    screen = win.photo_editor
    try:
        assert screen is not None and type(screen).__name__ == "AlignScreen"
        assert win.image_viewer.rotation_angle == 0
    finally:
        screen._close()
    win.rotate_all = True
    win.rotate_action()
    assert getattr(win, "photo_editor", None) is None and win.image_viewer.rotation_angle == 90


# ------------------------------------------------------------------ RA-3 / RA-5 screen
def test_ra3_ra5_screen_controls(win, qapp):
    """RA-3/RA-5: ruler range, result size, Save only when something changed, Esc cancels with no change."""
    win.set_advanced_rotation(True)
    before = (win.photos / "a.png").read_bytes()
    win.rotate_action()
    screen = win.photo_editor
    assert screen.ruler.LIMIT == 45 and screen.ruler.STEP == 0.1
    assert screen.result_size == (1600, 1000)
    assert not screen.btn_save.isEnabled()                 # RA-5
    screen.set_angle(10.0)
    assert screen.btn_save.isEnabled()
    assert screen.result_size == align.canvas_size((1600, 1000), 0, 10.0)
    screen.set_angle(0.0)
    assert not screen.btn_save.isEnabled()
    screen.turn(clockwise=True)                            # a 90-degree turn alone is a change
    assert screen.btn_save.isEnabled() and screen.result_size == (1000, 1600)
    QTest.keyClick(screen, Qt.Key.Key_Escape)
    assert _wait(qapp, lambda: win.photo_editor is None)
    assert (win.photos / "a.png").read_bytes() == before


# ------------------------------------------------------------------ RA-4 end to end
def test_ra4_saving_from_the_screen_runs_the_job(win, qapp):
    """RA-4: Save a copy: progress dialog, copy has the canvas size, original untouched, screen closes."""
    win.set_advanced_rotation(True)
    original = win.photos / "a.png"
    before = original.read_bytes()
    win.rotate_action()
    screen = win.photo_editor
    saved = []
    screen.saved.connect(lambda path, overwrote: saved.append((path, overwrote)))
    screen.set_angle(7.5)
    screen.save(overwrite=False)
    assert screen._job is not None and screen._job.dialog.isVisible()
    assert _wait(qapp, lambda: screen._job is None and saved)
    copy = win.photos / "a_copy.png"
    assert saved[0][1] is False and copy.exists()
    with Image.open(copy) as out:
        assert out.size == align.canvas_size((1600, 1000), 0, 7.5)
    assert original.read_bytes() == before
    assert _wait(qapp, lambda: win.photo_editor is None)


# ------------------------------------------------------------------ RA-6
def test_ra6_unsaved_changes_block_the_screen(win, qapp):
    """RA-6: the save works on the file, so unsaved viewer edits must be saved or undone first."""
    win.set_advanced_rotation(True)
    win.image_modified = True
    win.rotate_action()
    assert getattr(win, "photo_editor", None) is None
    assert "unsaved" in win.ephemeral_messages[0].text().lower() or "save or undo" in win.ephemeral_messages[0].text().lower()


# ------------------------------------------------------------------ RA-7 zoom and pan
def _screen(win):
    win.set_advanced_rotation(True)
    win.rotate_action()
    return win.photo_editor


def test_ra7_zoom_about_the_pointer_with_limits(win, qapp):
    """RA-7: the point under the pointer stays put; zoom is limited between fit and the maximum."""
    from PyQt6.QtCore import QPointF

    s = _screen(win)
    c = s._canvas
    try:
        assert c.zoom == 1.0
        f0 = c.frame_rect()
        anchor = QPointF(c.width() * 0.55, c.height() * 0.45)
        u = ((anchor.x() - f0.left()) / f0.width(), (anchor.y() - f0.top()) / f0.height())
        size_before = s.result_size
        c.zoom_by(2.0, anchor)
        f = c.frame_rect()
        assert c.zoom == pytest.approx(2.0)
        assert f.left() + u[0] * f.width() == pytest.approx(anchor.x(), abs=1.5)
        assert f.top() + u[1] * f.height() == pytest.approx(anchor.y(), abs=1.5)
        assert s.result_size == size_before                   # zoom never changes the result
        c.zoom_by(1000.0, None)
        assert c.zoom == pytest.approx(c.max_zoom()) and c.max_zoom() > 1.0
        c.zoom_by(1e-6, None)
        assert c.zoom == 1.0
    finally:
        s._close()


def test_ra7_the_frame_never_leaves_the_view_and_fit_resets(win, qapp):
    """RA-7: panning stops at the frame's edges; fit restores the fitted view."""
    s = _screen(win)
    c = s._canvas
    try:
        c.zoom_by(3.0, None)
        c.pan_by(100000, 100000)
        f, a = c.frame_rect(), c._avail()
        assert f.left() <= a.left() + 0.5 and f.top() <= a.top() + 0.5
        assert f.right() >= a.right() - 0.5 and f.bottom() >= a.bottom() - 0.5
        c.pan_by(-100000, -100000)
        f = c.frame_rect()
        assert f.right() >= a.right() - 0.5 and f.bottom() >= a.bottom() - 0.5
        c.fit()
        assert c.zoom == 1.0 and c.frame_rect() == c._fit_frame()
    finally:
        s._close()


def test_ra7_inputs_zoom_pan_and_fit(win, qapp):
    """RA-7: wheel and +/- zoom, drag pans, double-click / Backspace / Ctrl+0 fit; the zoom level is shown."""
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtGui import QWheelEvent

    s = _screen(win)
    c = s._canvas
    try:
        pos = QPointF(s.width() / 2, s.height() / 2)
        s.wheelEvent(QWheelEvent(pos, pos, QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                                 Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
        assert c.zoom > 1.0 and "%" in s.info.text()
        QTest.keyClick(s, Qt.Key.Key_Minus)
        QTest.keyClick(s, Qt.Key.Key_Minus)
        QTest.keyClick(s, Qt.Key.Key_Minus)
        assert c.zoom == 1.0
        for _ in range(3):
            QTest.keyClick(s, Qt.Key.Key_Plus)
        assert c.zoom > 1.0
        before = c.frame_rect().center()
        centre = QPoint(s.width() // 2, s.height() // 3)
        QTest.mousePress(s, Qt.MouseButton.LeftButton, pos=centre)
        QTest.mouseMove(s, centre + QPoint(-60, -20))
        QTest.mouseRelease(s, Qt.MouseButton.LeftButton, pos=centre + QPoint(-60, -20))
        assert c.frame_rect().center() != before
        QTest.keyClick(s, Qt.Key.Key_Backspace)
        assert c.zoom == 1.0
        c.zoom_by(2.0, None)
        QTest.keyClick(s, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
        assert c.zoom == 1.0
        c.zoom_by(2.0, None)
        QTest.mouseDClick(s, Qt.MouseButton.LeftButton, pos=centre)
        assert c.zoom == 1.0
    finally:
        s._close()


# ------------------------------------------------------------------ RA-8 performance
def test_ra8_nothing_is_copied_or_rebuilt_by_turns_zoom_or_angle(win, qapp):
    """RA-8: the one frame is drawn as given (no per-turn rotated copy)."""
    s = _screen(win)
    c = s._canvas
    try:
        key = c._base.cacheKey()
        for _ in range(4):
            s.turn(True)
        s.set_angle(12.3)
        c.zoom_by(2.0, None)
        c.pan_by(30, 10)
        assert c._base.cacheKey() == key and not hasattr(c, "_oriented")
    finally:
        s._close()


def test_ra8_fast_sampling_while_dragging_and_smooth_after(win, qapp):
    """RA-8: ruler drag uses fast sampling; release restores smooth sampling."""
    s = _screen(win)
    try:
        assert s._canvas.smooth
        s.ruler.pressed.emit()
        assert not s._canvas.smooth and s._canvas._grid
        s.ruler.released.emit()
        assert s._canvas.smooth and not s._canvas._grid
    finally:
        s._close()


def test_ra8_the_frame_keeps_up_to_8192_px_and_painting_it_is_fast(win, qapp):
    """RA-8: a 8192 px frame is kept whole (zoom shows real detail) and a zoomed, tilted paint stays quick."""
    from image_classifier.editor.align_screen import AlignScreen
    from PyQt6.QtGui import QImage

    big = QImage(8192, 5461, QImage.Format.Format_RGB32)
    big.fill(Qt.GlobalColor.darkGray)
    s = AlignScreen(win, big, str(win.photos / "a.png"), (32000, 21332))
    try:
        assert s._canvas._base.width() == 8192
        s.set_angle(3.7)
        timings = {}
        for name, zoom in (("fit", 1.0), ("zoomed", 99.0)):
            s._canvas.fit()
            s._canvas.zoom_by(zoom, None)
            start = time.perf_counter()
            grabbed = s._canvas.grab().toImage()
            timings[name] = time.perf_counter() - start
            centre = grabbed.pixelColor(grabbed.width() // 2, grabbed.height() // 2)
            assert centre.red() > 60 and centre.green() > 60   # the photo (dark grey) really was painted
        print("paint seconds", timings)
        assert max(timings.values()) < 1.5
    finally:
        s._close()


def test_ra7_a_reduced_frame_never_zooms_past_the_real_pixels_and_fit_is_labelled(win, qapp):
    """RA-7: fitted shows "Fit (n %)"; a map's reduced frame stops at exactly 100 % of the real pixels."""
    from image_classifier.editor.align_screen import AlignScreen
    from PyQt6.QtGui import QImage

    frame = QImage(8192, 6872, QImage.Format.Format_RGB32)      # a quarter of a 32,000 x 26,850 map
    frame.fill(Qt.GlobalColor.darkGray)
    s = AlignScreen(win, frame, str(win.photos / "a.png"), (32000, 26850))
    try:
        assert s.info.text().endswith("%)") and "Fit (" in s.info.text()
        s._canvas.zoom_by(1000.0, None)
        s._refresh_info()
        assert s._canvas.screen_per_true_pixel() == pytest.approx(1.0, abs=0.01)
        assert "Zoom 100 %" in s.info.text()
    finally:
        s._close()

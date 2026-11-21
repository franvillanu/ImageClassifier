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

REQUIRES = ["RA-1", "RA-2", "RA-3", "RA-4", "RA-5", "RA-6"]


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

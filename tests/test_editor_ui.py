"""End-to-end tests for the photo editor widgets (offscreen)."""
import time

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from image_classifier.editor import geometry as g
from image_classifier.editor.editor_window import PhotoEditor
from image_classifier.editor.widgets import StraightenRuler


def _wait(pred, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


def _mouse(widget, kind, pos, button=Qt.MouseButton.LeftButton):
    buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else button
    ev = QMouseEvent(kind, QPointF(pos), QPointF(widget.mapToGlobal(QPoint(int(pos.x()), int(pos.y())))),
                     button, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


def _drag(widget, a, b, steps=8):
    _mouse(widget, QEvent.Type.MouseButtonPress, a)
    for i in range(1, steps + 1):
        _mouse(widget, QEvent.Type.MouseMove, a + (b - a) * (i / steps))
    _mouse(widget, QEvent.Type.MouseButtonRelease, b)


@pytest.fixture
def photo(tmp_path):
    w, h = 900, 600
    y, x = np.mgrid[0:h, 0:w]
    arr = np.zeros((h, w, 3), np.uint8)
    arr[..., 0] = (x * 255 // w).astype(np.uint8)
    arr[..., 1] = (y * 255 // h).astype(np.uint8)
    arr[..., 2] = 180
    path = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    Image.fromarray(arr).save(path, quality=95, exif=exif.tobytes())
    return path, QImage(str(path))


@pytest.fixture
def editor(photo):
    path, image = photo
    host = QWidget()
    host.resize(1400, 900)
    host.show()
    ed = PhotoEditor(host, image, str(path), language="es")
    QApplication.processEvents()
    yield ed, host, path
    if not ed._closing:
        ed._close()
    host.deleteLater()
    QApplication.processEvents()


def test_ruler_snaps_and_resets():
    r = StraightenRuler()
    r.resize(600, 44)
    got = []
    r.valueChanged.connect(got.append)
    _drag(r, QPointF(300, 20), QPointF(300 - StraightenRuler.PX_PER_DEGREE * 6.6, 20))
    assert abs(r.value() - 6.6) < 0.11
    _drag(r, QPointF(300, 20), QPointF(300 + StraightenRuler.PX_PER_DEGREE * 6.5, 20))  # back to ~0.1 -> snaps to 0
    assert r.value() == 0.0
    assert r.text().endswith("°")


def test_straighten_and_drag_keep_crop_inside(editor):
    ed, _, _ = editor
    ed._ruler_pressed()
    ed._ruler_changed(-6.6)
    ed._ruler_released()
    st = ed._state
    assert st.crop.angle == -6.6
    assert g.is_valid(st.crop, st.oriented_size)
    canvas = ed.crop_canvas
    fx, fy, fw, fh = canvas._view.frame_rect(st.crop)
    # Drag the top-left handle far outside the image: the crop must stay inside.
    _drag(canvas, QPointF(fx, fy), QPointF(fx - 2000, fy - 2000))
    assert g.is_valid(ed._state.crop, ed._state.oriented_size)
    # Pan the image hard in one direction.
    _drag(canvas, QPointF(fx + fw / 2, fy + fh / 2), QPointF(fx + fw / 2 + 3000, fy + fh / 2))
    assert g.is_valid(ed._state.crop, ed._state.oriented_size)
    assert ed._history.can_undo()


def test_undo_redo_roundtrip(editor):
    ed, _, _ = editor
    s0 = ed._state
    ed._orient(lambda s: g.rotate90(s, True))
    ed.sliders["contrast"].slider.setValue(30)
    assert ed._state.adjust.contrast == 30
    ed._undo()
    assert ed._state.adjust.contrast == 0
    ed._undo()
    assert ed._state == s0
    ed._redo()
    assert ed._state.orientation.rot90 == 1


def test_resize_keeps_crop(editor):
    ed, host, _ = editor
    ed._set_aspect(1.0)
    before = ed._state.crop
    host.resize(1000, 700)
    QApplication.processEvents()
    assert ed._state.crop == before


def test_adjust_tab_renders_preview(editor):
    ed, _, _ = editor
    ed._switch_tab("adjust")
    ed.sliders["exposure"].slider.setValue(40)
    assert _wait(lambda: ed.adjust_canvas._image is not None)
    assert ed.adjust_canvas._size == ed._state.output_size


def test_save_copy_writes_cropped_image_with_metadata(editor, tmp_path):
    ed, _, path = editor
    ed._ruler_pressed()
    ed._ruler_changed(8.0)
    ed._ruler_released()
    ed.sliders["vignette"].slider.setValue(-40)
    saved = []
    ed.saved.connect(lambda p, o: saved.append((p, o)))
    ed._save(overwrite=False)
    assert _wait(lambda: saved, timeout=20)
    out_path, overwrite = saved[0]
    assert not overwrite and out_path.endswith("photo_copy.jpg")
    with Image.open(out_path) as img:
        assert img.size == ed._state.output_size
        assert img.getexif()[0x010F] == "TestCam"
        arr = np.asarray(img)
    # No black wedges from the straighten: the blue channel is 180 everywhere in the source.
    assert arr[..., 2].min() > 60


def test_cancel_clean_editor_closes_without_prompt(editor):
    ed, _, _ = editor
    closed = []
    ed.closed.connect(lambda: closed.append(True))
    ed.request_cancel()
    assert closed


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0, 3.0])
def test_icons_render_centred_at_any_display_scaling(scale):
    """Regression: at 200 % icons were once drawn 2x and clipped to their top-left quarter."""
    from image_classifier.editor import icons
    for name in icons.GLYPHS:
        pm = icons.pixmap(name, 24, scale)
        assert pm.devicePixelRatio() == scale
        img = pm.toImage()
        alpha = np.array([[img.pixelColor(x, y).alpha() for x in range(img.width())]
                          for y in range(img.height())])
        ys, xs = np.nonzero(alpha > 40)
        assert len(xs) > 0, name
        cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
        size = img.width()
        assert abs(cx - size / 2) < size * 0.25 and abs(cy - size / 2) < size * 0.25, (name, scale)
        assert xs.max() - xs.min() > size * 0.3 or ys.max() - ys.min() > size * 0.3, (name, scale)


def test_drag_just_outside_frame_straightens(editor):
    ed, _, _ = editor
    canvas = ed.crop_canvas
    fx, fy, fw, fh = canvas._view.frame_rect(ed._state.crop)
    cx, cy = fx + fw / 2, fy + fh / 2
    start = QPointF(fx + fw + 20, cy)  # right of the frame, inside the rotate band
    assert canvas._hit(start) == "rotate"
    _drag(canvas, start, QPointF(fx + fw + 20, cy + 80))  # clockwise around the centre
    st = ed._state
    assert st.crop.angle > 1.0
    assert ed.ruler.value() == st.crop.angle
    assert g.is_valid(st.crop, st.oriented_size)
    assert ed._history.can_undo()


def test_drag_inside_frame_moves_the_frame_not_the_image(editor):
    ed, _, _ = editor
    ed._set_aspect(1.0)
    canvas = ed.crop_canvas
    view_before = canvas._view
    before = ed._state.crop
    fx, fy, fw, fh = view_before.frame_rect(before)
    _drag(canvas, QPointF(fx + fw / 2, fy + fh / 2), QPointF(fx + fw / 2 + 40, fy + fh / 2))
    after = ed._state.crop
    assert canvas._view == view_before  # the image did not move
    assert after.cx > before.cx and abs(after.cy - before.cy) < 1e-6
    assert (after.w, after.h) == (before.w, before.h)
    assert g.is_valid(after, ed._state.oriented_size)
    assert ed._history.can_undo()


def test_wheel_zooms_the_view_without_touching_the_crop(editor):
    ed, _, _ = editor
    canvas = ed.crop_canvas
    before = ed._state.crop
    z0 = canvas._view.zoom
    canvas.zoom_by(1.5, QPointF(200, 200))
    assert canvas._view.zoom > z0 and ed._state.crop == before
    canvas.zoom_by(0.1)
    assert canvas._view == canvas._fit_view()  # zooming out snaps back to the whole image


def test_aspect_strip_sets_ratio(editor):
    ed, _, _ = editor
    ed.btn_aspect.click()
    assert ed.aspect_card.isVisible()
    index = next(i for i, (label, _) in enumerate(ed.aspect_strip._items) if label == "16 : 9")
    ed.aspect_strip.picked.emit(index)
    assert abs(ed._state.crop.w / ed._state.crop.h - 16 / 9) < 1e-3
    assert "16 : 9" in ed.btn_aspect.text()
    assert _wait(lambda: not ed.aspect_card.isVisible(), timeout=2)


def test_confirm_dialog_is_a_centred_card(editor):
    from image_classifier.editor.editor_window import _Modal
    ed, _, _ = editor
    m = _Modal(ed, "Title", "Body", [("keep", "Keep", "Secondary"), ("ok", "OK", "Primary")])
    QApplication.processEvents()
    card = m.findChild(QWidget, "DialogCard")
    assert card.width() == _Modal.WIDTH < ed.width()
    assert abs(card.geometry().center().x() - ed.width() / 2) <= 2
    m.deleteLater()


def test_handle_drag_does_not_zoom_or_move_the_view(editor):
    ed, _, _ = editor
    canvas = ed.crop_canvas
    view_before = canvas._view
    fx, fy, fw, fh = view_before.frame_rect(ed._state.crop)
    _drag(canvas, QPointF(fx + fw, fy + fh), QPointF(fx + fw * 0.6, fy + fh * 0.6))
    assert ed._state.crop.w < 0.7 * ed._state.source_size[0]
    QApplication.processEvents()
    assert canvas._view == view_before

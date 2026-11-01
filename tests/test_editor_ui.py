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
    """Regression: at 200 % the old SVG icons were drawn 2x and clipped to their top-left quarter."""
    from image_classifier.editor import icons
    assert icons.icon_family(), "Windows icon font not found"
    for name in icons.GLYPHS:
        img = icons.pixmap(name, 16, "#ffffff", scale).toImage()
        alpha = np.array([[img.pixelColor(x, y).alpha() for x in range(img.width())]
                          for y in range(img.height())])
        ys, xs = np.nonzero(alpha > 40)
        assert len(xs) > 0, name
        cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
        size = img.width()
        assert abs(cx - size / 2) < size * 0.25 and abs(cy - size / 2) < size * 0.25, (name, scale)
        assert xs.max() - xs.min() > size * 0.3 or ys.max() - ys.min() > size * 0.3, (name, scale)


def test_handle_drag_does_not_zoom_or_move_the_view(editor):
    ed, _, _ = editor
    canvas = ed.crop_canvas
    view_before = canvas._view
    fx, fy, fw, fh = view_before.frame_rect(ed._state.crop)
    _drag(canvas, QPointF(fx + fw, fy + fh), QPointF(fx + fw * 0.6, fy + fh * 0.6))
    assert ed._state.crop.w < 0.7 * ed._state.source_size[0]
    QApplication.processEvents()
    assert canvas._view == view_before

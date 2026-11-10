"""Executable form of docs/specs/SPEC-004-editor-view.md (ED-1, ED-2)."""
import time

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from image_classifier.editor import geometry as g
from image_classifier.editor.editor_window import PhotoEditor
from image_classifier.editor.render import output_to_source_matrix
from image_classifier.editor.state import CropGeometry, EditState, Orientation

REQUIRES = ["ED-1", "ED-2"]


def _wait(pred, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


def _mouse(widget, kind, pos):
    buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
    ev = QMouseEvent(kind, QPointF(pos), QPointF(widget.mapToGlobal(QPoint(int(pos.x()), int(pos.y())))),
                     Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


def _drag(widget, a, b, steps=6):
    _mouse(widget, QEvent.Type.MouseButtonPress, a)
    for i in range(1, steps + 1):
        _mouse(widget, QEvent.Type.MouseMove, a + (b - a) * (i / steps))
    _mouse(widget, QEvent.Type.MouseButtonRelease, b)


@pytest.fixture
def editor(qapp, tmp_path):
    w, h = 900, 1200  # portrait, like the reported cover
    y, x = np.mgrid[0:h, 0:w]
    arr = np.zeros((h, w, 3), np.uint8)
    arr[..., 0] = (x * 255 // w).astype(np.uint8)
    arr[..., 1] = (y * 255 // h).astype(np.uint8)
    arr[..., 2] = 180
    path = tmp_path / "photo.jpg"
    Image.fromarray(arr).save(path, quality=95)
    host = QWidget()
    host.resize(1400, 900)
    host.show()
    ed = PhotoEditor(host, QImage(str(path)), str(path), language="es")
    QApplication.processEvents()
    yield ed
    if not ed._closing:
        ed._close()
    host.deleteLater()
    QApplication.processEvents()


def _compare_source_at_center(ed):
    """Source point drawn at the view centre while comparing, and the compare scale."""
    c = ed.adjust_canvas
    rect, mid, z = c.image_rect(), c.area_center(), c.zoom()
    return ((mid.x() - rect.x()) / z, (mid.y() - rect.y()) / z), z


def _zoom_and_pan_adjust(ed):
    c = ed.adjust_canvas
    assert _wait(lambda: c._image is not None and c._size == ed._state.output_size)
    mid = c.area_center()
    c.zoom_by(3.0, mid + QPointF(0, 200))  # zoom towards the lower half
    _drag(c, mid, mid + QPointF(-120, -160))
    assert c.view_center() != QPointF(0.5, 0.5)
    return c


@pytest.mark.parametrize("state", [
    EditState(source_size=(900, 1200), crop=CropGeometry(400, 700, 500, 300, 0.0)),
    EditState(source_size=(900, 1200), orientation=Orientation(1, False), crop=CropGeometry(600, 400, 300, 200, 7.5)),
    EditState(source_size=(900, 1200), orientation=Orientation(2, True), crop=CropGeometry(450, 600, 400, 500, -4.0)),
    EditState(source_size=(900, 1200), orientation=Orientation(3, True), crop=CropGeometry(500, 450, 600, 300, 12.0)),
])
def test_ed1_output_point_maps_to_the_source_like_the_renderer(state):
    """ED-1: the compare anchor uses the same output->source mapping the renderer warps with."""
    out = (int(round(state.crop.w)), int(round(state.crop.h)))
    m = output_to_source_matrix(state, (1200, 900), out)
    for n in ((0.5, 0.5), (0.1, 0.8), (0.9, 0.2)):
        idx = m @ np.array([n[0] * out[0] - 0.5, n[1] * out[1] - 0.5, 1.0])
        sx, sy = g.output_to_source(state, n)
        assert abs(sx - (idx[0] + 0.5)) < 1e-6 and abs(sy - (idx[1] + 0.5)) < 1e-6
    o = g.orientation_matrix(state.orientation, state.source_size)
    p = (123.0, 456.0)
    q = (o[0][0] * p[0] + o[0][1] * p[1] + o[0][2], o[1][0] * p[0] + o[1][1] * p[1] + o[1][2])
    assert np.allclose(g.oriented_to_source(state, q), p)


def test_ed1_compare_keeps_the_zoomed_panned_spot_on_adjust(editor):
    """ED-1: Ajuste tab, zoomed and panned, no crop: the original shows the same spot at the same scale."""
    ed = editor
    ed._switch_tab("adjust")
    c = _zoom_and_pan_adjust(ed)
    edit_zoom, before = c.zoom(), c.image_rect()
    n = c.view_center()
    expected = (n.x() * ed._size[0], n.y() * ed._size[1])
    ed._set_compare(True)
    got, z = _compare_source_at_center(ed)
    assert abs(z - edit_zoom) < 1e-9
    assert abs(got[0] - expected[0]) < 0.5 and abs(got[1] - expected[1]) < 0.5, (got, expected)
    assert c.image_rect() == before  # no crop: the original covers exactly the edit's rect
    ed._set_compare(False)
    assert c.image_rect() == before  # released: the edit is back where it was


def test_ed1_compare_lines_up_with_a_cropped_turned_edit(editor):
    """ED-1: with a crop, straighten and 90° turn the source point at the view centre stays put."""
    ed = editor
    st = g.rotate90(ed._state, clockwise=True)
    st = EditState(source_size=st.source_size, orientation=st.orientation,
                   crop=g.fit_to_angle(CropGeometry(700, 450, 500, 400, 0.0), 6.0, st.oriented_size),
                   adjust=st.adjust)
    ed._set_state(st, commit=True)
    ed._switch_tab("result")
    c = _zoom_and_pan_adjust(ed)
    n = c.view_center()
    expected = g.output_to_source(ed._state, (n.x(), n.y()))
    edit_zoom = c.zoom()
    ed._set_compare(True)
    got, z = _compare_source_at_center(ed)
    assert abs(z - edit_zoom) < 1e-9
    assert abs(got[0] - expected[0]) < 0.5 and abs(got[1] - expected[1]) < 0.5, (got, expected)


def test_ed1_compare_from_the_crop_tab_keeps_the_view(editor):
    """ED-1: Crop tab zoomed in: the original keeps the crop view's scale and centre point."""
    ed = editor
    assert ed.stack.currentWidget() is ed.crop_canvas
    ed.crop_canvas.zoom_by(2.5)
    view = ed.crop_canvas._view
    mid = ed.adjust_canvas.area_center()
    expected = g.oriented_to_source(ed._state, view.to_image((mid.x(), mid.y())))
    ed._set_compare(True)
    got, z = _compare_source_at_center(ed)
    assert abs(z - view.zoom) < 1e-9
    assert abs(got[0] - expected[0]) < 0.5 and abs(got[1] - expected[1]) < 0.5, (got, expected)
    ed._set_compare(False)
    assert ed.stack.currentWidget() is ed.crop_canvas


def test_ed2_mouse_release_keeps_background_and_insets(editor):
    """ED-2: clicking/dragging the Ajuste canvas keeps its insets, background and image position."""
    ed = editor
    ed._switch_tab("adjust")
    c = ed.adjust_canvas
    assert _wait(lambda: c._image is not None)
    insets, bg, rect = c._insets, c._bg.name(), c.image_rect()
    assert insets != (0, 0, 0, 0)
    mid = c.area_center()
    _mouse(c, QEvent.Type.MouseButtonPress, mid)
    _mouse(c, QEvent.Type.MouseButtonRelease, mid)
    assert c._insets == insets and c._bg.name() == bg
    assert c.image_rect() == rect

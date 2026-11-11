"""Executable form of docs/specs/SPEC-004-editor-view.md (ED-1 to ED-8)."""
import time

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from image_classifier.editor import geometry as g
from image_classifier.editor.editor_window import PhotoEditor
from image_classifier.editor.render import output_to_source_matrix
from image_classifier.editor.state import CropGeometry, EditState, Orientation

REQUIRES = ["ED-1", "ED-2", "ED-3", "ED-4", "ED-5", "ED-6", "ED-7", "ED-8", "ED-9", "ED-10"]


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


def _in_editor(ed, w):
    """Widget geometry in editor coordinates."""
    return w.rect().translated(w.mapTo(ed, QPoint(0, 0)))


def test_ed3_modes_are_tabs_at_the_start_of_the_bottom_row(editor):
    """ED-3: Recortar/Ajuste are labelled tabs that start the bottom row; no rail, only close at the top."""
    ed = editor
    assert not hasattr(ed, "rail")
    for tab, label in ((ed.tab_crop, "Recortar"), (ed.tab_adjust, "Ajuste")):
        assert tab.text() == label and ed.crop_tools.isAncestorOf(tab)
    shown = [w for w in ed.crop_tools.findChildren(QWidget) if w.isVisible() and w.width() > 0]
    assert _in_editor(ed, ed.tab_crop).left() == min(_in_editor(ed, w).left() for w in shown)
    assert _in_editor(ed, ed.tab_crop).right() < _in_editor(ed, ed.tab_adjust).left()
    assert not ed.actions.isAncestorOf(ed.btn_save) and ed.actions.isAncestorOf(ed.btn_cancel)
    assert ed.tab_crop.isChecked() and not ed.tab_adjust.isChecked()
    ed._switch_tab("adjust")
    assert ed.tab_adjust.isChecked() and not ed.tab_crop.isChecked()


@pytest.mark.parametrize("tab", ["crop", "adjust", "result"])
def test_ed4_history_and_compare_live_in_the_bottom_row(editor, tab):
    """ED-4: undo, redo, reset and compare are in the bottom row on every tab, after the tab's tools."""
    ed = editor
    if tab == "result":
        ed._set_aspect(1.0)
        ed._apply_crop()
    else:
        ed._switch_tab(tab)
    QApplication.processEvents()
    assert _in_editor(ed, ed.crop_tools).top() > ed.height() * 0.75
    for b in (ed.btn_undo, ed.btn_redo, ed.btn_reset, ed.btn_compare):
        assert ed.crop_tools.isAncestorOf(b) and b.isVisible()
    tools = ed.crop_group if tab == "crop" else ed.adjust_group if tab == "adjust" else None
    if tools is not None:
        assert _in_editor(ed, tools).right() < _in_editor(ed, ed.btn_undo).left()
    assert _in_editor(ed, ed.btn_undo).right() < _in_editor(ed, ed.btn_redo).left()


@pytest.mark.parametrize("tab", ["crop", "adjust", "result"])
def test_ed5_the_row_ends_in_one_accent_button(editor, tab):
    """ED-5: Listo while cropping, Guardar elsewhere: one accent button, last in the bottom row."""
    ed = editor
    if tab == "result":
        ed._set_aspect(1.0)
        ed._apply_crop()
    else:
        ed._switch_tab(tab)
        ed._set_aspect(1.0)  # so both would be enabled
    QApplication.processEvents()
    expected = ed.btn_apply if tab == "crop" else ed.btn_save
    other = ed.btn_save if tab == "crop" else ed.btn_apply
    assert expected.isVisible() and not other.isVisible()
    assert expected.objectName() == "Primary" and ed.crop_tools.isAncestorOf(expected)
    shown = [w for w in ed.crop_tools.findChildren(QWidget) if w.isVisible() and w.width() > 0]
    assert _in_editor(ed, expected).right() == max(_in_editor(ed, w).right() for w in shown)


def test_ed5_save_options_open_above_the_bottom_row(editor):
    """ED-5: Guardar sits at the bottom, so its options open above it, fully inside the editor."""
    ed = editor
    ed._set_aspect(1.0)
    ed._switch_tab("adjust")
    ed.btn_save.click()
    menu = ed.save_menu
    assert _wait(lambda: menu._slide.state() == menu._slide.State.Stopped, timeout=2)
    card = menu.card.geometry()
    assert card.bottom() < _in_editor(ed, ed.btn_save).top() and card.top() >= 0
    menu.close_menu()


def test_ed6_photo_area_uses_the_full_width(editor):
    """ED-6: left and right insets are equal and only the edge gap on both canvases and tabs."""
    from image_classifier.editor.editor_window import EDGE
    ed = editor
    for tab in ("crop", "adjust"):
        ed._switch_tab(tab)
        for c in (ed.crop_canvas, ed.adjust_canvas):
            left, _, right, _ = c._insets
            assert left == right <= EDGE + 8, (tab, c._insets)


@pytest.mark.parametrize("width", [1920, 1366, 1280])
def test_ed7_bottom_row_fits_the_window(editor, width):
    """ED-7: on every tab the row stays inside the window; labels go first, then the ruler narrows."""
    ed = editor
    ed.parent().resize(width, 900)
    for tab in ("crop", "adjust", "result"):
        ed._switch_tab(tab)
        QApplication.processEvents()
        r = _in_editor(ed, ed.crop_tools)
        assert r.left() >= 0 and r.right() < ed.width(), (width, tab, r)
        assert ed.ruler.width() >= 200
        if width == 1920:
            assert not ed.tab_crop._compact and ed.ruler.width() == 360
    ed.parent().resize(1920, 900)
    ed._switch_tab("crop")
    QApplication.processEvents()
    assert not ed.tab_crop._compact and ed.ruler.width() == 360  # wider again: everything comes back


def test_ed8_dock_is_an_opaque_rounded_card_over_a_zoomed_photo(qapp, tmp_path):
    """ED-8: over a white photo zoomed in, the dock stays dark grey; dividers; selected = filled square."""
    from image_classifier.editor.widgets import Divider
    path = tmp_path / "white.png"
    Image.fromarray(np.full((800, 1200, 3), 255, np.uint8)).save(path)
    host = QWidget()
    host.resize(1920, 1000)
    host.show()
    ed = PhotoEditor(host, QImage(str(path)), str(path), language="es")
    try:
        ed._switch_tab("adjust")
        c = ed.adjust_canvas
        assert _wait(lambda: c._image is not None)
        c.zoom_by(4.0)
        QApplication.processEvents()
        shot = ed.grab().toImage()
        dock = _in_editor(ed, ed.crop_tools)
        px = QColor(shot.pixel(dock.left() + 5, dock.center().y()))  # inside the dock's margin
        assert px.red() < 60 and px.green() < 60 and px.blue() < 60, px.name()
        assert sum(d.isVisible() for d in ed.crop_tools.findChildren(Divider)) >= 3
        b = ed.adjust_buttons["brightness"]
        assert b.isChecked()
        btn = b.grab().toImage()
        corner = QColor(btn.pixel(5, 6))  # inside the rounded square, outside the value ring
        assert corner.alpha() > 200 and corner.blue() > corner.red() + 15, corner.name()
    finally:
        ed._close()
        host.deleteLater()
        QApplication.processEvents()


def test_ed9_wand_on_auto_adjust_and_own_icon_on_auto_straighten(editor):
    """ED-9: the wand marks auto-adjust; auto-straighten has its own, different straighten icon."""
    from image_classifier.editor import icons
    assert editor.btn_enhance._name == "wand"
    assert editor.btn_auto._name == "straighten"
    assert icons._PATHS["straighten"] not in (icons._PATHS["wand"], icons._PATHS["enhance"])


def test_ed10_straighten_ruler_has_a_tick_every_five_degrees(editor):
    """ED-10: 19 ticks from -45 to 45, labelled ones (every 15) major, no 1-degree ticks."""
    r = editor.ruler
    units = r.tick_units()
    assert units == list(range(-45, 46, 5))
    assert [u for u in units if r.is_major(u)] == list(range(-45, 46, 15))

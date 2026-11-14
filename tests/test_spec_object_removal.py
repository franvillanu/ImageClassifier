"""Executable form of docs/specs/SPEC-005-object-removal.md (RM-1 to RM-8)."""
import time

import cv2
import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from image_classifier.editor import removal as rm
from image_classifier.editor.editor_window import PhotoEditor
from image_classifier.editor.render import render
from image_classifier.editor.state import CropGeometry, EditState, Orientation, Removal

REQUIRES = ["RM-1", "RM-2", "RM-3", "RM-4", "RM-5", "RM-6", "RM-7", "RM-8", "RM-9", "RM-10", "RM-11"]

W, H = 480, 320
PERIOD = 24


def _stripes(w=W, h=H, noise=10.0, seed=3):
    """Vertical stripes with grain: a pattern that a blur cannot fake and a patch copy continues."""
    x = np.arange(w)[None, :].repeat(h, 0)
    base = 128 + 70 * np.sin(2 * np.pi * x / PERIOD)
    grain = np.random.default_rng(seed).normal(0, noise, (h, w))
    rgb = np.stack([base + grain, base * 0.8 + grain, 90 + 0 * base + grain], -1)
    return np.clip(rgb, 0, 255).astype(np.uint8), base


def _rgba(rgb):
    return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])


STROKE = Removal(points=((190.0, 160.0), (290.0, 160.0)), radius=26.0)


@pytest.fixture(autouse=True)
def _fresh_caches():
    rm.clear_caches()
    yield
    rm.clear_caches()


def _highpass_std(gray, mask):
    hp = gray.astype(np.float32) - cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 3)
    return float(hp[mask].std())


def test_rm1_state_carries_removals_and_they_are_not_identity():
    """RM-1: removals are part of the state; they make it non-identity; initial has none."""
    s = EditState.initial((W, H))
    assert s.removals == () and s.is_identity
    t = s.with_removal(STROKE)
    assert t.removals == (STROKE,) and not t.is_identity
    assert EditState.initial((W, H)).removals == ()
    assert t.with_removal(STROKE).removals == (STROKE, STROKE)


def test_rm2_only_the_painted_area_changes():
    """RM-2: pixels away from the stroke are bit-identical after filling."""
    rgb, _ = _stripes()
    src = _rgba(rgb)
    out = rm.apply_removals(src, (STROKE,), (W, H))
    assert out is not src and out.shape == src.shape
    painted = rm.stroke_mask((H, W), STROKE, 1.0, margin=4.0) > 0
    assert (out[~painted] == src[~painted]).all()
    core = rm.stroke_mask((H, W), STROKE, 1.0) > 0
    assert (out[core] != src[core]).any()
    assert (out[..., 3] == 255).all()


def test_rm3_the_fill_has_texture_and_continues_the_pattern():
    """RM-3: not a blur: detail inside is >= 60 % of the surroundings, and the stripes run through the hole."""
    rgb, base = _stripes()
    out = rm.apply_removals(_rgba(rgb), (STROKE,), (W, H))
    core = rm.stroke_mask((H, W), STROKE, 1.0, margin=-2.0) > 0
    core[:, :200] = core[:, 280:] = False  # deep inside the area, away from its blended rim
    gray_in, gray_out = rgb[..., 1], out[..., 1]
    ring = (cv2.dilate(core.astype(np.uint8), np.ones((81, 81), np.uint8)) > 0) & ~(
        cv2.dilate(core.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0)
    assert _highpass_std(gray_out, core) >= 0.6 * _highpass_std(gray_in, ring)
    # the column profile inside the hole follows the stripes that were there before
    cols = np.arange(200, 280)
    got = gray_out[140:180, 200:280].astype(np.float32).mean(0)
    want = base[0, cols] * 0.8
    assert np.corrcoef(got, want)[0, 1] > 0.8


def test_rm3_a_plain_inpaint_would_fail_the_same_check():
    """RM-3 (control): Telea inpaint of the same area is flat, so the check above does measure something."""
    rgb, _ = _stripes()
    mask = rm.stroke_mask((H, W), STROKE, 1.0, margin=2.0)
    flat = cv2.inpaint(rgb, mask, 5, cv2.INPAINT_TELEA)
    core = rm.stroke_mask((H, W), STROKE, 1.0, margin=-2.0) > 0
    core[:, :200] = core[:, 280:] = False
    assert _highpass_std(flat[..., 1], core) < 0.6 * _highpass_std(rgb[..., 1], core)


def test_rm4_preview_and_full_resolution_use_the_same_plan():
    """RM-4: a proxy and the full source share one fill plan and agree where the fill is."""
    rgb, _ = _stripes(w=960, h=640)
    big = Removal(points=((380.0, 320.0), (580.0, 320.0)), radius=52.0)
    size = (960, 640)
    full = _rgba(rgb)
    proxy = _rgba(cv2.resize(rgb, (480, 320), interpolation=cv2.INTER_AREA))
    out_proxy = rm.apply_removals(proxy, (big,), size)
    assert len(rm._plans) == 1
    out_full = rm.apply_removals(full, (big,), size)
    assert len(rm._plans) == 1, "the full render must reuse the proxy's plan"
    down = cv2.resize(out_full, (480, 320), interpolation=cv2.INTER_AREA)
    hole = rm.stroke_mask((320, 480), Removal(tuple((x / 2, y / 2) for x, y in big.points), big.radius / 2), 1.0) > 0
    diff = np.abs(down[..., :3].astype(np.int16) - out_proxy[..., :3].astype(np.int16))[hole].mean()
    assert diff < 22, diff  # the stripes (amplitude 70) line up; a different fill would differ by ~50


def test_rm5_removals_follow_crop_and_turn():
    """RM-5: source-space strokes: a 90 deg turn rotates the filled photo; a crop away from the stroke is untouched."""
    rgb, _ = _stripes()
    src = _rgba(rgb)
    turned = EditState.initial((W, H), rot90=1).with_removal(STROKE)
    plain = EditState.initial((W, H)).with_removal(STROKE)
    assert (render(src, turned) == np.rot90(render(src, plain), k=-1)).all()
    away = EditState(source_size=(W, H), crop=CropGeometry(400.0, 160.0, 160.0, 320.0)).with_removal(STROKE)
    untouched = EditState(source_size=(W, H), crop=CropGeometry(400.0, 160.0, 160.0, 320.0))
    assert (render(src, away) == render(src, untouched)).all()


def test_rm5_adding_a_stroke_keeps_the_earlier_fills():
    """RM-5/RM-4: strokes apply in order and the second render only works on the new stroke."""
    rgb, _ = _stripes()
    src = _rgba(rgb)
    second = Removal(points=((90.0, 70.0), (120.0, 70.0)), radius=14.0)
    one = rm.apply_removals(src, (STROKE,), (W, H))
    two = rm.apply_removals(src, (STROKE, second), (W, H))
    assert len(rm._plans) == 2
    far = rm.stroke_mask((H, W), second, 1.0, margin=6.0) == 0
    assert (one[far] == two[far]).all()
    assert (one != two).any()


# ----------------------------------------------------------------------------- editor UI
def _wait(pred, timeout=30.0):
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


def _drag(widget, a, b, steps=8, button=Qt.MouseButton.LeftButton):
    _mouse(widget, QEvent.Type.MouseButtonPress, a, button)
    for i in range(1, steps + 1):
        _mouse(widget, QEvent.Type.MouseMove, a + (b - a) * (i / steps), button)
    _mouse(widget, QEvent.Type.MouseButtonRelease, b, button)


@pytest.fixture
def editor(qapp, tmp_path):
    rgb, _ = _stripes(w=900, h=600)
    path = tmp_path / "photo.png"
    Image.fromarray(rgb).save(path)
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


def _open_remove(ed):
    ed._switch_tab("remove")
    c = ed.adjust_canvas
    assert _wait(lambda: c._image is not None and c._size == ed._state.output_size)
    return c


def test_rm6_painting_adds_one_removal_at_the_dragged_place(editor):
    """RM-6: drag = one removal = one undo step, in source pixels; the cursor/brush size is known; wheel still zooms."""
    ed = editor
    c = _open_remove(ed)
    assert c.brush_active()
    rect, z = c.image_rect(), c.zoom()
    a = QPointF(rect.x() + 300 * z, rect.y() + 300 * z)
    b = QPointF(rect.x() + 420 * z, rect.y() + 300 * z)
    _drag(c, a, b)
    assert ed._state.removals == ()  # painted, not handed over yet: the user may still add strokes
    ed._commit_strokes()
    assert len(ed._state.removals) == 1
    r = ed._state.removals[0]
    assert abs(r.points[0][0] - 300) < 3 and abs(r.points[0][1] - 300) < 3
    assert abs(r.points[-1][0] - 420) < 3
    assert abs(r.radius - ed.brush_size.value() / 2 / z) < 1.0
    ed._undo()
    assert ed._state.removals == ()
    ed._redo()
    assert len(ed._state.removals) == 1
    # the removal reaches the picture on screen
    assert _wait(lambda: not c.is_waiting())
    # wheel zoom still works while the brush is on
    before = c.zoom()
    from PyQt6.QtGui import QWheelEvent
    ev = QWheelEvent(QPointF(a), QPointF(c.mapToGlobal(QPoint(int(a.x()), int(a.y())))), QPoint(0, 0), QPoint(0, 240),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(c, ev)
    assert c.zoom() > before
    # a right-button drag pans instead of painting
    n = len(ed._state.removals)
    _drag(c, QPointF(c.width() / 2, c.height() / 2), QPointF(c.width() / 2 - 80, c.height() / 2), button=Qt.MouseButton.RightButton)
    assert len(ed._state.removals) == n


def test_rm7_eliminar_is_the_third_tab_and_the_row_fits(editor):
    """RM-7: tab with icon, brush size in the row, shared actions, fits 1280 px."""
    ed = editor
    assert ed.tabs.layout().indexOf(ed.tab_remove) == 2
    for width in (1920, 1366, 1280):
        ed.parent().resize(width, 900)
        for tab in ("crop", "adjust", "remove", "result"):
            ed._switch_tab(tab)
            QApplication.processEvents()
            r = ed.crop_tools.geometry()
            assert r.left() >= 0 and r.right() < ed.width(), (width, tab, r)
    ed._switch_tab("remove")
    assert ed.tab_remove.isChecked() and not ed.tab_adjust.isChecked()
    assert not ed.remove_group.isHidden() and ed.adjust_group.isHidden() and ed.crop_group.isHidden()
    assert ed.dial_card.isHidden()
    for b in (ed.btn_compare, ed.btn_undo, ed.btn_redo, ed.btn_reset, ed.btn_save):
        assert not b.isHidden()
    assert ed.tab_remove._name == "eraser"


def test_rm8_compare_shows_the_original_and_other_tools_see_the_removal(editor):
    """RM-8: Comparar draws the unedited photo; the crop tab shows the photo with the object gone."""
    ed = editor
    c = _open_remove(ed)
    rect, z = c.image_rect(), c.zoom()
    _drag(c, QPointF(rect.x() + 300 * z, rect.y() + 300 * z), QPointF(rect.x() + 420 * z, rect.y() + 300 * z))
    ed._commit_strokes()
    assert _wait(lambda: not c.is_waiting())
    ed._set_compare(True)
    assert c._compare is not None and c._compare[0] is ed._orig_qimage
    ed._set_compare(False)
    ed._switch_tab("crop")
    top = ed.crop_canvas._levels[0][0]
    assert _wait(lambda: ed.crop_canvas._levels[0][0] is not ed._orig_levels[0][0])
    shown = ed.crop_canvas._levels[0][0]
    assert shown.size() == ed._orig_qimage.size()
    assert shown != ed._orig_qimage  # the painted area differs from the untouched photo


def test_rm6_strokes_in_quick_succession_are_one_removal(editor):
    """RM-6: several strokes + the pause = ONE removal with all of them; Ctrl+Z before it discards them."""
    ed = editor
    c = _open_remove(ed)
    rect, z = c.image_rect(), c.zoom()
    for y in (280, 320, 360):
        _drag(c, QPointF(rect.x() + 300 * z, rect.y() + y * z), QPointF(rect.x() + 420 * z, rect.y() + y * z))
    assert ed._state.removals == () and c.has_selection()
    assert _wait(lambda: len(ed._state.removals) == 1, timeout=5)  # the pause timer hands them over
    r = ed._state.removals[0]
    assert len(r.strokes()) == 3 and not c.has_selection()
    assert _wait(lambda: not c.is_waiting())
    assert len(ed._state.removals) == 1
    # painting again and undoing at once throws the new strokes away instead of the old removal
    _drag(c, QPointF(rect.x() + 100 * z, rect.y() + 100 * z), QPointF(rect.x() + 150 * z, rect.y() + 100 * z))
    ed._undo()
    assert not c.has_selection() and len(ed._state.removals) == 1
    ed._undo()
    assert ed._state.removals == ()


def test_rm9_overlapping_strokes_are_as_dark_as_one(editor):
    """RM-9: the painted area is one flat tint: a pixel under two overlapping strokes equals one under a single stroke."""
    ed = editor
    c = _open_remove(ed)
    c.set_brush_size(60)
    rect, z = c.image_rect(), c.zoom()
    y1 = rect.y() + 300 * z
    x0 = rect.x() + 200 * z
    probe = (int(x0 + 100), int(y1))
    plain = c.grab().toImage().pixelColor(*probe)
    _drag(c, QPointF(x0, y1), QPointF(x0 + 200, y1))
    c._hover = None
    once = c.grab().toImage().pixelColor(*probe)
    _drag(c, QPointF(x0, y1), QPointF(x0 + 200, y1))  # the same place again, and again, slightly off
    _drag(c, QPointF(x0 + 30, y1 + 5), QPointF(x0 + 190, y1 - 5))
    c._hover = None
    twice = c.grab().toImage().pixelColor(*probe)
    assert once != plain  # it is tinted
    assert once == twice, (once.name(), twice.name())


def test_rm10_a_card_and_pulse_show_while_the_fill_is_worked_out(editor):
    """RM-10: busy card ("Eliminando...") + pulsing area from hand-over until the new picture arrives, then nothing."""
    ed = editor
    c = _open_remove(ed)
    rect, z = c.image_rect(), c.zoom()
    _drag(c, QPointF(rect.x() + 300 * z, rect.y() + 300 * z), QPointF(rect.x() + 800 * z, rect.y() + 300 * z))
    c._hover = None
    before = c.grab().toImage()
    ed._worker.stop()  # keep the fill from arriving, to look at the waiting state
    ed._commit_strokes()
    assert c.is_waiting() and c._busy_timer.isActive() and c._busy_text == "Eliminando..."
    seen = {c.grab().toImage().pixelColor(int(rect.x() + 312 * z), int(rect.y() + 300 * z)).name()}
    for _ in range(12):
        c._tick()
        seen.add(c.grab().toImage().pixelColor(int(rect.x() + 312 * z), int(rect.y() + 300 * z)).name())
    assert len(seen) > 2, seen  # the area pulses
    card = c.grab().toImage()
    mid = card.pixelColor(int(rect.x() + 550 * z), int(rect.y() + 300 * z))
    assert mid.red() < 50 and mid.green() < 50  # the dark card sits over the middle of the painted area
    assert card != before
    c.set_image(c._image, c._size)  # the filled picture arrives
    assert not c.is_waiting() and not c._busy_timer.isActive()


def _region_area(region, w, h) -> int:
    """Pixels a paint region really covers (the rectangles of the region, not the box around them)."""
    from PyQt6.QtGui import QPainter as _P
    mask = QImage(w, h, QImage.Format.Format_Grayscale8)
    mask.fill(0)
    p = _P(mask)
    p.setClipRegion(region)
    p.fillRect(0, 0, w, h, Qt.GlobalColor.white)
    p.end()
    rows = np.frombuffer(mask.constBits().asstring(mask.sizeInBytes()), np.uint8).reshape(h, mask.bytesPerLine())
    return int((rows[:, :w] > 0).sum())


class _PaintLog:
    """Records the area of every paint event of a widget (what the compositor has to redo)."""

    def __init__(self, widget):
        from PyQt6.QtCore import QObject

        class Filter(QObject):
            def eventFilter(inner, obj, ev):
                if obj is widget and ev.type() == QEvent.Type.Paint:
                    self.areas.append(_region_area(ev.region(), widget.width(), widget.height()))
                return False

        self.areas = []
        self._filter = Filter(widget)
        widget.installEventFilter(self._filter)
        self.full = widget.width() * widget.height()

    def reset(self):
        self.areas.clear()


def test_rm11_moving_and_painting_repaint_only_a_small_area(editor):
    """RM-11: mouse moves repaint a small area; the painted area is a cached layer, not rebuilt per repaint."""
    ed = editor
    c = _open_remove(ed)
    c.set_brush_size(50)
    rect, z = c.image_rect(), c.zoom()
    log = _PaintLog(c)
    QApplication.processEvents()
    # hovering: ring only
    log.reset()
    for i in range(30):
        _mouse(c, QEvent.Type.MouseMove, QPointF(rect.x() + (200 + 6 * i) * z, rect.y() + 300 * z), Qt.MouseButton.NoButton)
        QApplication.processEvents()
    assert log.areas and max(log.areas) < 0.05 * log.full, (max(log.areas), log.full)
    # a big scribble already painted
    for i in range(8):
        y = 120 + i * 50
        _drag(c, QPointF(rect.x() + 60 * z, rect.y() + y * z), QPointF(rect.x() + 800 * z, rect.y() + y * z), steps=60)
    QApplication.processEvents()
    assert c.has_selection()
    builds = c._layer_builds
    log.reset()
    # painting one more stroke over it: small repaints, and no layer is rebuilt
    a, b = QPointF(rect.x() + 100 * z, rect.y() + 520 * z), QPointF(rect.x() + 600 * z, rect.y() + 540 * z)
    _mouse(c, QEvent.Type.MouseButtonPress, a)
    for i in range(1, 41):
        _mouse(c, QEvent.Type.MouseMove, a + (b - a) * (i / 40))
        QApplication.processEvents()
    _mouse(c, QEvent.Type.MouseButtonRelease, b)
    QApplication.processEvents()
    assert max(log.areas) < 0.08 * log.full, (max(log.areas), log.full)
    assert c._layer_builds == builds, "the painted layer must not be rebuilt while painting"
    # the busy pulse repaints the painted area and the card, not the whole canvas
    ed._request_previews = lambda: None  # no render arrives: look at the waiting state only
    ed._commit_strokes()
    QApplication.processEvents()
    log.reset()
    for _ in range(10):
        c._tick()
        QApplication.processEvents()
    assert log.areas and max(log.areas) < 0.6 * log.full  # this scribble covers a large part of the photo
    # a small removal's pulse is tiny
    c.set_image(c._image, c._size)
    c.set_brush_size(30)
    _drag(c, QPointF(rect.x() + 400 * z, rect.y() + 300 * z), QPointF(rect.x() + 440 * z, rect.y() + 300 * z))
    ed._commit_strokes()
    QApplication.processEvents()
    log.reset()
    for _ in range(10):
        c._tick()
        QApplication.processEvents()
    assert log.areas and max(log.areas) < 0.1 * log.full, (max(log.areas), log.full)

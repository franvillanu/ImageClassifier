"""Recortar canvas: the crop frame stays put, the image moves underneath.

Everything is drawn with one QTransform (proxy pixels -> source -> oriented ->
screen), so straightening, panning and zooming never resample pixels per frame.
Gestures produce new ``EditState`` values through the closed-form functions in
``geometry.py``; the canvas never owns the truth, the editor does.
"""
from __future__ import annotations

import math

import cv2
from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QTransform
from PyQt6.QtWidgets import QWidget

from image_classifier.editor import geometry as g
from image_classifier.editor.qtimage import rgba_to_qimage
from image_classifier.editor.state import EditState

CORNER_HIT = 18
EDGE_HIT = 10
MARGIN = 44
ANIM_MS = 180

_CURSORS = {
    "top_left": Qt.CursorShape.SizeFDiagCursor,
    "bottom_right": Qt.CursorShape.SizeFDiagCursor,
    "top_right": Qt.CursorShape.SizeBDiagCursor,
    "bottom_left": Qt.CursorShape.SizeBDiagCursor,
    "left": Qt.CursorShape.SizeHorCursor,
    "right": Qt.CursorShape.SizeHorCursor,
    "top": Qt.CursorShape.SizeVerCursor,
    "bottom": Qt.CursorShape.SizeVerCursor,
}


def build_levels(rgba, source_size: tuple[int, int]) -> list:
    """Mipmap pyramid of display images: [(QImage, source px per image px x, y), ...]."""
    W, H = source_size
    levels = []
    arr = rgba
    while True:
        img = rgba_to_qimage(arr).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        levels.append((img, W / arr.shape[1], H / arr.shape[0]))
        if max(arr.shape[:2]) <= 640:
            break
        arr = cv2.resize(arr, (max(1, arr.shape[1] // 2), max(1, arr.shape[0] // 2)),
                         interpolation=cv2.INTER_AREA)
    return levels


def _blend_view(a: g.View, b: g.View, t: float) -> g.View:
    lerp = lambda x, y: x + (y - x) * t
    return g.View(
        (lerp(a.focus[0], b.focus[0]), lerp(a.focus[1], b.focus[1])),
        (lerp(a.center[0], b.center[0]), lerp(a.center[1], b.center[1])),
        math.exp(lerp(math.log(a.zoom), math.log(b.zoom))),
        lerp(a.angle, b.angle),
    )


def _view_transform(v: g.View) -> QTransform:
    a = math.radians(v.angle)
    c, s = math.cos(a), math.sin(a)
    z = v.zoom
    fx, fy = v.focus
    return QTransform(z * c, z * s, -z * s, z * c,
                      v.center[0] - z * (c * fx - s * fy), v.center[1] - z * (s * fx + c * fy))


class CropCanvas(QWidget):
    stateEdited = pyqtSignal(object, bool)  # EditState, committed
    zoomChanged = pyqtSignal(float)  # physical screen pixels per source pixel

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._levels: list[tuple[QImage, float, float]] = []  # (image, src px per image px x/y)
        self._state: EditState | None = None
        self._view: g.View | None = None
        self._gesture = None
        self._grid = None  # None | "thirds" | "fine"
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim_from = self._anim_to = None
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(350)
        self._commit_timer.timeout.connect(self._commit_pending)
        self._pending_commit = False

    # ------------------------------------------------------------------ data
    def set_levels(self, levels: list):
        """Set the pixels to display, as built by ``build_levels`` (safe to build off-thread)."""
        self._levels = levels
        self.update()

    def state(self) -> EditState | None:
        return self._state

    def set_state(self, state: EditState, *, animate: bool = False):
        """Show ``state`` (from undo, buttons, the ruler...). Cancels any gesture."""
        old_view = self._view
        self._state = state
        self._gesture = None
        target = self._fit()
        if animate and old_view is not None and target is not None:
            self._start_anim(old_view, target)
        else:
            self._anim.stop()
            self._view = target
            self._emit_zoom()
        self.update()

    def set_grid(self, grid: str | None):
        self._grid = grid
        self.update()

    def _bounds(self):
        return self._state.oriented_size

    def _fit(self) -> g.View | None:
        if self._state is None or self.width() < 10 or self.height() < 10:
            return None
        return g.fit_view(self._state.crop, (0, 0, self.width(), self.height()), MARGIN)

    def _emit_zoom(self):
        if self._view is not None:
            self.zoomChanged.emit(self._view.zoom * self.devicePixelRatioF())

    def _emit(self, state: EditState, committed: bool):
        self._state = state
        self.stateEdited.emit(state, committed)

    # ------------------------------------------------------------------ animation
    def _start_anim(self, a: g.View, b: g.View):
        self._anim.stop()
        self._anim_from, self._anim_to = a, b
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _on_anim(self, t):
        if self._anim_from is None:
            return
        self._view = _blend_view(self._anim_from, self._anim_to, float(t))
        self._emit_zoom()
        self.update()

    # ------------------------------------------------------------------ zoom API
    def zoom_by(self, factor: float, anchor_screen: QPointF | None = None):
        if self._state is None or self._view is None:
            return
        anchor = None if anchor_screen is None else self._view.to_image((anchor_screen.x(), anchor_screen.y()))
        crop = g.zoom(self._state.crop, factor, anchor, self._bounds())
        if crop != self._state.crop:
            self._emit(self._state.with_crop(crop), False)
            self._view = self._fit()
            self._emit_zoom()
            self._schedule_commit()
            self.update()

    def _schedule_commit(self):
        self._pending_commit = True
        self._commit_timer.start()

    def _commit_pending(self):
        if self._pending_commit and self._state is not None:
            self._pending_commit = False
            self.stateEdited.emit(self._state, True)

    # ------------------------------------------------------------------ painting
    def _pick_level(self, view: g.View):
        """Smallest pyramid level that still has >= 1 image pixel per physical screen pixel."""
        need = view.zoom * self.devicePixelRatioF()  # physical px per source px
        best = self._levels[0]
        for lvl in self._levels:
            if 1.0 / lvl[1] >= need * 0.999:
                best = lvl
        return best

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(28, 28, 28))
        st, view = self._state, self._view
        if st is None or view is None or not self._levels:
            p.end()
            return
        img, sx, sy = self._pick_level(view)
        m = g.orientation_matrix(st.orientation, st.source_size)
        t_scale = QTransform(sx, 0, 0, sy, 0, 0)
        t_orient = QTransform(m[0][0], m[1][0], m[0][1], m[1][1], m[0][2], m[1][2])
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setTransform(t_scale * t_orient * _view_transform(view))
        p.drawImage(0, 0, img)
        p.resetTransform()

        fx, fy, fw, fh = view.frame_rect(st.crop)
        frame = QRectF(fx, fy, fw, fh)
        # dim everything outside the frame
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(QRectF(self.rect()))
        path.addRect(frame)
        p.fillPath(path, QColor(28, 28, 28, 165))

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self._grid:
            self._paint_grid(p, frame)
        p.setPen(QPen(QColor(255, 255, 255, 210), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(frame.adjusted(0, 0, -1, -1))
        self._paint_handles(p, frame)
        self._paint_size(p, frame)
        p.end()

    def _paint_grid(self, p: QPainter, f: QRectF):
        n = 9 if self._grid == "fine" else 3
        for i in range(1, n):
            major = self._grid == "thirds" or i % 3 == 0
            p.setPen(QPen(QColor(255, 255, 255, 120 if major else 55), 1))
            x = f.left() + f.width() * i / n
            y = f.top() + f.height() * i / n
            p.drawLine(QPointF(x, f.top()), QPointF(x, f.bottom()))
            p.drawLine(QPointF(f.left(), y), QPointF(f.right(), y))

    def _paint_handles(self, p: QPainter, f: QRectF):
        L, T = 22.0, 4.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        l, t, r, b = f.left(), f.top(), f.right(), f.bottom()
        # L-shaped brackets just outside each corner
        for horiz, vert in (
            (QRectF(l - T, t - T, L + T, T), QRectF(l - T, t - T, T, L + T)),
            (QRectF(r - L, t - T, L + T, T), QRectF(r, t - T, T, L + T)),
            (QRectF(l - T, b, L + T, T), QRectF(l - T, b - L, T, L + T)),
            (QRectF(r - L, b, L + T, T), QRectF(r, b - L, T, L + T)),
        ):
            p.drawRect(horiz)
            p.drawRect(vert)
        cx, cy = f.center().x(), f.center().y()
        if f.width() > 3 * L:
            p.drawRect(QRectF(cx - L / 2, t - T, L, T))
            p.drawRect(QRectF(cx - L / 2, b, L, T))
        if f.height() > 3 * L:
            p.drawRect(QRectF(l - T, cy - L / 2, T, L))
            p.drawRect(QRectF(r, cy - L / 2, T, L))

    def _paint_size(self, p: QPainter, f: QRectF):
        w, h = self._state.output_size
        text = f"{w} x {h}"
        font = QFont(self.font())
        font.setPixelSize(12)
        p.setFont(font)
        tw = p.fontMetrics().horizontalAdvance(text) + 16
        th = 24
        x = f.center().x() - tw / 2
        y = f.bottom() - th - 12 if f.height() > th * 3 else f.bottom() + 10
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(32, 32, 32, 225))
        p.drawRoundedRect(QRectF(x, y, tw, th), 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x, y, tw, th), Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------------ hit testing
    def _hit(self, pos: QPointF) -> str:
        if self._view is None or self._state is None:
            return "pan"
        fx, fy, fw, fh = self._view.frame_rect(self._state.crop)
        l, t, r, b = fx, fy, fx + fw, fy + fh
        x, y = pos.x(), pos.y()
        for name, (cx, cy) in (("top_left", (l, t)), ("top_right", (r, t)),
                               ("bottom_left", (l, b)), ("bottom_right", (r, b))):
            if abs(x - cx) <= CORNER_HIT and abs(y - cy) <= CORNER_HIT:
                return name
        if t <= y <= b:
            if abs(x - l) <= EDGE_HIT:
                return "left"
            if abs(x - r) <= EDGE_HIT:
                return "right"
        if l <= x <= r:
            if abs(y - t) <= EDGE_HIT:
                return "top"
            if abs(y - b) <= EDGE_HIT:
                return "bottom"
        return "pan"

    # ------------------------------------------------------------------ events
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._gesture is None:
            self._anim.stop()
            self._view = self._fit()
            self._emit_zoom()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._state is None or self._view is None:
            return
        self._anim.stop()
        self._commit_pending()
        kind = self._hit(e.position())
        self._gesture = {"kind": kind, "start": self._state, "pos": e.position(), "view": self._view}
        self._grid = "thirds"
        if kind == "pan":
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.update()

    def mouseMoveEvent(self, e):
        gst = self._gesture
        if gst is None:
            self.setCursor(_CURSORS.get(self._hit(e.position()), Qt.CursorShape.OpenHandCursor))
            return
        start: EditState = gst["start"]
        view: g.View = gst["view"]
        d = e.position() - gst["pos"]
        bounds = start.oriented_size
        if gst["kind"] == "pan":
            delta = view.delta_to_image((-d.x(), -d.y()))
            crop = g.pan(start.crop, delta, bounds)
            self._emit(start.with_crop(crop), False)
            self._view = self._fit()
        else:
            aspect = start.aspect
            if aspect is None and e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                aspect = start.crop.w / start.crop.h
            crop = g.resize_handle(start.crop, gst["kind"], (d.x() / view.zoom, d.y() / view.zoom),
                                   aspect, bounds)
            self._emit(start.with_crop(crop), False)
            # view stays frozen during the drag so the frame visibly follows the pointer
        self.update()

    def mouseReleaseEvent(self, e):
        gst = self._gesture
        if gst is None or e.button() != Qt.MouseButton.LeftButton:
            return
        self._gesture = None
        self._grid = None
        self.setCursor(_CURSORS.get(self._hit(e.position()), Qt.CursorShape.OpenHandCursor))
        if self._state != gst["start"]:
            self.stateEdited.emit(self._state, True)
        target = self._fit()
        if gst["kind"] != "pan" and target is not None and self._view is not None:
            self._start_anim(self._view, target)
        else:
            self._view = target
        self.update()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps:
            self.zoom_by(1.15 ** steps, e.position())
        e.accept()

    def keyPressEvent(self, e):
        if self._state is None or self._view is None:
            return super().keyPressEvent(e)
        step = 10.0 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if e.key() in moves:
            dx, dy = moves[e.key()]
            # Arrow moves the image, so the crop moves the opposite way.
            delta = self._view.delta_to_image((-dx, -dy))
            crop = g.pan(self._state.crop, delta, self._bounds())
            if crop != self._state.crop:
                self._emit(self._state.with_crop(crop), False)
                self._view = self._fit()
                self._schedule_commit()
                self.update()
            return
        super().keyPressEvent(e)

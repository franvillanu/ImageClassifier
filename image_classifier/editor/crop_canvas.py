"""Recortar canvas: the crop frame is the tool, the image stays where it is.

Everything is drawn with one QTransform (proxy pixels -> source -> oriented ->
screen), so straightening, panning and zooming never resample pixels per frame.
Gestures produce new ``EditState`` values through the closed-form functions in
``geometry.py``; the canvas never owns the truth, the editor does.

Interaction:
  * drag a handle            -> resize the frame
  * drag inside the frame    -> move the frame over the image
  * drag just outside it     -> straighten (rotate the image about the frame)
  * drag further out         -> pan the view (middle button pans anywhere)
  * wheel / zoom buttons     -> zoom the view about the cursor (crop unchanged)
  * arrow keys               -> nudge the frame (Shift: 10 px)

View policy: the view never jumps. While the view is "fitted" it keeps the
whole rotated image visible (straightening zooms out smoothly); once the user
zooms or pans, the zoom is left alone and straightening rotates the image about
the frame centre.
"""
from __future__ import annotations

import math

import cv2
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt6.QtWidgets import QWidget

from image_classifier.editor import geometry as g
from image_classifier.editor.qtimage import rgba_to_qimage
from image_classifier.editor.state import CropGeometry, EditState
from image_classifier.editor.widgets import ui_font

CORNER_HIT = 20
EDGE_HIT = 12
ROTATE_BAND = 56  # px outside the frame where dragging straightens
MARGIN = 24
MAX_ZOOM = 8.0  # physical screen px per source px
_rotate_cursor = None


def rotate_cursor():
    """Curved double arrow in the app's halo style."""
    global _rotate_cursor
    if _rotate_cursor is None:
        from PyQt6.QtGui import QCursor, QPixmap
        scale = 2
        pm = QPixmap(32 * scale, 32 * scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(scale, scale)
        path = QPainterPath()
        path.arcMoveTo(QRectF(6, 6, 20, 20), 200)
        path.arcTo(QRectF(6, 6, 20, 20), 200, -220)
        start, end = path.pointAtPercent(0), path.pointAtPercent(1)
        for color, width in ((QColor(0, 0, 0), 4.5), (QColor(255, 255, 255), 2.0)):
            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.drawPolyline([start + QPointF(-1, -5), start, start + QPointF(5, -1)])
            p.drawPolyline([end + QPointF(-5, -1), end, end + QPointF(1, -5)])
        p.end()
        pm.setDevicePixelRatio(scale)
        _rotate_cursor = QCursor(pm, 16, 16)
    return _rotate_cursor

_CURSORS = {
    "top_left": Qt.CursorShape.SizeFDiagCursor,
    "bottom_right": Qt.CursorShape.SizeFDiagCursor,
    "top_right": Qt.CursorShape.SizeBDiagCursor,
    "bottom_left": Qt.CursorShape.SizeBDiagCursor,
    "left": Qt.CursorShape.SizeHorCursor,
    "right": Qt.CursorShape.SizeHorCursor,
    "top": Qt.CursorShape.SizeVerCursor,
    "bottom": Qt.CursorShape.SizeVerCursor,
    "move": Qt.CursorShape.SizeAllCursor,
    "pan": Qt.CursorShape.OpenHandCursor,
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


def follow_crop(view: g.View, old: CropGeometry, new: CropGeometry) -> g.View:
    """Same zoom, ``new``'s centre shown where ``old``'s centre was, rotated to ``new.angle``."""
    return g.View((new.cx, new.cy), view.to_screen((old.cx, old.cy)), view.zoom, new.angle)


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
    userZoomed = pyqtSignal()  # the user zoomed (wheel); the editor flashes the zoom level
    acceptRequested = pyqtSignal()  # double-click inside the frame = Done
    # straighten by dragging outside the frame; the editor treats it like the ruler
    rotateStarted = pyqtSignal()
    rotateChanged = pyqtSignal(float)
    rotateFinished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._levels: list[tuple[QImage, float, float]] = []
        self._bg = QColor(0, 0, 0)
        self._insets = (0, 0, 0, 0)  # left, top, right, bottom kept free for floating controls
        self._state: EditState | None = None
        self._view: g.View | None = None
        self._fitted = True
        self._gesture = None
        self._grid = None  # None | "thirds" | "fine"
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

    def set_state(self, state: EditState, *, view: str = "keep"):
        """Show ``state``. ``view``: "keep" follows the frame without jumping, "fit" shows the whole image."""
        old_state, old_view = self._state, self._view
        self._state = state
        if not (self._gesture and self._gesture["kind"] == "rotate"):  # rotating drives this very call
            self._gesture = None
        if view == "fit" or old_view is None or old_state is None \
                or old_state.orientation != state.orientation:
            self._fitted = True
        if self._fitted:
            self._view = self._fit_view()
        else:
            self._view = follow_crop(old_view, old_state.crop, state.crop)
        self._emit_zoom()
        self.update()

    def fit(self):
        self._fitted = True
        self._view = self._fit_view()
        self._emit_zoom()
        self.update()

    def set_background(self, color: QColor):
        self._bg = QColor(color)
        self.update()

    def set_insets(self, left: int, top: int, right: int, bottom: int):
        if (left, top, right, bottom) != self._insets:
            self._insets = (left, top, right, bottom)
            if self._fitted:
                self.fit()

    def set_grid(self, grid: str | None):
        self._grid = grid
        self.update()

    def _bounds(self):
        return self._state.oriented_size

    def _fit_view(self) -> g.View | None:
        if self._state is None or self.width() < 10 or self.height() < 10:
            return None
        l, t, r, b = self._insets
        viewport = (l, t, max(10, self.width() - l - r), max(10, self.height() - t - b))
        return g.fit_image_view(self._bounds(), self._state.crop.angle, viewport, MARGIN)

    def _emit_zoom(self):
        if self._view is not None:
            self.zoomChanged.emit(self._view.zoom * self.devicePixelRatioF())

    def _apply(self, crop: CropGeometry, committed: bool):
        """Update the crop from a gesture; the view stays exactly where it is."""
        self._state = self._state.with_crop(crop)
        self.stateEdited.emit(self._state, committed)
        self.update()

    # ------------------------------------------------------------------ zoom API
    def zoom_by(self, factor: float, anchor_screen: QPointF | None = None):
        """Zoom the view about ``anchor_screen`` (default: the frame centre). The crop is not touched."""
        if self._state is None or self._view is None:
            return
        v = self._view
        fit = self._fit_view()
        lo = fit.zoom * 0.5 if fit else 1e-4
        hi = max(MAX_ZOOM / self.devicePixelRatioF(), fit.zoom if fit else 0)
        z = max(lo, min(hi, v.zoom * factor))
        if fit is not None and factor < 1 and z <= fit.zoom * 1.0001 <= v.zoom * 1.0001:
            self.fit()  # zooming out snaps back to "whole image"
            return
        if anchor_screen is None:
            fx, fy, fw, fh = v.frame_rect(self._state.crop)
            anchor = (fx + fw / 2.0, fy + fh / 2.0)
        else:
            anchor = (anchor_screen.x(), anchor_screen.y())
        p = v.to_image(anchor)
        self._view = g.View(p, anchor, z, v.angle)
        self._fitted = False
        self._emit_zoom()
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
        need = view.zoom * self.devicePixelRatioF()
        best = self._levels[0]
        for lvl in self._levels:
            if 1.0 / lvl[1] >= need * 0.999:
                best = lvl
        return best

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        st, view = self._state, self._view
        if st is None or view is None or not self._levels:
            p.end()
            return
        img, sx, sy = self._pick_level(view)
        m = g.orientation_matrix(st.orientation, st.source_size)
        t_scale = QTransform(sx, 0, 0, sy, 0, 0)
        t_orient = QTransform(m[0][0], m[1][0], m[0][1], m[1][1], m[0][2], m[1][2])
        # Smooth sampling but no Antialiasing hint: AA on a transformed image doubles the
        # cost for a 1-physical-pixel edge nobody can see. Same for the dim path below.
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setTransform(t_scale * t_orient * _view_transform(view))
        p.drawImage(0, 0, img)
        p.resetTransform()

        fx, fy, fw, fh = view.frame_rect(st.crop)
        frame = QRectF(fx, fy, fw, fh)
        # Dim the image outside the frame (not the canvas, which stays the window colour).
        W, H = st.oriented_size
        image = QPainterPath()
        image.addPolygon(QPolygonF([QPointF(*view.to_screen(c)) for c in ((0, 0), (W, 0), (W, H), (0, H))]))
        image.closeSubpath()
        frame_path = QPainterPath()
        frame_path.addRect(frame)
        p.fillPath(image.subtracted(frame_path), QColor(0, 0, 0, 150))

        if self._grid:
            self._paint_grid(p, frame)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(frame.adjusted(0, 0, -1, -1))
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_handles(p, frame)
        if self._gesture is not None or self._grid:
            self._paint_size(p, frame)
        p.end()

    def _paint_grid(self, p: QPainter, f: QRectF):
        n = 9 if self._grid == "fine" else 3
        for i in range(1, n):
            major = self._grid == "thirds" or i % 3 == 0
            p.setPen(QPen(QColor(255, 255, 255, 120 if major else 50), 1))
            x = f.left() + f.width() * i / n
            y = f.top() + f.height() * i / n
            p.drawLine(QPointF(x, f.top()), QPointF(x, f.bottom()))
            p.drawLine(QPointF(f.left(), y), QPointF(f.right(), y))

    def _paint_handles(self, p: QPainter, f: QRectF):
        """Windows-style handles: square L brackets at the corners, short bars on the edges."""
        L = min(20.0, f.width() / 3.0, f.height() / 3.0)
        T = 3.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        l, t, r, b = f.left(), f.top(), f.right(), f.bottom()
        for x, y, dx, dy in ((l, t, 1, 1), (r, t, -1, 1), (l, b, 1, -1), (r, b, -1, -1)):
            ox = x - (T if dx > 0 else 0)  # bracket sits just outside the frame line
            oy = y - (T if dy > 0 else 0)
            p.drawRect(QRectF(ox if dx > 0 else x - L, oy, L + T, T))
            p.drawRect(QRectF(ox, oy if dy > 0 else y - L, T, L + T))
        half = 10.0
        cx, cy = f.center().x(), f.center().y()
        if f.width() > 6 * half:
            p.drawRect(QRectF(cx - half, t - T, 2 * half, T))
            p.drawRect(QRectF(cx - half, b, 2 * half, T))
        if f.height() > 6 * half:
            p.drawRect(QRectF(l - T, cy - half, T, 2 * half))
            p.drawRect(QRectF(r, cy - half, T, 2 * half))

    def _paint_size(self, p: QPainter, f: QRectF):
        w, h = self._state.output_size
        text = f"{w} x {h}"
        p.setFont(ui_font(14))
        tw = p.fontMetrics().horizontalAdvance(text) + 20
        th = 28
        x = f.center().x() - tw / 2
        y = f.bottom() - th - 10 if f.height() > th * 3 else f.bottom() + 12
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(45, 45, 45, 235))
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
        if l < x < r and t < y < b:
            return "move"
        if l - ROTATE_BAND <= x <= r + ROTATE_BAND and t - ROTATE_BAND <= y <= b + ROTATE_BAND:
            return "rotate"
        return "pan"

    # ------------------------------------------------------------------ events
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fitted or self._view is None:
            self.fit()
        else:
            old = e.oldSize()
            if old.width() > 0 and old.height() > 0:
                v = self._view
                dx = (self.width() - old.width()) / 2.0
                dy = (self.height() - old.height()) / 2.0
                self._view = g.View(v.focus, (v.center[0] + dx, v.center[1] + dy), v.zoom, v.angle)

    def mousePressEvent(self, e):
        if self._state is None or self._view is None:
            return
        if e.button() == Qt.MouseButton.MiddleButton:
            kind = "pan"
        elif e.button() == Qt.MouseButton.LeftButton:
            kind = self._hit(e.position())
        else:
            return
        self._commit_pending()
        self._gesture = {"kind": kind, "start": self._state, "pos": e.position(), "view": self._view,
                         "button": e.button()}
        if kind == "pan":
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif kind == "rotate":
            fx, fy, fw, fh = self._view.frame_rect(self._state.crop)
            self._gesture["pivot"] = QPointF(fx + fw / 2.0, fy + fh / 2.0)
            self.rotateStarted.emit()
        else:
            self._grid = "thirds"
        self.update()

    def mouseMoveEvent(self, e):
        gst = self._gesture
        if gst is None:
            self._set_hover_cursor(e.position())
            return
        start: EditState = gst["start"]
        view: g.View = gst["view"]
        d = e.position() - gst["pos"]
        bounds = start.oriented_size
        kind = gst["kind"]
        if kind == "pan":
            self._view = g.View(view.focus, (view.center[0] + d.x(), view.center[1] + d.y()),
                                view.zoom, view.angle)
            self._fitted = False
            self.update()
        elif kind == "rotate":
            pivot = gst["pivot"]
            a0 = math.atan2(gst["pos"].y() - pivot.y(), gst["pos"].x() - pivot.x())
            a1 = math.atan2(e.position().y() - pivot.y(), e.position().x() - pivot.x())
            delta = math.degrees(math.atan2(math.sin(a1 - a0), math.cos(a1 - a0)))
            angle = max(-45.0, min(45.0, start.crop.angle + delta))
            angle = 0.0 if abs(angle) < 0.3 else round(angle, 1)
            self.rotateChanged.emit(angle)
        elif kind == "move":
            dx, dy = view.delta_to_image((d.x(), d.y()))
            moved = CropGeometry(start.crop.cx + dx, start.crop.cy + dy, start.crop.w, start.crop.h,
                                 start.crop.angle)
            self._apply(g.clamp_center(moved, bounds), False)
        else:
            aspect = start.aspect
            if aspect is None and e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                aspect = start.crop.w / start.crop.h
            crop = g.resize_handle(start.crop, kind, (d.x() / view.zoom, d.y() / view.zoom), aspect, bounds)
            self._apply(crop, False)

    def mouseReleaseEvent(self, e):
        gst = self._gesture
        if gst is None or e.button() != gst["button"]:
            return
        self._gesture = None
        self._set_hover_cursor(e.position())
        if gst["kind"] == "rotate":
            self.rotateFinished.emit()
            return
        self._grid = None
        if self._state != gst["start"]:
            self.stateEdited.emit(self._state, True)
        self.update()

    def _set_hover_cursor(self, pos: QPointF):
        kind = self._hit(pos)
        self.setCursor(rotate_cursor() if kind == "rotate" else _CURSORS[kind])

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._hit(e.position()) == "move":
            self.acceptRequested.emit()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps:
            self.zoom_by(1.15 ** steps, e.position())
            self.userZoomed.emit()
        e.accept()

    def keyPressEvent(self, e):
        if self._state is None or self._view is None:
            return super().keyPressEvent(e)
        step = 10.0 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if e.key() in moves:
            dx, dy = self._view.delta_to_image(moves[e.key()])
            c = self._state.crop
            crop = g.clamp_center(CropGeometry(c.cx + dx, c.cy + dy, c.w, c.h, c.angle), self._bounds())
            if crop != c:
                self._apply(crop, False)
                self._schedule_commit()
            return
        super().keyPressEvent(e)

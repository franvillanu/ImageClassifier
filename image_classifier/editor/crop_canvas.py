"""Recortar canvas: the crop frame stays put, the image moves underneath.

Everything is drawn with one QTransform (proxy pixels -> source -> oriented ->
screen), so straightening, panning and zooming never resample pixels per frame.
Gestures produce new ``EditState`` values through the closed-form functions in
``geometry.py``; the canvas never owns the truth, the editor does.

View policy: the view never jumps on its own. Resizing the frame moves only
the frame; panning, zooming and straightening keep the frame where it is on
screen. The view is refitted only on request (``fit``) or when the editor
replaces the state wholesale (rotate, flip, aspect, undo, reset, resize).
"""
from __future__ import annotations

import math

import cv2
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QTransform
from PyQt6.QtWidgets import QWidget

from image_classifier.editor import geometry as g
from image_classifier.editor.qtimage import rgba_to_qimage
from image_classifier.editor.state import CropGeometry, EditState

CORNER_HIT = 20
EDGE_HIT = 12
MARGIN = 48

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


def keep_frame(view: g.View, old: CropGeometry, new: CropGeometry) -> g.View:
    """View that shows ``new`` in the same on-screen frame rectangle ``old`` had."""
    fx, fy, fw, fh = view.frame_rect(old)
    z = min(fw / new.w, fh / new.h)
    return g.View((new.cx, new.cy), (fx + fw / 2.0, fy + fh / 2.0), z, new.angle)


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
        self._levels: list[tuple[QImage, float, float]] = []
        self._state: EditState | None = None
        self._view: g.View | None = None
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
        """Show ``state``. ``view``: "keep" holds the frame on screen, "fit" recentres it."""
        old_state, old_view = self._state, self._view
        self._state = state
        self._gesture = None
        if view == "keep" and old_view is not None and old_state is not None \
                and old_state.orientation == state.orientation:
            self._view = keep_frame(old_view, old_state.crop, state.crop)
        else:
            self._view = self._fit()
        self._emit_zoom()
        self.update()

    def fit(self):
        self._view = self._fit()
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

    def _apply(self, crop: CropGeometry, committed: bool, *, hold_frame: bool = True):
        """Update the crop from a gesture; optionally keep the frame fixed on screen."""
        old = self._state
        new = old.with_crop(crop)
        if hold_frame and self._view is not None:
            self._view = keep_frame(self._view, old.crop, crop)
            self._emit_zoom()
        self._state = new
        self.stateEdited.emit(new, committed)
        self.update()

    # ------------------------------------------------------------------ zoom API
    def zoom_by(self, factor: float, anchor_screen: QPointF | None = None):
        if self._state is None or self._view is None:
            return
        anchor = None if anchor_screen is None else self._view.to_image((anchor_screen.x(), anchor_screen.y()))
        crop = g.zoom(self._state.crop, factor, anchor, self._bounds())
        if crop != self._state.crop:
            self._apply(crop, False)
            self._schedule_commit()

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
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(QRectF(self.rect()))
        path.addRect(frame)
        p.fillPath(path, QColor(28, 28, 28, 170))

        if self._grid:
            self._paint_grid(p, frame)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(QPen(QColor(255, 255, 255, 220), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(frame)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._paint_handles(p, frame)
        if self._gesture is not None or self._grid:
            self._paint_size(p, frame)
        p.end()

    def _paint_grid(self, p: QPainter, f: QRectF):
        n = 9 if self._grid == "fine" else 3
        for i in range(1, n):
            major = self._grid == "thirds" or i % 3 == 0
            p.setPen(QPen(QColor(255, 255, 255, 110 if major else 45), 1))
            x = f.left() + f.width() * i / n
            y = f.top() + f.height() * i / n
            p.drawLine(QPointF(x, f.top()), QPointF(x, f.bottom()))
            p.drawLine(QPointF(f.left(), y), QPointF(f.right(), y))

    def _paint_handles(self, p: QPainter, f: QRectF):
        """Windows-style handles: rounded L brackets at the corners, short bars on the edges."""
        L, T = 22.0, 4.0
        pen = QPen(QColor(255, 255, 255), T, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        o = T / 2.0  # draw just outside the frame line
        l, t, r, b = f.left() - o, f.top() - o, f.right() + o, f.bottom() + o
        for x, y, dx, dy in ((l, t, 1, 1), (r, t, -1, 1), (l, b, 1, -1), (r, b, -1, -1)):
            path = QPainterPath(QPointF(x + dx * L, y))
            path.lineTo(QPointF(x, y))
            path.lineTo(QPointF(x, y + dy * L))
            p.drawPath(path)
        cx, cy = f.center().x(), f.center().y()
        half = L / 2.0
        if f.width() > 4 * L:
            p.drawLine(QPointF(cx - half, t), QPointF(cx + half, t))
            p.drawLine(QPointF(cx - half, b), QPointF(cx + half, b))
        if f.height() > 4 * L:
            p.drawLine(QPointF(l, cy - half), QPointF(l, cy + half))
            p.drawLine(QPointF(r, cy - half), QPointF(r, cy + half))

    def _paint_size(self, p: QPainter, f: QRectF):
        w, h = self._state.output_size
        text = f"{w} × {h}"
        font = QFont(self.font())
        font.setPixelSize(12)
        p.setFont(font)
        tw = p.fontMetrics().horizontalAdvance(text) + 18
        th = 24
        x = f.center().x() - tw / 2
        y = f.bottom() - th - 14 if f.height() > th * 3 else f.bottom() + 12
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(32, 32, 32, 230))
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
            self.fit()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._state is None or self._view is None:
            return
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
            crop = g.pan(start.crop, view.delta_to_image((-d.x(), -d.y())), bounds)
            self._view = keep_frame(view, start.crop, crop)
            self._apply(crop, False, hold_frame=False)
        else:
            aspect = start.aspect
            if aspect is None and e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                aspect = start.crop.w / start.crop.h
            crop = g.resize_handle(start.crop, gst["kind"], (d.x() / view.zoom, d.y() / view.zoom),
                                   aspect, bounds)
            self._view = view  # the view stays still; only the frame moves
            self._apply(crop, False, hold_frame=False)

    def mouseReleaseEvent(self, e):
        gst = self._gesture
        if gst is None or e.button() != Qt.MouseButton.LeftButton:
            return
        self._gesture = None
        self._grid = None
        self.setCursor(_CURSORS.get(self._hit(e.position()), Qt.CursorShape.OpenHandCursor))
        if self._state != gst["start"]:
            self.stateEdited.emit(self._state, True)
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
            # The arrow moves the image, so the crop moves the opposite way.
            crop = g.pan(self._state.crop, self._view.delta_to_image((-dx, -dy)), self._bounds())
            if crop != self._state.crop:
                self._apply(crop, False)
                self._schedule_commit()
            return
        super().keyPressEvent(e)

"""Ajuste canvas: shows the rendered result, fit-to-window by default, zoom and pan."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QWidget

MARGIN = 32
MIN_ZOOM, MAX_ZOOM = 0.02, 16.0


class AdjustCanvas(QWidget):
    zoomChanged = pyqtSignal(float)  # physical screen pixels per output pixel
    userZoomed = pyqtSignal()  # the user zoomed (wheel, double-click)
    strokeFinished = pyqtSignal(object, float)  # SPEC-005: brush path (output px) and radius (output px)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._image: QImage | None = None
        self._size = (1, 1)  # logical (full-resolution) size the image represents
        self._compare: tuple[QImage, tuple[int, int]] | None = None
        self._compare_zoom: float | None = None
        self._compare_focus: tuple[float, float] | None = None
        self._zoom: float | None = None  # None = fit
        self._center = QPointF(0.5, 0.5)  # view centre in normalised image coords
        self._drag = None
        self._bg = QColor(0, 0, 0)
        self._insets = (0, 0, 0, 0)  # left, top, right, bottom kept free for floating controls
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._brush = False  # SPEC-005: remove-object brush
        self._brush_px = 40.0  # brush diameter on screen
        self._stroke: list[QPointF] | None = None  # screen points of the stroke being painted
        self._pending: list[tuple[list, float]] = []  # finished strokes still being filled in (output px)
        self._hover: QPointF | None = None
        self._pan = None

    # ------------------------------------------------------------------ remove-object brush (SPEC-005)
    def set_brush(self, on: bool):
        self._brush = on
        self._stroke = None
        self._pending.clear()
        self._hover = None
        self.setMouseTracking(on)
        self.setCursor(Qt.CursorShape.BlankCursor if on else Qt.CursorShape.OpenHandCursor)
        self.update()

    def brush_active(self) -> bool:
        return self._brush

    def set_brush_size(self, diameter_px: float):
        self._brush_px = float(diameter_px)
        self.update()

    def is_waiting(self) -> bool:
        """True while painted strokes are still being filled in by the render worker."""
        return bool(self._pending)

    def _to_output(self, pt: QPointF) -> tuple[float, float]:
        rect, z = self.image_rect(), self.zoom()
        return ((pt.x() - rect.x()) / z, (pt.y() - rect.y()) / z)

    def _finish_stroke(self):
        pts, self._stroke = self._stroke, None
        if not pts:
            return
        radius = self._brush_px / 2.0 / self.zoom()
        path = [self._to_output(p) for p in pts]
        self._pending.append((path, radius))
        self.update()
        self.strokeFinished.emit(path, radius)

    def set_background(self, color: QColor):
        self._bg = QColor(color)
        self.update()

    def set_insets(self, left: int, top: int, right: int, bottom: int):
        self._insets = (left, top, right, bottom)
        self._emit_zoom()
        self.update()

    def _area(self) -> QRectF:
        l, t, r, b = self._insets
        return QRectF(l, t, max(10, self.width() - l - r), max(10, self.height() - t - b))

    def set_image(self, image: QImage, size: tuple[int, int]):
        if size != self._size:
            self._zoom = None
            self._center = QPointF(0.5, 0.5)
        self._image, self._size = image, size
        self._pending.clear()
        self._emit_zoom()
        self.update()

    def set_compare(self, compare: tuple[QImage, tuple[int, int]] | None, zoom: float | None = None,
                    focus: tuple[float, float] | None = None):
        """Show ``compare`` (image, size) instead of the edit, at ``zoom`` (the edit's screen scale).

        Keeping the scale means the original is drawn at its true size next to what you were
        looking at, instead of being refitted (and shrunk) to the window. ``focus`` is the point
        of ``compare`` (in its ``size`` units) drawn at ``area_center()``; None centres it.
        """
        self._compare_zoom = zoom if compare is not None else None
        self._compare_focus = focus if compare is not None else None
        self._compare = compare
        self._emit_zoom()
        self.update()

    def _shown(self):
        if self._compare is not None:
            return self._compare
        return (self._image, self._size) if self._image is not None else (None, (1, 1))

    def _fit_zoom(self, size) -> float:
        w, h = size
        a = self._area()
        return max(1e-6, min((a.width() - 2 * MARGIN) / w, (a.height() - 2 * MARGIN) / h))

    def zoom(self) -> float:
        _, size = self._shown()
        if self._compare is not None:
            return self._compare_zoom or self._fit_zoom(size)
        return self._fit_zoom(size) if self._zoom is None else self._zoom

    def display_scale(self, size: tuple[int, int]) -> float:
        """Physical screen pixels per output pixel an image of ``size`` would be shown at."""
        z = self._fit_zoom(size) if self._zoom is None else self._zoom
        return z * self.devicePixelRatioF()

    def _emit_zoom(self):
        self.zoomChanged.emit(self.zoom() * self.devicePixelRatioF())

    def fit(self):
        self._zoom = None
        self._center = QPointF(0.5, 0.5)
        self._emit_zoom()
        self.update()

    def zoom_by(self, factor: float, anchor: QPointF | None = None):
        if self._image is None:
            return
        old = self.zoom()
        new = max(MIN_ZOOM, min(MAX_ZOOM, old * factor))
        fit = self._fit_zoom(self._size)
        if new <= fit * 1.0001 and factor < 1:
            self.fit()
            return
        if anchor is not None:
            # keep the image point under the cursor fixed
            w, h = self._size
            mid = self._area().center()
            ax = (anchor.x() - mid.x()) / (old * w)
            ay = (anchor.y() - mid.y()) / (old * h)
            self._center = QPointF(self._center.x() + ax * (1 - old / new),
                                   self._center.y() + ay * (1 - old / new))
        self._zoom = new
        self._clamp_center()
        self._emit_zoom()
        self.update()

    def _clamp_center(self):
        w, h = self._size
        z = self.zoom()
        half_x = self.width() / (2 * z * w)
        half_y = self.height() / (2 * z * h)
        cx = 0.5 if half_x >= 0.5 else min(1 - half_x, max(half_x, self._center.x()))
        cy = 0.5 if half_y >= 0.5 else min(1 - half_y, max(half_y, self._center.y()))
        self._center = QPointF(cx, cy)

    def area_center(self) -> QPointF:
        """Screen point at the centre of the view area (the zoom/pan anchor)."""
        return self._area().center()

    def view_center(self) -> QPointF:
        """Normalised point of the edit shown at ``area_center()``."""
        return QPointF(0.5, 0.5) if self._zoom is None else QPointF(self._center)

    def image_rect(self) -> QRectF:
        """Screen rect the shown image (edit or compare) is drawn in."""
        _, size = self._shown()
        z = self.zoom()
        w, h = size[0] * z, size[1] * z
        mid = self.area_center()
        if self._compare is not None and self._compare_focus is not None:
            fx, fy = self._compare_focus  # SPEC-004 ED-1: keep the same source point under the centre
            return QRectF(mid.x() - fx * z, mid.y() - fy * z, w, h)
        center = QPointF(0.5, 0.5) if self._compare is not None else self.view_center()
        return QRectF(mid.x() - center.x() * w, mid.y() - center.y() * h, w, h)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        image, _ = self._shown()
        if image is not None and not image.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(self.image_rect(), image, QRectF(image.rect()))
        if self._brush:
            self._paint_brush(p)
        p.end()

    def _paint_brush(self, p: QPainter):
        """Red translucent strokes (finished-but-filling and current) and the round brush cursor."""
        rect, z = self.image_rect(), self.zoom()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        red = QColor(255, 60, 60, 110)
        strokes = [([QPointF(rect.x() + x * z, rect.y() + y * z) for x, y in path], r * z * 2)
                   for path, r in self._pending]
        if self._stroke:
            strokes.append((self._stroke, self._brush_px))
        for pts, width in strokes:
            pen = QPen(red, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            if len(pts) == 1:
                p.drawPoint(pts[0])
            else:
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)
        if self._hover is not None:
            r = self._brush_px / 2.0
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 170), 3))
            p.drawEllipse(self._hover, r, r)
            p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
            p.drawEllipse(self._hover, r, r)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._clamp_center()
        self._emit_zoom()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps:
            self.zoom_by(1.15 ** steps, e.position())
            self.userZoomed.emit()
        e.accept()

    def mousePressEvent(self, e):
        self._hover = e.position()
        if self._brush and e.button() == Qt.MouseButton.LeftButton:
            self._stroke = [e.position()]
            self.update()
        elif e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton)                 and self._zoom is not None:
            self._drag = (e.position(), QPointF(self._center))
            if not self._brush:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._brush:
            self._hover = e.position()
        if self._stroke is not None:
            last = self._stroke[-1]
            d = e.position() - last
            if d.x() ** 2 + d.y() ** 2 >= max(2.0, self._brush_px / 6.0) ** 2:
                self._stroke.append(e.position())
            self.update()
            return
        if self._drag is None:
            if self._brush:
                self.update()
            return
        start, center = self._drag
        d = e.position() - start
        z = self.zoom()
        self._center = QPointF(center.x() - d.x() / (z * self._size[0]),
                               center.y() - d.y() / (z * self._size[1]))
        self._clamp_center()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        if self._stroke is not None and e.button() == Qt.MouseButton.LeftButton:
            if e.position() != self._stroke[-1]:
                self._stroke.append(e.position())
            self._finish_stroke()
            return
        self._drag = None
        self.setCursor(Qt.CursorShape.BlankCursor if self._brush else Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, e):
        if self._zoom is None:
            self.zoom_by(1.0 / max(1e-6, self.zoom() * self.devicePixelRatioF()), e.position())  # 100 %
        else:
            self.fit()
        self.userZoomed.emit()

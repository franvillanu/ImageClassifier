"""Ajuste canvas: shows the rendered result, fit-to-window by default, zoom and pan."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QWidget

MARGIN = 32
MIN_ZOOM, MAX_ZOOM = 0.02, 16.0


class AdjustCanvas(QWidget):
    zoomChanged = pyqtSignal(float)  # physical screen pixels per output pixel
    userZoomed = pyqtSignal()  # the user zoomed (wheel, double-click)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._image: QImage | None = None
        self._size = (1, 1)  # logical (full-resolution) size the image represents
        self._compare: tuple[QImage, tuple[int, int]] | None = None
        self._zoom: float | None = None  # None = fit
        self._center = QPointF(0.5, 0.5)  # view centre in normalised image coords
        self._drag = None
        self._bg = QColor(0, 0, 0)
        self._insets = (0, 0, 0, 0)  # left, top, right, bottom kept free for floating controls
        self.setCursor(Qt.CursorShape.OpenHandCursor)

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
        self._emit_zoom()
        self.update()

    def set_compare(self, compare: tuple[QImage, tuple[int, int]] | None):
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
        return self._fit_zoom(size) if self._zoom is None or self._compare is not None else self._zoom

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

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        image, size = self._shown()
        if image is not None and not image.isNull():
            z = self.zoom()
            w, h = size[0] * z, size[1] * z
            center = (QPointF(0.5, 0.5) if self._compare is not None or self._zoom is None else self._center)
            mid = self._area().center()
            x = mid.x() - center.x() * w
            y = mid.y() - center.y() * h
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(QRectF(x, y, w, h), image, QRectF(image.rect()))
        p.end()

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
        if e.button() == Qt.MouseButton.LeftButton and self._zoom is not None:
            self._drag = (e.position(), QPointF(self._center))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        start, center = self._drag
        d = e.position() - start
        z = self.zoom()
        self._center = QPointF(center.x() - d.x() / (z * self._size[0]),
                               center.y() - d.y() / (z * self._size[1]))
        self._clamp_center()
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None
        self._bg = QColor(0, 0, 0)
        self._insets = (0, 0, 0, 0)  # left, top, right, bottom kept free for floating controls
        self.setCursor(Qt.CursorShape.OpenHandCursor)

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

    def mouseDoubleClickEvent(self, e):
        if self._zoom is None:
            self.zoom_by(1.0 / max(1e-6, self.zoom() * self.devicePixelRatioF()), e.position())  # 100 %
        else:
            self.fit()
        self.userZoomed.emit()

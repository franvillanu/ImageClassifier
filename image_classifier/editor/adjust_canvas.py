"""Ajuste canvas: shows the rendered result, fit-to-window by default, zoom and pan."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QWidget

MARGIN = 32
MIN_ZOOM, MAX_ZOOM = 0.02, 16.0


class AdjustCanvas(QWidget):
    zoomChanged = pyqtSignal(float)  # physical screen pixels per output pixel
    userZoomed = pyqtSignal()  # the user zoomed (wheel, double-click)
    strokeStarted = pyqtSignal()  # SPEC-005: the brush went down
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
        self._selection: list[tuple[list, float]] = []  # painted, not yet handed over (output px)
        self._pending: list[tuple[list, float]] = []  # handed over, being filled in (output px)
        self._busy_text = ""
        self._phase = 0.0
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(40)
        self._busy_timer.timeout.connect(self._tick)
        self._hover: QPointF | None = None
        self._pan = None

    # ------------------------------------------------------------------ remove-object brush (SPEC-005)
    def set_brush(self, on: bool):
        self._brush = on
        self._stroke = None
        self._selection.clear()
        self._clear_pending()
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

    def set_busy_text(self, text: str):
        self._busy_text = text

    def has_selection(self) -> bool:
        return bool(self._selection)

    def clear_selection(self):
        self._selection.clear()
        self.update()

    def take_selection(self) -> list:
        """Hand over everything painted so far as one removal: ``[(path, radius), ...]`` (output px).
        The area keeps pulsing, with the busy card, until the filled photo arrives (SPEC-005 RM-10)."""
        taken, self._selection = self._selection, []
        if taken:
            self._pending = taken
            self._phase = 0.0
            self._busy_timer.start()
        self.update()
        return taken

    def _clear_pending(self):
        self._pending.clear()
        self._busy_timer.stop()

    def _tick(self):
        self._phase += 0.2
        self.update()

    def _to_output(self, pt: QPointF) -> tuple[float, float]:
        rect, z = self.image_rect(), self.zoom()
        return ((pt.x() - rect.x()) / z, (pt.y() - rect.y()) / z)

    def _finish_stroke(self):
        pts, self._stroke = self._stroke, None
        if not pts:
            return
        radius = self._brush_px / 2.0 / self.zoom()
        path = [self._to_output(p) for p in pts]
        self._selection.append((path, radius))
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
        self._clear_pending()
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

    def _screen_path(self, strokes) -> QPainterPath:
        """One filled shape for all strokes (screen px, width = brush): overlaps add nothing (RM-9)."""
        union = QPainterPath()
        for pts, width in strokes:
            one = QPainterPath(pts[0])
            if len(pts) == 1:
                one.addEllipse(pts[0], width / 2.0, width / 2.0)
                union = union.united(one)
                continue
            for q in pts[1:]:
                one.lineTo(q)
            stroker = QPainterPathStroker()
            stroker.setWidth(width)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            union = union.united(stroker.createStroke(one))
        return union

    def _paint_brush(self, p: QPainter):
        """The painted area as one flat red tint, the busy card, and the round brush cursor."""
        rect, z = self.image_rect(), self.zoom()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        def screen(done):
            return [([QPointF(rect.x() + x * z, rect.y() + y * z) for x, y in path], r * z * 2) for path, r in done]

        waiting = self._screen_path(screen(self._pending)) if self._pending else None
        if waiting is not None:  # pulsing while the fill is worked out
            alpha = int(95 + 70 * (0.5 + 0.5 * math.sin(self._phase)))
            p.fillPath(waiting, QColor(255, 60, 60, alpha))
        mine = screen(self._selection) + ([(self._stroke, self._brush_px)] if self._stroke else [])
        if mine:
            p.fillPath(self._screen_path(mine), QColor(255, 60, 60, 110))
        if waiting is not None:
            self._paint_busy_card(p, waiting.boundingRect())
        if self._hover is not None:
            r = self._brush_px / 2.0
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 170), 3))
            p.drawEllipse(self._hover, r, r)
            p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
            p.drawEllipse(self._hover, r, r)

    def _paint_busy_card(self, p: QPainter, area: QRectF):
        """A card with a spinner and the message, centred on the painted area and kept inside the view."""
        font = QFont()
        font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        text_w = p.fontMetrics().horizontalAdvance(self._busy_text)
        w, h = text_w + 76, 52.0
        c = area.center()
        x = min(max(8.0, c.x() - w / 2), self.width() - w - 8.0)
        y = min(max(8.0, c.y() - h / 2), self.height() - h - 8.0)
        card = QRectF(x, y, w, h)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(20, 20, 23, 235))
        p.drawRoundedRect(card, 14, 14)
        spin = QRectF(card.left() + 16, card.center().y() - 11, 22, 22)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 50), 3))
        p.drawEllipse(spin)
        pen = QPen(QColor("#1a8cea"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(spin, int(-math.degrees(self._phase) * 16) % (360 * 16), 100 * 16)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(card.left() + 50, card.top(), text_w + 20, card.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._busy_text)

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
            self.strokeStarted.emit()
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

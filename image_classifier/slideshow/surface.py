"""OpenGL and raster surfaces sharing a single smooth QPainter composition."""
from PyQt6.QtCore import QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QWidget, QStackedLayout
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    QOpenGLWidget = None
from .motion import EFFECTS


def panned_bounds(bounds, pan, zoom=1.0, viewport=(0, 0)):
    """The motion's bounds with the user's view on top: zoom about the window centre (SPEC-002
    SZ-1), then pan, never more than half the drawn (zoomed) size (SP-2, SZ-4)."""
    x, y, w, h = bounds
    if zoom != 1.0:
        cx, cy = viewport[0] / 2, viewport[1] / 2
        x, y, w, h = cx + (x - cx) * zoom, cy + (y - cy) * zoom, w * zoom, h * zoom
    dx = max(-w / 2, min(w / 2, pan[0]))
    dy = max(-h / 2, min(h / 2, pan[1]))
    return x + dx, y + dy, w, h


def paint_slide(widget):
    painter = QPainter(widget)
    painter.fillRect(widget.rect(), Qt.GlobalColor.black)
    surface = widget.surface
    if surface.pixmap is not None and surface.entry is not None:
        frame = EFFECTS[surface.entry.effect_id].evaluate(
            surface.progress, (surface.pixmap.width(), surface.pixmap.height()),
            (widget.width(), widget.height()), surface.strength)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = frame.bounds
        if not surface.fade:  # SPEC-002 SE-1: fade only while playing, and a stopped slide at an end is not off screen
            painter.setOpacity(1.0)
            if surface.progress <= 0 or surface.progress >= 1:
                bounds = EFFECTS[surface.entry.effect_id].evaluate(
                    surface.progress, (surface.pixmap.width(), surface.pixmap.height()),
                    (widget.width(), widget.height()), 0).bounds  # strength 0: no zoom or offset, fitted and centred
        else:
            painter.setOpacity(frame.opacity)
        bounds = panned_bounds(bounds, surface.pan, surface.zoom, (widget.width(), widget.height()))
        painter.drawPixmap(QRectF(*bounds), surface.pixmap, QRectF(surface.pixmap.rect()))
    painter.end()
    surface.framePainted.emit()


class RasterSurface(QWidget):
    def paintEvent(self, event):
        paint_slide(self)


class GLSurface(QOpenGLWidget if QOpenGLWidget is not None else QWidget):
    def paintGL(self):
        paint_slide(self)


class SlideSurface(QWidget):
    fallbackActivated = pyqtSignal()
    framePainted = pyqtSignal()

    def __init__(self, parent=None, *, raster=False):
        super().__init__(parent)
        self.pixmap = None
        self._source = None
        self.rotation = 0
        self.pan = (0.0, 0.0)
        self.zoom = 1.0
        self.entry = None
        self.progress = 0
        self.fade = True
        self.strength = 100
        self._layout = QStackedLayout(self)
        self._layout.setContentsMargins(0,0,0,0)
        requested_raster = raster
        raster = raster or QOpenGLWidget is None
        try:
            self.canvas = RasterSurface(self) if raster else GLSurface(self)
        except RuntimeError:
            raster = True
            self.canvas = RasterSurface(self)
        self.canvas.surface = self
        self._layout.addWidget(self.canvas)
        self._checked = raster
        self._initial_fallback = raster and not requested_raster

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_fallback:
            self._initial_fallback = False
            self.fallbackActivated.emit()
        if not self._checked:
            QTimer.singleShot(100, self.check_context)

    def check_context(self):
        if self._checked:
            return
        self._checked = True
        if not self.canvas.isValid():
            old = self.canvas
            self.canvas = RasterSurface(self)
            self.canvas.surface = self
            self.canvas.setMouseTracking(True)
            self._layout.addWidget(self.canvas)
            self._layout.setCurrentWidget(self.canvas)
            old.hide()
            old.deleteLater()
            self.fallbackActivated.emit()

    def present(self, entry, frame, rotation=0):
        self.entry = entry
        self._source = QPixmap.fromImage(frame.image)
        self.rotation = rotation % 360
        self.pixmap = self._rotated(self._source)
        self.canvas.update()

    def set_rotation(self, rotation):
        """Display-only rotation in degrees clockwise (SPEC-002 SR-1/SR-3): the motion fits the
        rotated pixmap, so a turned landscape photo is fitted as portrait."""
        self.rotation = rotation % 360
        if self._source is not None:
            self.pixmap = self._rotated(self._source)
            self.canvas.update()

    def set_pan(self, pan):
        """Offset in logical pixels on top of the motion; the player animates it (SP-1)."""
        if pan != self.pan:
            self.pan = pan
            self.canvas.update()

    def set_zoom(self, zoom):
        """User zoom on top of the motion; the player animates it (SZ-1)."""
        if zoom != self.zoom:
            self.zoom = zoom
            self.canvas.update()

    def reset_pan(self):
        self.pan = (0.0, 0.0)
        self.zoom = 1.0

    def _rotated(self, pixmap):
        if not self.rotation:
            return pixmap
        return pixmap.transformed(QTransform().rotate(self.rotation), Qt.TransformationMode.SmoothTransformation)

    def refresh(self, progress, strength, fade=True):
        self.progress, self.strength, self.fade = progress, strength, fade
        self.canvas.update()

    def release(self):
        self.pixmap = None
        self._source = None
        self.entry = None

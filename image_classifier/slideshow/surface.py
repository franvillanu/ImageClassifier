"""OpenGL and raster surfaces sharing a single smooth QPainter composition."""
from PyQt6.QtCore import QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QWidget, QStackedLayout
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    QOpenGLWidget = None
from .motion import EFFECTS


def panned_bounds(bounds, pan):
    """Shift the motion's bounds by the user's pan, never more than half the drawn size (SPEC-002 SP-2)."""
    x, y, w, h = bounds
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
        painter.setOpacity(frame.opacity)
        painter.drawPixmap(QRectF(*panned_bounds(frame.bounds, surface.pan)), surface.pixmap, QRectF(surface.pixmap.rect()))
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
        self.entry = None
        self.progress = 0
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

    def pan_by(self, dx, dy):
        """Move the photo by (dx, dy) logical pixels on top of its motion (SP-1). The stored pan is
        kept within half the window so a long key repeat cannot build up an offset far past the clamp."""
        limit_x, limit_y = self.width() / 2, self.height() / 2
        self.pan = (max(-limit_x, min(limit_x, self.pan[0] + dx)), max(-limit_y, min(limit_y, self.pan[1] + dy)))
        self.canvas.update()

    def reset_pan(self):
        self.pan = (0.0, 0.0)

    def _rotated(self, pixmap):
        if not self.rotation:
            return pixmap
        return pixmap.transformed(QTransform().rotate(self.rotation), Qt.TransformationMode.SmoothTransformation)

    def refresh(self, progress, strength):
        self.progress, self.strength = progress, strength
        self.canvas.update()

    def release(self):
        self.pixmap = None
        self._source = None
        self.entry = None

"""OpenGL and raster surfaces sharing a single smooth QPainter composition."""
from PyQt6.QtCore import QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QWidget, QStackedLayout
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    QOpenGLWidget = None
from .motion import EFFECTS


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
        painter.drawPixmap(QRectF(*frame.bounds), surface.pixmap, QRectF(surface.pixmap.rect()))
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

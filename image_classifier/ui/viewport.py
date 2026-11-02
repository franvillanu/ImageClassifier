"""OpenGL helpers and the viewport used by the image viewer.
"""
from PyQt6.QtGui import QSurfaceFormat, QColorSpace
from PyQt6.QtOpenGLWidgets import QOpenGLWidget


# Multisampling (MSAA) makes every repaint several times more expensive, which
# shows at 4K. The photo is drawn with texture sampling and gains nothing from it.
# Set to 4 to restore the old behaviour. 0 disables it.
VIEWPORT_SAMPLES = 0


def _opengl():
    from OpenGL import GL

    return GL


class NearestViewport(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Ensure this widget uses sRGB color space for consistent rendering
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setVersion(3, 3)
        fmt.setSamples(VIEWPORT_SAMPLES)
        fmt.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        self.setFormat(fmt)

    def initializeGL(self):
        super().initializeGL()
        GL = _opengl()

        # 1) Nearest-neighbor for all texture sampling
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)

        # 2) Enable blending so smoothed primitives composite correctly
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        # 3) Line smoothing for divider/handles
        GL.glEnable(GL.GL_LINE_SMOOTH)
        GL.glHint(GL.GL_LINE_SMOOTH_HINT, GL.GL_NICEST)

        # Note: sRGB color space is handled automatically by Qt when set on QSurfaceFormat
        # No manual GL_FRAMEBUFFER_SRGB enable needed - Qt manages the conversion

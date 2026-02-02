import sys
import traceback
import datetime
import os
import json
import send2trash
import ctypes
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QMainWindow, QWidget, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QHBoxLayout, QScrollArea, QLayout, QDialog, QCheckBox,
    QRadioButton, QLineEdit, QSizePolicy, QSlider, QMenu, QGridLayout, QFrame, QProgressBar, QTabWidget, QGraphicsDropShadowEffect, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsOpacityEffect, QButtonGroup, QComboBox, QRubberBand, QListView, QProgressDialog,
    QStyledItemDelegate, QStyleOptionViewItem , QStyle, QStyleOptionSlider 
)
from PyQt6.QtGui import (
    QPixmap, QKeySequence, QShortcut, QWheelEvent, QMouseEvent, QCursor, QIcon,
    QPainter, QFont, QTransform, QColor, QImageReader, QGuiApplication, QImage, QVector3D, QPen, QKeyEvent, QBrush, QPalette, QOpenGLContext, QAction,
    QSurfaceFormat, QColorSpace
)
from PyQt6.QtCore import (
    Qt, QPoint, QTimer, QByteArray, QSize, QMimeData, QUrl, QObject, QEvent, QPropertyAnimation, QRect, QPointF, QEventLoop, QEasingCurve, pyqtSignal,
    QThread, QCoreApplication, QRect, QRectF, QRunnable, pyqtSlot, QThreadPool, QStandardPaths, QBuffer, QIODevice
)    
from PyQt6.QtSvg import QSvgRenderer
from PIL import Image, ImageQt, ImageFilter
from io import BytesIO
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLShaderProgram, QOpenGLShader, QOpenGLTexture, QOpenGLPaintDevice
from OpenGL import GL
from OpenGL.GL import (
    # --- texture / FBO ---
    glBindTexture, glTexImage2D, glTexParameteri, glGenTextures,
    glActiveTexture,
    # --- VAO / VBO ---
    glGenVertexArrays, glBindVertexArray,
    glGenBuffers, glBindBuffer, glBufferData,
    glVertexAttribPointer, glEnableVertexAttribArray,
    # --- draw + state ---
    glViewport, glClearColor, glClear,
    glDrawElements, glDrawArrays,
    glDisable,
    # --- scalar types for ctypes arrays ---
    GLfloat, GLuint,
    # --- enums / constants ---
    GL_TEXTURE_2D, GL_RGBA, GL_UNSIGNED_BYTE,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE0,
    GL_ARRAY_BUFFER, GL_ELEMENT_ARRAY_BUFFER,
    GL_STATIC_DRAW, GL_FLOAT, GL_FALSE, GL_UNSIGNED_INT,
    GL_TRIANGLES, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
    GL_NEAREST,
    # --- depth‐test / cull enums ---
    GL_DEPTH_TEST, GL_CULL_FACE,
)
# Windows Shell (COM + open in Explorer); imaging (sharpen, loader); config; workers; UI
from image_classifier.shell_win import open_folder_and_select_item
from image_classifier.imaging import sharpen_cv2, ImageLoaderRunnable, WorkerSignals
from image_classifier.config import get_config_file
from image_classifier.workers import ExportWorker, DeleteNonFavoritesWorker, SharpenThread
from image_classifier.ui import (
    IconFactory,
    BaseOverlay,
    AlternateComboBox,
    SortingBar,
    NoHighlightDelegate,
    DraggableContainer,
    OverlayComboBox,
    SmoothRotationSlider,
    MyDragOverlay,
    ALLOWED_EXTENSIONS,
    HelpDialog,
    TooltipEventFilter,
    LoadingKeyFilter,
    CustomTooltip,
    OverlayProgressDialog,
    EphemeralPopup,
    FloatingMenu,
)


def exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    crash_file = f"error_log_{timestamp}.txt"
    with open(crash_file, "w", encoding="utf-8") as f:
        f.write(error_message)
    path = os.path.abspath(crash_file)
    if current_language == "es":
        title = "Error"
        message = (
            "La aplicación dejó de funcionar de forma inesperada.\n\n"
            f"Se ha guardado un reporte del error en:\n\n{path}"
        )
    else:
        title = "Error"
        message = (
            "The application stopped working unexpectedly.\n\n"
            f"An error report has been saved to:\n\n{path}"
        )
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.critical(None, title, message)
    sys.exit(1)

sys.excepthook = exception_handler

# ------------------------------------------------------------------------
# Global Variables
# ------------------------------------------------------------------------

current_language = "en"
try:
    QApplication.setAttribute(
        Qt.ApplicationAttribute.EnableHighDpiScaling, True
    )
    QApplication.setAttribute(
        Qt.ApplicationAttribute.UseHighDpiPixmaps,    True
    )
except AttributeError:
    pass

fmt = QSurfaceFormat()
fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
fmt.setVersion(3, 3)
fmt.setSamples(16)   # 4× MSAA globally
# Set sRGB color space for consistent color rendering in fullscreen and windowed mode
fmt.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
QSurfaceFormat.setDefaultFormat(fmt)
# ------------------------------------------------------------------------
# Translations (localized: image_classifier/i18n/translations.py)
# ------------------------------------------------------------------------
try:
    from image_classifier.i18n.translations import translations
except ImportError:
    translations = {"en": {}, "es": {}}

class NearestViewport(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Ensure this widget uses sRGB color space for consistent rendering
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setVersion(3, 3)
        fmt.setSamples(16)
        fmt.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        self.setFormat(fmt)

    def initializeGL(self):
        super().initializeGL()

        # 1) Nearest-neighbor for all texture sampling
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)

        # 2) Enable multisampling (requires default format set globally)
        GL.glEnable(GL.GL_MULTISAMPLE)

        # 3) Enable blending so smoothed primitives composite correctly
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        # 4) Line smoothing for divider/handles
        GL.glEnable(GL.GL_LINE_SMOOTH)
        GL.glHint(GL.GL_LINE_SMOOTH_HINT, GL.GL_NICEST)

        # 5) Polygon smoothing for any 1-pixel quads
        GL.glEnable(GL.GL_POLYGON_SMOOTH)
        GL.glHint(GL.GL_POLYGON_SMOOTH_HINT, GL.GL_NICEST)

        # 6) Alpha-to-coverage so MSAA respects your alpha edges perfectly
        GL.glEnable(GL.GL_SAMPLE_ALPHA_TO_COVERAGE)
        
        # Note: sRGB color space is handled automatically by Qt when set on QSurfaceFormat
        # No manual GL_FRAMEBUFFER_SRGB enable needed - Qt manages the conversion


# ------------------------------------------------------------------------
# AdvancedGraphicsImageViewer
# ------------------------------------------------------------------------
class AdvancedGraphicsImageViewer(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.bg_color = "#000000"
        self.setStyleSheet(f"border: none; background-color: {self.bg_color};")
        self.setRenderHint(QPainter.RenderHint.Antialiasing) 
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setViewport(NearestViewport())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.pixmap_item.setCacheMode(QGraphicsPixmapItem.CacheMode.NoCache)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self.scene.addItem(self.pixmap_item)
        self.original_pixmap = None
        self.rotation_angle = 0
        self.brightness_factor = 1.0
        self.auto_fit = True
        self.zoom_factor = 1.0
        self.fit_zoom_factor = 1.0
        self.loader = None
        self.loading_dialog = None  

    def setImage(self, image_path, reset_zoom=True, preserve_zoom=False):
        import os
        from PyQt6.QtCore import QThreadPool

        # 0) Normalize here the same way the loader did:
        norm = os.path.normcase(os.path.abspath(image_path))

        # 1) Increment load counter & record path
        self.load_counter     = getattr(self, "load_counter", 0) + 1
        self.current_load_id  = self.load_counter
        self.current_loading_image = norm

        # 2) Cache-first: if we’ve already decoded full-res, skip threading
        cache = ImageLoaderRunnable._pixmap_cache
        if norm in cache:
            pix = cache[norm]
            # Call onImageLoaded directly (synchronous, <1 ms)
            self.onImageLoaded(pix, reset_zoom, preserve_zoom, self.current_load_id)
            return

        # 3) Otherwise cancel old loader and start a new one…
        if getattr(self, "loader", None):
            self.loader.cancel()
            self.loader = None

        window = self.window()
        window.image_loading = True

        worker = ImageLoaderRunnable(image_path)
        worker.signals.finished.connect(
            lambda pix, id=self.current_load_id:
                self.onImageLoaded(pix, reset_zoom, preserve_zoom, id)
        )
        worker.signals.error.connect(lambda err: print("Error loading image:", err))
        QThreadPool.globalInstance().start(worker)
        self.loader = worker

        # --- RESET BRIGHTNESS & COMPARE-MODE FOR NEW IMAGE ---
        # Nuke any old GPU texture so we rebuild it fresh
        self.cached_texture    = None
        # Reset brightness back to neutral
        self.brightness_factor = 1.0
        # If you have a brightness slider widget, reset its UI
        if hasattr(self, "brightness_slider"):
            self.brightness_slider.setValue(0)
        # Turn off split-view compare so no diagonal line
        self.compare_enabled   = False



    def _cancel_loader(self):
        """Safely cancel the image loader and close the overlay, if any."""
        if getattr(self, "loader", None) is not None:
            if self.loader.isRunning():
                try:
                    self.loader.terminate()
                    self.loader.wait()
                except Exception:
                    pass
            self.loader = None

        if getattr(self, "loading_dialog", None) is not None:
            self.loading_dialog.releaseKeyboard()
            self.loading_dialog.hide()
            self.loading_dialog.deleteLater()
            self.loading_dialog = None

        self.window().enable_all_shortcuts()
        self.window().loading_in_progress = False

    def _on_loader_finished(self):
        """Called when the loader thread finishes; ensure the overlay is closed."""
        if getattr(self, "loading_dialog", None) is not None:
            self.loading_dialog.releaseKeyboard()
            self.loading_dialog.hide()
            self.loading_dialog.deleteLater()
            self.loading_dialog = None
        self.loader = None

        self.window().enable_all_shortcuts()
        self.window().loading_in_progress = False

    def onImageLoaded(self,
                      pixmap: QPixmap,
                      reset_zoom: bool,
                      preserve_zoom: bool,
                      load_id: int):
        main_win = self.window()

        # 1) Only update the UI if this load ID is still current.
        if load_id != self.current_load_id:
            return

        # 2) Cleanup any loading dialogs or key-filters
        if getattr(main_win, "loading_dialog", None):
            main_win.loading_dialog.releaseKeyboard()
            main_win.loading_dialog.close()
            main_win.loading_dialog.deleteLater()
            main_win.loading_dialog = None
        if getattr(main_win, "loading_key_filter", None):
            QApplication.instance().removeEventFilter(main_win.loading_key_filter)
            main_win.loading_key_filter = None

        # 3) Bail if nothing to show
        if pixmap.isNull():
            return

        # 4) Keep a *clean* full-res pixmap (DPR = 1.0) for all logic
        self.original_pixmap = pixmap.copy()
        self.cached_texture  = None

        # 5) Pull through any pending rotation/brightness
        if hasattr(self, "desired_rotation"):
            self.rotation_angle = self.desired_rotation
            del self.desired_rotation
        if hasattr(self, "desired_brightness"):
            self.brightness_factor = self.desired_brightness
            del self.desired_brightness

        # 6) Hide while we update
        self.pixmap_item.setVisible(False)

        # ─── Decide what to do with zoom on load ─────────────────────────────
        if reset_zoom:
            self.auto_fit    = True
            self.zoom_factor = 1.0
            self.resetTransform()
            self.adjustToFit()
        elif preserve_zoom and hasattr(self, "_saved_transform"):
            self.auto_fit = False
            self.setTransform(self._saved_transform)
        else:
            at_fit = abs(self.zoom_factor - self.fit_zoom_factor) < 0.01
            self.auto_fit = at_fit
        # ─────────────────────────────────────────────────────────────────────

        # 7) Render the pixmap
        if self.auto_fit:
            self.adjustToFit()
        else:
            display_pix = self._pixmapWithRotationAndBrightness()
            self.pixmap_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
            self.pixmap_item.setPixmap(display_pix)
            self.scene.setSceneRect(self.pixmap_item.boundingRect())

        self.pixmap_item.setVisible(True)

        # 8) Clear the busy-loading flag first
        main_win.image_loading = False

        # 9) Now that loading is done, refresh all controls (star will update)
        if hasattr(main_win, "update_floating_controls"):
            main_win.update_floating_controls()

        # ─── Ensure rotation/brightness are GPU-baked even in manual-zoom mode ───
        if not self.auto_fit:
            self.updatePixmap()


    def _pixmapWithRotationAndBrightness(self) -> QPixmap:
        """
        Bake rotation & brightness into a new QPixmap via the GPU
        (we assume viewport() is always a QOpenGLWidget).
        """
        # 1) Rotate first (skip transform if angle==0 for a small perf win)
        if self.rotation_angle != 0:
            base = self.original_pixmap.transformed(
                QTransform().rotate(self.rotation_angle),
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            base = self.original_pixmap

        # 2) GPU brightness (only if non‐default)
        if self.brightness_factor != 1.0:
            vp = self.viewport()               # must be QOpenGLWidget
            vp.makeCurrent()
            out = self.applyBrightnessGPU(
                base,
                self.brightness_factor
            )
            vp.doneCurrent()
        else:
            out = base

        # 3) preserve DPR on the result
        out.setDevicePixelRatio(base.devicePixelRatio())
        return out

    def clear(self):
        self.pixmap_item.setPixmap(QPixmap())

    def adjustToFit(self):
        """
        Reset zoom, rotate + bake brightness into a pixmap,
        then fit & center that result in the view (preserving DPR).
        """
        # 1) Bail if there’s nothing to fit
        if not self.original_pixmap or not self.auto_fit:
            return

        # 2) Reset any prior zoom/transform
        self.resetTransform()

        # 3) Always rotate into a fresh pixmap
        rotated = self.original_pixmap.transformed(
            QTransform().rotate(self.rotation_angle),
            Qt.TransformationMode.SmoothTransformation
        )

        # 4) Bake brightness (GPU if possible, else CPU)
        if self.brightness_factor != 1.0:
            vp = self.viewport()
            if isinstance(vp, QOpenGLWidget):
                vp.makeCurrent()
                baked = self.applyBrightnessGPU(rotated, self.brightness_factor)
                vp.doneCurrent()
            else:
                baked = self.applyBrightness(rotated, self.brightness_factor)
        else:
            baked = rotated

        # 5) Preserve the *original* image’s DPR tag
        baked.setDevicePixelRatio(self.original_pixmap.devicePixelRatio())

        # 6) Show the baked pixmap
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self.pixmap_item.setPixmap(baked)

        # 7) Fit that pixmap to the view & update scene bounds
        rect = self.pixmap_item.sceneBoundingRect()
        self.scene.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

        # 8) Record the new zoom factors
        scale = self.transform().m11()
        self.zoom_factor     = scale
        self.fit_zoom_factor = scale

        # 9) Center (unless explicitly skipped)
        if not getattr(self, "skip_centering", False):
            self.centerOn(rect.center())


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit and self.original_pixmap:
            self.adjustToFit()

    def updatePixmap(self):
        if not self.original_pixmap:
            return

        # 0) Save current view transform & anchor
        saved_transform = self.transform()
        saved_anchor    = self.transformationAnchor()

        # 1) Anchor at center for the bake
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # 2) Rotate
        if self.rotation_angle != 0:
            base = self.original_pixmap.transformed(
                QTransform().rotate(self.rotation_angle),
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            base = self.original_pixmap

        # 3) Brightness (GPU vs CPU)
        vp = self.viewport()
        if self.brightness_factor != 1.0 and isinstance(vp, QOpenGLWidget):
            vp.makeCurrent()
            baked = self.applyBrightnessGPU(base, self.brightness_factor)
            vp.doneCurrent()
        elif self.brightness_factor != 1.0:
            baked = self.applyBrightness(base, self.brightness_factor)
        else:
            baked = base

        # 4) Tag with original DPR
        baked.setDevicePixelRatio(self.original_pixmap.devicePixelRatio())

        # 5) Nearest‐neighbor into item + update bounds
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self.pixmap_item.setPixmap(baked)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        # 6) Restore transform & anchor so zoom/pan stay exactly where they were
        self.setTransform(saved_transform)
        self.setTransformationAnchor(saved_anchor)


    def setBrightness(self, factor):
        # Turn off split‐view compare overlay
        self.compare_enabled   = False
        # Drop the old GL texture so we rebuild fresh
        self.cached_texture    = None
        # Apply the new brightness and repaint
        self.brightness_factor = factor
        self.updatePixmap()

    def wheelEvent(self, event: QWheelEvent):
        if not self.original_pixmap:
            return
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.auto_fit = False
        old_scene_pos = self.mapToScene(event.position().toPoint())
        let_in = event.angleDelta().y() > 0
        factor = 1.1 if let_in else 0.9
        current_zoom = self.transform().m11()
        if current_zoom * factor < 0.1:
            factor = 0.1 / current_zoom
        elif current_zoom * factor > 3.0:
            factor = 3.0 / current_zoom
        self.scale(factor, factor)
        self.zoom_factor = self.transform().m11()
        new_scene_pos = self.mapToScene(event.position().toPoint())
        delta = new_scene_pos - old_scene_pos
        self.translate(delta.x(), delta.y())

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.auto_fit = True
        self.adjustToFit()
        self.zoom_factor = self.transform().m11()
        self.fit_zoom_factor = self.zoom_factor

    def paintEvent(self, event):
        gl_viewport = self.viewport()

        # If we're using an OpenGL viewport, clear it properly
        if isinstance(gl_viewport, QOpenGLWidget):
            from OpenGL import GL
            from PyQt6.QtGui import QColor

            gl_viewport.makeCurrent()

            # Convert self.bg_color ("#RRGGBB") to normalized floats
            c = QColor(self.bg_color)
            r, g, b, _ = c.getRgbF()
            GL.glClearColor(r, g, b, 1.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

            super().paintEvent(event)
            gl_viewport.doneCurrent()

        else:
            # Standard Qt painter fallback
            from PyQt6.QtGui import QPainter, QColor

            painter = QPainter(gl_viewport)
            painter.fillRect(gl_viewport.rect(), QColor(self.bg_color))
            painter.end()

            super().paintEvent(event)


    def zoom_in(self):
        self._manual_zoom(zoom_in=True)

    def zoom_out(self):
        self._manual_zoom(zoom_in=False)

    def _manual_zoom(self, zoom_in: bool):
        if not self.original_pixmap:
            return
        viewport_center = self.viewport().rect().center()
        scene_center = self.mapToScene(viewport_center)
        factor = 1.1 if zoom_in else 0.9
        current_zoom = self.transform().m11()
        if current_zoom * factor < 0.1:
            factor = 0.1 / current_zoom
        elif current_zoom * factor > 3.0:
            factor = 3.0 / current_zoom
        self.scale(factor, factor)
        self.zoom_factor = self.transform().m11()
        self.centerOn(scene_center)

    def rotate_clockwise(self):
        self.rotation_angle = (self.rotation_angle + 90) % 360
        
        # Invalidate the cached texture so the GPU brightness code
        # will recreate it with the correct size:
        self.cached_texture = None

        if self.auto_fit or abs(self.zoom_factor - 1.0) < 0.01:
            self.auto_fit = True
            self.adjustToFit()
        else:
            self.updatePixmap()
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
            self.centerOn(self.scene.sceneRect().center())
    
    def contextMenuEvent(self, event: QMouseEvent):
        # Get the main window (PhotoViewer) that contains this viewer.
        photo_viewer = self.window()

        # Create the overlay.
        overlay = BaseOverlay(
            parent=photo_viewer,
            overlay_name="ContextMenuOverlay",
            bg_color="rgba(0, 0, 0, 150)"
        )
        overlay.setObjectName("ContextMenuOverlay")
        overlay.setGeometry(photo_viewer.rect())
        overlay.show()
        overlay.raise_()
        photo_viewer.context_menu_overlay = overlay

        # Allow closing the overlay when pressing ESC.
        def overlay_key_press(ev):
            if ev.key() == Qt.Key.Key_Escape:
                overlay.close()
            else:
                ev.ignore()
        overlay.keyPressEvent = overlay_key_press

        # Create the container to hold all the menu buttons.
        container = QWidget(overlay)
        container.setObjectName("ContextMenuContainer")
        container.setStyleSheet("""
            QWidget#ContextMenuContainer {
                background-color: rgba(0, 0, 0, 0.90);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
            }
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 16px;
                text-align: left;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 50);
            }
            QFrame {
                background-color: #666666;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        # A helper function to add a horizontal separator.
        def add_separator():
            sep = QFrame(container)
            sep.setFixedHeight(1)
            sep.setStyleSheet("background-color: #666666; margin: 6px 0;")
            layout.addWidget(sep)

        # Get the translation dictionary.
        lang = photo_viewer.current_language
        t = translations.get(lang, translations["en"])

        # Determine if an image is loaded.
        has_image = (photo_viewer.image_files and
                     0 <= photo_viewer.current_index < len(photo_viewer.image_files))
        current_image = photo_viewer.image_files[photo_viewer.current_index] if has_image else None

        has_favorites = bool(photo_viewer.favorites)
        has_compare = bool(photo_viewer.compare_set)

        # --- Standard Options: Favorite and Compare ---
        if has_image:
            fav_text = t["unfavorite_image"] if current_image in photo_viewer.favorites else t["favorite_image"]
            btn_fav = QPushButton(fav_text)
            btn_fav.clicked.connect(lambda: (photo_viewer.toggle_favorite(), overlay.close()))
            layout.addWidget(btn_fav)

            cmp_text = t["remove_from_compare"] if current_image in photo_viewer.compare_set else t["add_to_compare"]
            btn_cmp = QPushButton(cmp_text)
            btn_cmp.clicked.connect(lambda: (photo_viewer.toggle_compare(), overlay.close()))
            layout.addWidget(btn_cmp)
            add_separator()

        # --- Undo/Redo Options: Grouped as Their Own Category ---
        # look up the current image’s history instead of undo_stack/redo_stack
        path     = photo_viewer._current_path
        can_undo = False
        can_redo = False
        if path and path in photo_viewer._history:
            hist     = photo_viewer._history[path]
            can_undo = bool(hist["undo"])
            can_redo = bool(hist["redo"])

        if can_undo or can_redo:
            add_separator()  # Separator above the undo/redo group

            if can_undo:
                btn_undo = QPushButton(t["undo"], container)
                btn_undo.clicked.connect(lambda: (photo_viewer.undo_action(), overlay.close()))
                layout.addWidget(btn_undo)

            if can_redo:
                btn_redo = QPushButton(t["redo"], container)
                btn_redo.clicked.connect(lambda: (photo_viewer.redo_action(), overlay.close()))
                layout.addWidget(btn_redo)

            add_separator()  # Separator below the undo/redo group


        # --- Saving Options (only add these if the image is modified) ---
        # Get the image_modified flag.
        image_modified_flag = getattr(photo_viewer, "image_modified", False)
        # Define pristine solely based on brightness and rotation.
        pristine = (self.brightness_factor == 1.0 and 
                    self.rotation_angle == 0 and 
                    not image_modified_flag)
        if not pristine:
            add_separator()
            btn_save_modified = QPushButton(t["save_modified_file"])
            btn_save_modified.clicked.connect(lambda: (overlay.close(), photo_viewer.saveModifiedImage(overwrite=True)))
            layout.addWidget(btn_save_modified)

            btn_save_copy = QPushButton(t["save_copy_modified_file"])
            btn_save_copy.clicked.connect(lambda: (overlay.close(), photo_viewer.saveModifiedImage(overwrite=False)))
            layout.addWidget(btn_save_copy)

            add_separator()             

        # --- File Operations ---
        btn_open = QPushButton(t["open_in_explorer"])
        btn_open.clicked.connect(lambda: (photo_viewer.open_image_in_path(), overlay.close()))
        layout.addWidget(btn_open)

        btn_delete = QPushButton(t["delete_image"])
        btn_delete.clicked.connect(lambda: (overlay.close(), photo_viewer.delete_current_image()))
        layout.addWidget(btn_delete)

        btn_copy = QPushButton(t["copy_image"])
        btn_copy.clicked.connect(lambda: (photo_viewer.copy_current_image(), overlay.close()))
        layout.addWidget(btn_copy)

        add_separator()

        # --- Navigation Options ---
        btn_first = QPushButton(t["go_to_first_image"])
        btn_first.clicked.connect(lambda: (photo_viewer.go_to_first_image(), overlay.close()))
        layout.addWidget(btn_first)

        btn_last = QPushButton(t["go_to_last_image"])
        btn_last.clicked.connect(lambda: (photo_viewer.go_to_last_image(), overlay.close()))
        layout.addWidget(btn_last)

        container.adjustSize()

        # --- Advanced Options Submenu ---
        submenu = QWidget(overlay)
        submenu.setObjectName("SubMenuContainer")
        submenu.setStyleSheet("""
            QWidget#SubMenuContainer {
                background-color: rgba(0, 0, 0, 0.95);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 6px;
            }
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 16px;
                text-align: left;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 50);
            }
        """)
        sub_layout = QVBoxLayout(submenu)
        sub_layout.setContentsMargins(6, 6, 6, 6)
        sub_layout.setSpacing(0)

        if has_favorites:
            btn_clear_fav = QPushButton(t["clear_favorites"], submenu)
            btn_clear_fav.clicked.connect(lambda: (photo_viewer.clear_favorites(), overlay.close()))
            sub_layout.addWidget(btn_clear_fav)

        if has_compare:
            btn_clear_cmp = QPushButton(t["clear_compare"], submenu)
            btn_clear_cmp.clicked.connect(lambda: (photo_viewer.clear_compare(), overlay.close()))
            sub_layout.addWidget(btn_clear_cmp)

        all_images = photo_viewer.get_all_images()
        if len(all_images) > len(photo_viewer.favorites):
            btn_del_nonfav = QPushButton(t["delete_non_favorites"], submenu)
            btn_del_nonfav.clicked.connect(lambda: (photo_viewer.delete_non_favorites_action(), overlay.close()))
            sub_layout.addWidget(btn_del_nonfav)

        if sub_layout.count() > 0:
            add_separator()
            bulk_label = "Advanced options" if lang == "en" else "Opciones avanzadas"
            btn_bulk = QPushButton(bulk_label)
            layout.addWidget(btn_bulk)
            # Set up the submenu toggle.
            submenu.hide()
            def toggle_submenu():
                if submenu.isVisible():
                    submenu.hide()
                else:
                    submenu.adjustSize()
                    container_top_left_global = container.mapToGlobal(QPoint(0, 0))
                    sub_x = container_top_left_global.x() + container.width() - 1
                    sub_y = container_top_left_global.y() + btn_bulk.pos().y()
                    local_sub_pos = overlay.mapFromGlobal(QPoint(sub_x, sub_y))
                    submenu.move(local_sub_pos)
                    submenu.show()
                    submenu.raise_()
            btn_bulk.clicked.connect(toggle_submenu)

        container.adjustSize()

        # Position the container near the mouse click.
        local_click = overlay.mapFromGlobal(event.globalPos())
        x = local_click.x()
        y = local_click.y()
        if x + container.width() > overlay.width():
            x = overlay.width() - container.width() - 10
        if y + container.height() > overlay.height():
            y = overlay.height() - container.height() - 10
        container.move(x, y)
        container.show()

        # Close the overlay if clicking outside the container.
        def overlay_mousePressEvent(ev):
            if not container.geometry().contains(ev.pos()):
                overlay.close()
            else:
                ev.ignore()
        overlay.mousePressEvent = overlay_mousePressEvent

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            if not hasattr(self, "_drag_overlay") or self._drag_overlay is None:
                self._drag_overlay = MyDragOverlay(self)
            self._drag_overlay.show()
            self._drag_overlay.raise_()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        if hasattr(self, "_drag_overlay") and self._drag_overlay:
            self._drag_overlay.dragLeaveEvent(event)
        else:
            event.accept()

    def dropEvent(self, event):
        if hasattr(self, "_drag_overlay") and self._drag_overlay:
            self._drag_overlay.dropEvent(event)
            # Optionally, schedule deletion:
            self._drag_overlay.deleteLater()
            self._drag_overlay = None
        else:
            event.ignore()

    def applyBrightnessGPU(self, pixmap: QPixmap, factor: float) -> QPixmap:
        # 1) Bake a fresh QOpenGLTexture from the pixmap each time
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        tex = QOpenGLTexture(image)
        tex.setMinificationFilter(QOpenGLTexture.Filter.Nearest)
        tex.setMagnificationFilter(QOpenGLTexture.Filter.Nearest)
        tex.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)

        # 2) Offscreen FBO of the same size
        w, h = pixmap.width(), pixmap.height()
        fbo = QOpenGLFramebufferObject(QSize(w, h))
        fbo.bind()
        from OpenGL import GL
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_CULL_FACE)

        glViewport(0, 0, w, h)
        glClearColor(0, 0, 0, 0)
        glClear(GL_COLOR_BUFFER_BIT)

        # 3) Compile + bind brightness‐gamma shader
        prog = QOpenGLShaderProgram()
        vertex_src = """
        #version 330 core
        layout(location=0) in vec2 position;
        layout(location=1) in vec2 texCoord;
        out vec2 vTC;
        void main() {
            gl_Position = vec4(position, 0.0, 1.0);
            vTC = texCoord;
        }
        """
        fragment_src = """
        #version 330 core
        in vec2 vTC;
        out vec4 outColor;
        uniform sampler2D image;
        uniform float brightness;
        void main() {
            vec4 c = texture(image, vTC);
            vec3 adj = pow(c.rgb, vec3(brightness));
            outColor = vec4(adj, c.a);
        }
        """
        VERTEX_SHADER   = 0x00000001
        FRAGMENT_SHADER = 0x00000002
        prog.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit(VERTEX_SHADER),
            vertex_src
        )
        prog.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit(FRAGMENT_SHADER),
            fragment_src
        )
        prog.link()
        prog.bind()
        prog.setUniformValue("brightness", factor)

        glActiveTexture(GL_TEXTURE0)
        tex.bind()
        prog.setUniformValue("image", 0)

        # 4) Draw one big triangle—no shared edge, no seam
        verts = [
            -1.0, -1.0,   0.0, 0.0,
             3.0, -1.0,   2.0, 0.0,
            -1.0,  3.0,   0.0, 2.0
        ]
        verts = (GLfloat * len(verts))(*verts)
        VAO = glGenVertexArrays(1)
        VBO = glGenBuffers(1)
        glBindVertexArray(VAO)
        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        glBufferData(GL_ARRAY_BUFFER, ctypes.sizeof(verts), verts, GL_STATIC_DRAW)

        stride = 4 * ctypes.sizeof(GLfloat)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE,
                              stride,
                              ctypes.c_void_p(2 * ctypes.sizeof(GLfloat)))
        glEnableVertexAttribArray(1)

        glDrawArrays(GL_TRIANGLES, 0, 3)

        # 5) Cleanup and read back
        glBindVertexArray(0)
        tex.release()
        prog.release()
        fbo.release()

        result = fbo.toImage().mirrored(False, True)
        return QPixmap.fromImage(result)


    def applySharpenGPU(self, pixmap: QPixmap, radius: int, amount: float) -> QPixmap:
        # 1) Compile & link shader if needed
        if self._sharpen_program is None:
            ctx = QOpenGLContext.currentContext()
            if not ctx:
                raise RuntimeError("No current OpenGL context!")
            prog = QOpenGLShaderProgram(ctx)

            # vertex pass-through
            prog.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Vertex,
                b"""
                #version 330 core
                layout(location = 0) in vec2 pos;
                layout(location = 1) in vec2 uv;
                out vec2 v_uv;
                void main() {
                    v_uv = uv;
                    gl_Position = vec4(pos, 0.0, 1.0);
                }
                """
            )
            # unsharp‐mask fragment
            prog.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Fragment,
                b"""
                #version 330 core
                in vec2 v_uv;
                uniform sampler2D u_tex;
                uniform float u_radius;
                uniform float u_amount;
                out vec4 fragColor;
                void main() {
                    vec2 texel = 1.0 / textureSize(u_tex, 0);
                    vec3 c = texture(u_tex, v_uv).rgb;
                    vec3 b = vec3(0.0);
                    for(int x=-1; x<=1; ++x)
                        for(int y=-1; y<=1; ++y)
                            b += texture(u_tex, v_uv + texel * vec2(x,y) * u_radius).rgb;
                    b /= 9.0;
                    vec3 r = c + (c - b) * u_amount;
                    fragColor = vec4(r, 1.0);
                }
                """
            )
            prog.link()
            self._sharpen_program = prog

        # 2) Prepare FBO
        size = QSize(pixmap.width(), pixmap.height())
        if self._sharpen_fbo is None or self._sharpen_fbo.size() != size:
            if self._sharpen_fbo:
                del self._sharpen_fbo
            self._sharpen_fbo = QOpenGLFramebufferObject(size)

        # 3) Render pass
        self._sharpen_fbo.bind()
        self._sharpen_program.bind()

        # upload texture
        tex = QOpenGLTexture(pixmap.toImage())
        tex.setMinificationFilter(QOpenGLTexture.Filter.Nearest)
        tex.setMagnificationFilter(QOpenGLTexture.Filter.Nearest)
        tex.bind(0)

        # set uniforms
        self._sharpen_program.setUniformValue("u_tex", 0)
        self._sharpen_program.setUniformValue("u_radius", float(radius))
        self._sharpen_program.setUniformValue("u_amount", float(amount))

        # draw full-screen quad via PyOpenGL
        GL.glBegin(GL.GL_TRIANGLE_STRIP)
        # bottom-left
        GL.glTexCoord2f(0.0, 0.0);  GL.glVertex2f(-1.0, -1.0)
        # top-left
        GL.glTexCoord2f(0.0, 1.0);  GL.glVertex2f(-1.0,  1.0)
        # bottom-right
        GL.glTexCoord2f(1.0, 0.0);  GL.glVertex2f( 1.0, -1.0)
        # top-right
        GL.glTexCoord2f(1.0, 1.0);  GL.glVertex2f( 1.0,  1.0)
        GL.glEnd()

        self._sharpen_program.release()
        self._sharpen_fbo.release()
        tex.destroy()

        # return the sharpened pixmap
        return QPixmap.fromImage(self._sharpen_fbo.toImage())

# Crop
# ------------------------------------------------------------------------
class CropOverlay(QWidget):
    def __init__(self, parent, original_pixmap: QPixmap, current_language="en"):
        super().__init__(parent)
        self.setObjectName("CropOverlay")
        # Make it cover the parent's entire area.
        if parent:
            self.setGeometry(parent.rect())
        # Configure the window: frameless and always on top.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        # Explicitly disable any translucent background.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        # Enable auto-fill so that the background gets painted.
        self.setAutoFillBackground(True)
        palette = self.palette()
        # Set our background (solid black) via the palette.
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.black)
        self.setPalette(palette)
        # Create the crop content (the handles, rotation slider, etc.).
        self.crop_content = CropOverlayContent(self, original_pixmap, current_language)
        self.crop_content.setGeometry(self.rect())
        self.crop_content.cropAccepted.connect(self.onCropAccepted)
        self.crop_content.cropCancelled.connect(self.onCropCancelled)
        self.show()
        QTimer.singleShot(0, self.crop_content.update)
        QTimer.singleShot(50, lambda: QCursor.setPos(self.mapToGlobal(self.rect().center())))


    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            # exactly the same as pressing “Cancel”
            self.onCropCancelled()
        else:
            super().keyPressEvent(event)

    def handleParentResize(self):
        # Delegate the resize handling to the crop content widget.
        self.crop_content.handleParentResize()

    def onCropAccepted(self, cropped_pix: QPixmap):
        # 1) Tell the PhotoViewer to apply the crop result
        if hasattr(self.parent(), "applyCropResult"):
            self.parent().applyCropResult(cropped_pix)

            # 2) Immediately snap the viewer to fit the new image
            viewer = self.parent().image_viewer
            viewer.auto_fit = True
            viewer.adjustToFit()

        # 3) Close the overlay
        self.close()

    def onCropCancelled(self):
        self.close()

    def closeEvent(self, event):
        # If the parent is a PhotoViewer, re-enable shortcuts and the floating menu.
        if hasattr(self.parent(), "enable_all_shortcuts"):
            self.parent().enable_all_shortcuts()
        if hasattr(self.parent(), "floating_menu") and self.parent().floating_menu:
            self.parent().floating_menu.setEnabled(True)
        super().closeEvent(event)


class CropOverlayContent(QWidget):
    cropAccepted = pyqtSignal(QPixmap)
    cropCancelled = pyqtSignal()

    def __init__(self, parent, original_pixmap: QPixmap, current_language="en"):
        super().__init__(parent)
        # Force this widget to have its own non-translucent background.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)


        # Continue with the original initialization.
        self.original_pixmap = original_pixmap
        self.current_language = current_language

        # Create rotation slider (using your SmoothRotationSlider)
        self.rotation = 0.0
        t = translations.get(current_language, translations["en"])

        # ─── NEW: compute the current image’s native aspect ratio ───
        w = original_pixmap.width()
        h = original_pixmap.height()
        default_ratio = (w / h) if h else 1.0
        # ─────────────────────────────────────────────────────────────

        # Set up aspect ratio combo box.
        self.ASPECT_RATIOS = [
            (None,            t["crop_aspect_custom"]),    # Custom
            (default_ratio,   t["crop_aspect_original"]),  # Original Aspect
            (1.0,             t["crop_aspect_square"]),    # Square (1:1)
            (16/9,            t["crop_aspect_sixteen_nine"]),  # Widescreen (16:9)
            (4/3,             t["crop_aspect_four_three"]),    # Standard (4:3)
        ]
        self.aspect_ratio_combo = OverlayComboBox(self)
        self.aspect_ratio_combo.setFixedWidth(180)
        self.aspect_ratio_combo.setStyleSheet("""
            QComboBox {
                background-color: #222;
                color: white;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 14px;
            }
            QComboBox QAbstractItemView {
                background-color: #333;
                color: white;
                selection-background-color: #555;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
        """)
        for ratio_value, label in self.ASPECT_RATIOS:
            self.aspect_ratio_combo.addItem(label, userData=ratio_value)
        self.aspect_ratio_combo.setCurrentIndex(0)
        self.aspect_ratio = self.aspect_ratio_combo.itemData(0)
        self.aspect_ratio_combo.currentIndexChanged.connect(self.on_aspect_ratio_changed)
        self.aspect_ratio_combo.activated.connect(self.on_aspect_ratio_changed)


        # Configure the rotation slider.
        self.rotation_slider = SmoothRotationSlider(Qt.Orientation.Horizontal, self)
        self.rotation_slider.keyPressEvent = self.slider_keyPressEvent
        self.rotation_slider.floatValueChanged.connect(self.on_rotation_slider_changed)
        self.rotation_slider.sliderReleased.connect(self.on_slider_released)
        self.angle_label = QLabel(f"{t['angle']} 0.0°", self)
        self.angle_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")

        # OK and Cancel buttons.
        self.ok_button = QPushButton(t["crop"], self)
        self.ok_button.setFixedSize(120, 35)
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #007BFF;
                color: white;
                border-radius: 6px;
                font-size: 15px;
            }
            QPushButton:hover { background-color: #0056b3; }
        """)
        self.cancel_button = QPushButton(t["cancel"], self)
        self.cancel_button.setFixedSize(120, 35)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #DC3545;
                color: white;
                border-radius: 6px;
                font-size: 15px;
            }
            QPushButton:hover { background-color: #B22222; }
        """)
        self.ok_button.clicked.connect(self.handleAccept)
        self.cancel_button.clicked.connect(self.handleCancel)

        # Layout the controls.
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.aspect_ratio_combo)
        bottom_layout.addSpacing(10)
        bottom_layout.addWidget(self.rotation_slider)
        bottom_layout.addWidget(self.angle_label)
        bottom_layout.addSpacing(10)
        bottom_layout.addWidget(self.ok_button)
        bottom_layout.addWidget(self.cancel_button)
        bottom_layout.addStretch()

        main_layout = QVBoxLayout(self)
        main_layout.addStretch()
        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)

        # Set initial focus on the rotation slider.
        QTimer.singleShot(
            0,
            lambda: self.rotation_slider.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        )

        # Cropping and drawing variables.
        self._scaled_pixmap = None
        self._image_rect = QRectF()
        self._scale_factor = 1.0
        self.crop_rect = QRect(0, 0, 200, 200)
        self.handles = {
            k: QRect() for k in [
                "top_left", "top_right", "bottom_left", "bottom_right",
                "left_mid", "right_mid", "top_mid", "bottom_mid"
            ]
        }
        self.handle_size = 14
        self.active_handle = None
        self.dragging = False
        self.mouse_start_pos = QPoint()
        self.initial_crop_rect = None
        self.modified = False

        # Resize to parent's size and initialize crop region.
        self.resize(parent.size())
        self.update_scaled_pixmap()
        self.init_default_crop()

    def on_aspect_ratio_changed(self, index):
        self.aspect_ratio = self.aspect_ratio_combo.itemData(index)
        self.init_default_crop()
        self.update()

    def slider_keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            new_val = self.rotation_slider.value() - 0.1
            self.rotation_slider.setValue(new_val)
            self.on_rotation_slider_changed(new_val)
            event.accept()
        elif event.key() == Qt.Key.Key_Right:
            new_val = self.rotation_slider.value() + 0.1
            self.rotation_slider.setValue(new_val)
            self.on_rotation_slider_changed(new_val)
            event.accept()
        elif event.key() == Qt.Key.Key_Up:
            new_val = self.rotation_slider.value() + 1.0
            self.rotation_slider.setValue(new_val)
            self.on_rotation_slider_changed(new_val)
            event.accept()
        elif event.key() == Qt.Key.Key_Down:
            new_val = self.rotation_slider.value() - 1.0
            self.rotation_slider.setValue(new_val)
            self.on_rotation_slider_changed(new_val)
            event.accept()
        elif event.key() == Qt.Key.Key_0:
            self.rotation_slider.setValue(0.0)
            self.on_rotation_slider_changed(0.0)
            event.accept()
        else:
            QSlider.keyPressEvent(self.rotation_slider, event)

    def on_rotation_slider_changed(self, angle: float):
        self.rotation = angle
        t = translations.get(self.current_language, translations["en"])
        self.angle_label.setText(f"{t['angle']} {angle:.1f}°")
        self.update_scaled_pixmap()
        self.update()

    def on_slider_released(self):
        threshold = 1
        current_value = self.rotation_slider.value()
        if abs(current_value) < threshold:
            self.rotation_slider.setValue(0)
            self.on_rotation_slider_changed(0)

    def update_scaled_pixmap(self):
        """
        1) Rotate full-res around its center → self._rotated_full
        2) Fit-to-screen scale via FBO → self._scaled_pixmap
        3) Recompute self._image_rect & handles, then repaint
        """
        if self.original_pixmap.isNull():
            return

        # 1) Center-pivot rotate full-res
        w = self.original_pixmap.width()
        h = self.original_pixmap.height()
        tf = QTransform()
        tf.translate(w/2, h/2)
        tf.rotate(self.rotation)
        tf.translate(-w/2, -h/2)
        self._rotated_full = self.original_pixmap.transformed(
            tf,
            Qt.TransformationMode.SmoothTransformation
        )

        # 2) Fit-to-screen scale exactly as before
        avail_w = self.width()
        avail_h = self.height() - 60
        rw = self._rotated_full.width()
        rh = self._rotated_full.height()
        if rw == 0 or rh == 0:
            return
        self._scale_factor = min(avail_w / rw, avail_h / rh)
        new_w = int(round(rw * self._scale_factor))
        new_h = int(round(rh * self._scale_factor))

        # 3) GPU-offscreen FBO → preview pixmap
        self._scaled_pixmap = self._rotated_full.scaled(
            new_w, new_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )


        # 4) Center & update handles, then repaint
        x = int(round((avail_w - new_w) / 2))
        y = 10
        self._image_rect = QRectF(x, y, new_w, new_h)
        self.update_handles()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(0, 0, 0))  # Black background

        # Just draw the already-prepared preview
        if not self._scaled_pixmap.isNull():
            painter.drawPixmap(
                int(self._image_rect.x()),
                int(self._image_rect.y()),
                self._scaled_pixmap
            )

        # Draw crop rectangle and handles
        gray_pen  = QPen(QColor(128, 128, 128), 2)
        white_pen = QPen(Qt.GlobalColor.white, 1)

        painter.setPen(gray_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.crop_rect)

        painter.setPen(white_pen)
        painter.drawRect(self.crop_rect)

        for handle in self.handles.values():
            painter.setPen(gray_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(handle)
            painter.setPen(white_pen)
            painter.setBrush(QColor("white"))
            painter.drawRect(handle)

        painter.end()

    def get_final_cropped_pixmap(self) -> QPixmap:
        # 1) rebuild the rotated_full
        rotated_full = self.original_pixmap.transformed(
            QTransform().rotate(self.rotation),
            Qt.TransformationMode.SmoothTransformation
        )

        # 2) same scale & offset as in paintEvent
        avail_w = self.width()
        avail_h = self.height() - 60
        scale = min(avail_w / rotated_full.width(),
                    avail_h / rotated_full.height())
        x_off = (avail_w - rotated_full.width() * scale) / 2
        y_off = 10

        # 3) invert only the translate+scale (not the rotation)
        tf = QTransform()
        tf.translate(x_off, y_off)
        tf.scale(scale, scale)
        inv, ok = tf.inverted()
        if not ok:
            return QPixmap()

        # 4) map the top-left corner of the crop box
        tl = inv.map(QPointF(self.crop_rect.left(), self.crop_rect.top()))

        # 5) compute how big the box is in rotated_full coords
        rw = int(round(self.crop_rect.width()  / scale))
        rh = int(round(self.crop_rect.height() / scale))
        ix = int(round(tl.x()))
        iy = int(round(tl.y()))

        # 6) clamp into the rotated_full bounds
        r = QRect(ix, iy, rw, rh).intersected(rotated_full.rect())
        if r.width() <= 0 or r.height() <= 0:
            return QPixmap()

        # 7) copy & return
        return rotated_full.copy(r)


    def init_default_crop(self):
        iw, ih = self._image_rect.width(), self._image_rect.height()
        if iw <= 0 or ih <= 0:
            return
        cw, ch = iw / 3, ih / 3
        if self.aspect_ratio is not None:
            # Force crop rectangle to maintain the given ratio.
            ch = cw / self.aspect_ratio
            if ch > ih / 3:
                ch = ih / 3
                cw = ch * self.aspect_ratio
        cx = self._image_rect.x() + (iw - cw) / 2
        cy = self._image_rect.y() + (ih - ch) / 2
        self.crop_rect = QRect(int(cx), int(cy), int(cw), int(ch))
        self.update_handles()

    def update_handles(self):
        """
        Recompute the positions of the eight handles around self.crop_rect,
        but if a fixed aspect ratio is active (i.e. self.aspect_ratio is not None),
        the mid‐edge handles are cleared (set to zero‐sized) so they neither draw
        nor respond to mouse events.
        """
        c = self.crop_rect
        s = self.handle_size
        half = s // 2

        # Corner handles
        self.handles["top_left"]     = QRect(c.left() - half,  c.top() - half,     s, s)
        self.handles["top_right"]    = QRect(c.right() - half, c.top() - half,     s, s)
        self.handles["bottom_left"]  = QRect(c.left() - half,  c.bottom() - half,  s, s)
        self.handles["bottom_right"] = QRect(c.right() - half, c.bottom() - half,  s, s)

        # Mid‐edge handles (computed for Custom mode, but then possibly cleared)
        mid_x = (c.left() + c.right()) // 2
        mid_y = (c.top()  + c.bottom()) // 2
        mids = {
            "left_mid":   QRect(c.left() - half,  mid_y - half, s, s),
            "right_mid":  QRect(c.right() - half, mid_y - half, s, s),
            "top_mid":    QRect(mid_x - half,     c.top() - half, s, s),
            "bottom_mid": QRect(mid_x - half,     c.bottom() - half, s, s),
        }
        self.handles.update(mids)

        # If we’re in a fixed‐ratio mode, disable the mid‐edge handles completely:
        if self.aspect_ratio is not None:
            for key in ("left_mid", "right_mid", "top_mid", "bottom_mid"):
                # zero‐size rect => invisible & non‐interactive
                self.handles[key] = QRect()

    def mousePressEvent(self, event: QEvent):
        if event.type() == QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
            pos = event.pos()
            self.initial_crop_rect = QRect(self.crop_rect)
            for name, rect in self.handles.items():
                if rect.contains(pos):
                    self.active_handle = name
                    self.dragging = True
                    self.mouse_start_pos = pos
                    break
            else:
                if self.crop_rect.contains(pos):
                    self.active_handle = "move"
                    self.dragging = True
                    self.mouse_start_pos = pos
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event: QEvent):
        if event.type() != QEvent.Type.MouseMove:
            return
        pos = event.pos()

        # Update cursor when hovering, but do nothing if not actively dragging
        if not self.dragging:
            self.setCursor(self.cursor_for_handle(self.handle_at(pos)))
            return

        dx = pos.x() - self.mouse_start_pos.x()
        dy = pos.y() - self.mouse_start_pos.y()
        img = self._image_rect  # alias for image bounds

        # If fixed ratio and dragged a mid-edge handle, ignore—only corners allowed
        if (
            self.aspect_ratio is not None
            and self.active_handle in ("left_mid", "right_mid", "top_mid", "bottom_mid")
        ):
            return

        # Start from current crop rectangle
        new_rect = QRect(self.crop_rect)

        if self.active_handle == "move":
            # Move the crop rect
            new_rect.translate(dx, dy)
            # Clamp within image
            if new_rect.left()   < img.left():   new_rect.moveLeft(int(img.left()))
            if new_rect.right()  > img.right():  new_rect.moveRight(int(img.right()))
            if new_rect.top()    < img.top():    new_rect.moveTop(int(img.top()))
            if new_rect.bottom() > img.bottom(): new_rect.moveBottom(int(img.bottom()))

        else:
            # Corner-resize with fixed ratio?
            if (
                self.aspect_ratio is not None
                and self.active_handle in ("top_left", "top_right", "bottom_left", "bottom_right")
            ):
                fixed = {
                    "top_left":     self.initial_crop_rect.bottomRight(),
                    "top_right":    self.initial_crop_rect.bottomLeft(),
                    "bottom_left":  self.initial_crop_rect.topRight(),
                    "bottom_right": self.initial_crop_rect.topLeft(),
                }[self.active_handle]

                # Compute new width/height preserving ratio
                new_width  = abs(pos.x() - fixed.x())
                new_height = new_width / self.aspect_ratio

                if self.active_handle == "top_left":
                    left   = fixed.x() - new_width
                    top    = fixed.y() - new_height
                    # clamp top/left
                    if left < img.left():
                        left = int(img.left())
                        new_width = fixed.x() - left
                        new_height = new_width / self.aspect_ratio
                        top = fixed.y() - new_height
                    if top < img.top():
                        top = int(img.top())
                        new_height = fixed.y() - top
                        new_width = new_height * self.aspect_ratio
                        left = fixed.x() - new_width
                    new_rect = QRect(int(left), int(top), int(new_width), int(new_height))

                elif self.active_handle == "top_right":
                    right  = fixed.x() + new_width
                    top    = fixed.y() - new_height
                    if right > img.right():
                        right = int(img.right())
                        new_width = right - fixed.x()
                        new_height = new_width / self.aspect_ratio
                        top = fixed.y() - new_height
                    if top < img.top():
                        top = int(img.top())
                        new_height = fixed.y() - top
                        new_width = new_height * self.aspect_ratio
                        right = fixed.x() + new_width
                    new_rect = QRect(int(fixed.x()), int(top), int(new_width), int(new_height))

                elif self.active_handle == "bottom_left":
                    left   = fixed.x() - new_width
                    bottom = fixed.y() + new_height
                    if left < img.left():
                        left = int(img.left())
                        new_width = fixed.x() - left
                        new_height = new_width / self.aspect_ratio
                        bottom = fixed.y() + new_height
                    if bottom > img.bottom():
                        bottom = int(img.bottom())
                        new_height = bottom - fixed.y()
                        new_width = new_height * self.aspect_ratio
                        left = fixed.x() - new_width
                    new_rect = QRect(int(left), int(fixed.y()), int(new_width), int(new_height))

                elif self.active_handle == "bottom_right":
                    right  = fixed.x() + new_width
                    bottom = fixed.y() + new_height
                    if right > img.right():
                        right = int(img.right())
                        new_width = right - fixed.x()
                        new_height = new_width / self.aspect_ratio
                        bottom = fixed.y() + new_height
                    if bottom > img.bottom():
                        bottom = int(img.bottom())
                        new_height = bottom - fixed.y()
                        new_width = new_height * self.aspect_ratio
                        right = fixed.x() + new_width
                    new_rect = QRect(int(fixed.x()), int(fixed.y()), int(new_width), int(new_height))

            else:
                # Freeform edge drags (only when aspect_ratio is None)
                if "left" in self.active_handle:
                    left = max(int(img.left()), new_rect.left() + dx)
                    left = min(left, new_rect.right() - 10)
                    new_rect.setLeft(left)
                if "right" in self.active_handle:
                    right = min(int(img.right()), new_rect.right() + dx)
                    right = max(right, new_rect.left() + 10)
                    new_rect.setRight(right)
                if "top" in self.active_handle:
                    top = max(int(img.top()), new_rect.top() + dy)
                    top = min(top, new_rect.bottom() - 10)
                    new_rect.setTop(top)
                if "bottom" in self.active_handle:
                    bottom = min(int(img.bottom()), new_rect.bottom() + dy)
                    bottom = max(bottom, new_rect.top() + 10)
                    new_rect.setBottom(bottom)

        # Final clamp for safety
        if new_rect.left()   < img.left():   new_rect.moveLeft(int(img.left()))
        if new_rect.right()  > img.right():  new_rect.moveRight(int(img.right()))
        if new_rect.top()    < img.top():    new_rect.moveTop(int(img.top()))
        if new_rect.bottom() > img.bottom(): new_rect.moveBottom(int(img.bottom()))

        # Commit changes
        self.crop_rect = new_rect
        self.mouse_start_pos = pos
        self.update_handles()
        self.update()

    def mouseReleaseEvent(self, event: QEvent):
        if event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton:
            self.dragging = False
            self.active_handle = None
            event.accept()
        else:
            event.ignore()

    def handle_at(self, pt: QPoint) -> str:
        for name, rect in self.handles.items():
            if rect.contains(pt):
                return name
        return "move" if self.crop_rect.contains(pt) else ""

    def cursor_for_handle(self, handle_name: str) -> Qt.CursorShape:
        mapping = {
            ("top_left","bottom_right"): Qt.CursorShape.SizeFDiagCursor,
            ("top_right","bottom_left"): Qt.CursorShape.SizeBDiagCursor,
            ("left_mid","right_mid"):     Qt.CursorShape.SizeHorCursor,
            ("top_mid","bottom_mid"):     Qt.CursorShape.SizeVerCursor,
            ("move",):                    Qt.CursorShape.SizeAllCursor,
        }
        for keys, cursor in mapping.items():
            if handle_name in keys:
                return cursor
        return Qt.CursorShape.ArrowCursor

    def get_final_crop(self) -> QPixmap:
        return self.get_final_cropped_pixmap()

    def accept(self):
        if not self.get_final_cropped_pixmap().isNull():
            self.modified = True
        else:
            self.modified = False
        super().accept()

    def handleAccept(self):
        cropped_pix = self.get_final_cropped_pixmap()
        self.cropAccepted.emit(cropped_pix)
    
    def handleCancel(self):
        self.cropCancelled.emit()

    def handleParentResize(self):
        # Called by the parent when resized while this overlay is open.
        self.setGeometry(self.parent().rect())
        self.update_scaled_pixmap()
        # Option A: Re-center the crop rect (loses any partial crop)
        self.init_default_crop()
        self.update()



# ------------------------------------------------------------------------
# Overlay Content: Split-view + 200px sliders + Apply/Cancel + mouse/keys
# ------------------------------------------------------------------------
class SharpnessOverlayContent(QWidget):
    """
    Split‐view preview of sharpen effect, with 200px sliders plus live
    numeric readouts, Apply/Cancel buttons, mouse‐drag divider, mouse‐pan,
    arrow keys, and mouse‐wheel zoom centered under the cursor.
    """
    def __init__(self, parent, original_pixmap: QPixmap, current_language="en"):
        super().__init__(parent)
        self.orig_pix     = original_pixmap
        self.current      = original_pixmap
        self.split_x      = 0.5
        self.btn_h        = 35
        self.ctrl_margin  = 20

        # Divider vs pan
        self._dragging_divider = False
        self._panning_image    = False
        self.pan_x = 0
        self.pan_y = 0

        # Zoom
        self.zoom     = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 4.0

        # accept keys & wheel
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        QTimer.singleShot(0, lambda: self.setFocus(Qt.FocusReason.ActiveWindowFocusReason))

        t = translations.get(current_language, translations["en"])

        # ─── Radius slider + label ────────────────────────────────
        lbl_r = QLabel(t["radius"], self)
        self.sld_r = QSlider(Qt.Orientation.Horizontal, self)
        self.sld_r.setRange(1, 50)
        self.sld_r.setValue(1)
        self.sld_r.setFixedWidth(200)
        self.sld_r.valueChanged.connect(self._on_radius_changed)

        # live readout (2-digit, monospaced width)
        self.lbl_r_value = QLabel(f"{self.sld_r.value():2d}", self)
        self.lbl_r_value.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        self.lbl_r_value.setFixedWidth(30)
        self.lbl_r_value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ─── Amount slider + label ────────────────────────────────
        lbl_a = QLabel(t["amount"], self)
        self.sld_a = QSlider(Qt.Orientation.Horizontal, self)
        self.sld_a.setRange(1, 300)
        self.sld_a.setValue(100)
        self.sld_a.setFixedWidth(200)
        self.sld_a.valueChanged.connect(self._on_amount_changed)

        # live readout (3-digit, monospaced width)
        self.lbl_a_value = QLabel(f"{self.sld_a.value():3d}", self)
        self.lbl_a_value.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        self.lbl_a_value.setFixedWidth(40)
        self.lbl_a_value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ─── Apply / Cancel buttons ───────────────────────────────────
        btn_apply  = QPushButton(t["apply"],  self)
        btn_cancel = QPushButton(t["cancel"], self)
        for btn, col in ((btn_apply, "#007BFF"), (btn_cancel, "#DC3545")):
            btn.setFixedSize(120, self.btn_h)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col};
                    color: white;
                    border-radius: 6px;
                    font-size: 15px;
                }}
                QPushButton:hover {{
                    background-color: {'#0056b3' if col=='#007BFF' else '#B22222'};
                }}
            """)
        btn_apply.clicked.connect(lambda: parent.onAccepted(self))
        btn_cancel.clicked.connect(lambda: parent.onCancelled())

        # ─── Layout ───────────────────────────────────────────────────
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, self.ctrl_margin)
        main.addStretch()

        bottom = QHBoxLayout()
        bottom.addStretch()
        # Radius: label, slider, value
        bottom.addWidget(lbl_r)
        bottom.addWidget(self.sld_r, 2)
        bottom.addWidget(self.lbl_r_value)
        bottom.addSpacing(10)
        # Amount: label, slider, value
        bottom.addWidget(lbl_a)
        bottom.addWidget(self.sld_a, 2)
        bottom.addWidget(self.lbl_a_value)
        bottom.addSpacing(20)
        bottom.addWidget(btn_apply)
        bottom.addSpacing(10)
        bottom.addWidget(btn_cancel)
        bottom.addStretch()
        main.addLayout(bottom)


        # initial preview render
        self._update_preview()

    def _on_radius_changed(self, v: int):
        self.lbl_r_value.setText(str(v))
        self._update_preview()

    def _on_amount_changed(self, v: int):
        # show as percentage
        self.lbl_a_value.setText(str(v))
        self._update_preview()

    def paintEvent(self, event):
        painter = QPainter(self)
        # full-black background
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        if self.current.isNull():
            return

        # leave room for controls + ctrl_margin
        total_ctrl_h = self.btn_h + 10  # 10 px internal margin
        W = self.width()
        H = self.height() - total_ctrl_h - self.ctrl_margin

        pw, ph     = self.current.width(), self.current.height()
        base_scale = min(W / pw, H / ph)
        scale      = base_scale * self.zoom
        nw, nh     = int(pw * scale), int(ph * scale)

        # center + pan
        ox = (W - nw) // 2 + int(self.pan_x)
        oy = (H - nh) // 2 + int(self.pan_y)
        split_px = ox + int(self.split_x * nw)

        # draw sharpened (left) half
        painter.save()
        painter.setClipRect(ox, oy, split_px - ox, nh)
        painter.drawPixmap(ox, oy,
            self.current.scaled(nw, nh,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
        painter.restore()

        # draw original (right) half
        painter.save()
        painter.setClipRect(split_px, oy, ox + nw - split_px, nh)
        painter.drawPixmap(ox, oy,
            self.orig_pix.scaled(nw, nh,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )
        painter.restore()

        # draw the split‐line
        pen = QPen(QColor("white"), 2)
        painter.setPen(pen)
        painter.drawLine(split_px, oy, split_px, oy + nh)

        # draw black bar behind controls, lifted by ctrl_margin
        bar_top = self.height() - (total_ctrl_h + self.ctrl_margin)
        painter.fillRect(
            0,
            bar_top,
            self.width(),
            total_ctrl_h + self.ctrl_margin,
            QColor(0, 0, 0)
        )

    def keyPressEvent(self, ev: QKeyEvent):
        k = ev.key()
        if k == Qt.Key.Key_Left:
            self.split_x = max(0.0, self.split_x - 0.02)
            self.update()
        elif k == Qt.Key.Key_Right:
            self.split_x = min(1.0, self.split_x + 0.02)
            self.update()

        # Up/Down adjust sharpen AMOUNT by 10 steps
        elif k == Qt.Key.Key_Up:
            self.sld_a.setValue(min(self.sld_a.maximum(), self.sld_a.value() + 10))
        elif k == Qt.Key.Key_Down:
            self.sld_a.setValue(max(self.sld_a.minimum(), self.sld_a.value() - 10))

        # '0' resets *only* Radius & Amount sliders
        elif k == Qt.Key.Key_0:
            self.sld_r.setValue(1)
            self.sld_a.setValue(100)
            self._on_radius_changed(self.sld_r.value())
            self._on_amount_changed(self.sld_a.value())

        # Backspace resets *only* zoom/pan to fit
        elif k == Qt.Key.Key_Backspace:
            self.zoom  = 1.0
            self.pan_x = 0
            self.pan_y = 0
            self.update()

        # Escape cancels (same as Cancel button)
        elif k == Qt.Key.Key_Escape:
            self.parent().onCancelled()

        else:
            super().keyPressEvent(ev)


    def mouseDoubleClickEvent(self, ev: QMouseEvent):
        """
        Reset only zoom/pan to initial state on double-click.
        (Sliders and divider remain untouched.)
        """
        self.zoom  = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update()
        ev.accept()


    def wheelEvent(self, ev: QWheelEvent):
        # Determine zoom factor
        delta    = ev.angleDelta().y()
        factor   = 1.1 if delta > 0 else 1 / 1.1
        old_zoom = self.zoom
        new_zoom = max(self.min_zoom, min(self.max_zoom, old_zoom * factor))
        if new_zoom == old_zoom:
            return

        # Widget and image dimensions (leave controls + margin)
        total_ctrl_h = self.btn_h + 10
        W = self.width()
        H = self.height() - total_ctrl_h - self.ctrl_margin
        pw, ph = self.current.width(), self.current.height()
        base   = min(W / pw, H / ph)

        # Compute current scale and origin
        old_scale = base * old_zoom
        ox_old    = (W - pw * old_scale) / 2 + self.pan_x
        oy_old    = (H - ph * old_scale) / 2 + self.pan_y

        # Mouse position
        mx, my = ev.position().x(), ev.position().y()

        # Image-space under cursor
        rel_x = (mx - ox_old) / old_scale
        rel_y = (my - oy_old) / old_scale

        # Apply zoom
        self.zoom = new_zoom
        new_scale = base * new_zoom

        # Centered origin
        ox_center = (W - pw * new_scale) / 2
        oy_center = (H - ph * new_scale) / 2

        # Recompute pan
        self.pan_x = mx - (ox_center + rel_x * new_scale)
        self.pan_y = my - (oy_center + rel_y * new_scale)

        self.update()
        ev.accept()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            total_ctrl_h = self.btn_h + 10
            W = self.width()
            H = self.height() - total_ctrl_h - self.ctrl_margin
            pw, ph = self.current.width(), self.current.height()
            base_scale = min(W / pw, H / ph) * self.zoom
            nw = pw * base_scale
            ox = (W - nw) / 2 + self.pan_x
            split_px = ox + self.split_x * nw

            x = ev.position().x()
            if abs(x - split_px) <= 5:
                self._dragging_divider = True
                self._press_x = x
                self._start_split = self.split_x
            else:
                self._panning_image = True
                self._pan_start_x = x
                self._pan_start_y = ev.position().y()
                self._pan_orig_x  = self.pan_x
                self._pan_orig_y  = self.pan_y

            ev.accept()
        else:
            super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent):
        # If over any interactive child (slider, button, label), show arrow
        w = self.childAt(ev.position().toPoint())
        if isinstance(w, (QSlider, QPushButton, QLabel)):
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return super().mouseMoveEvent(ev)

        # If over the bottom “menu” region, also show arrow
        bottom_y = self.height() - (self.btn_h + self.ctrl_margin)
        if ev.position().y() >= bottom_y:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return super().mouseMoveEvent(ev)

        # Otherwise, calculate split/pan and show the hand or resize cursor
        total_ctrl_h = self.btn_h + 10
        W = self.width()
        H = self.height() - total_ctrl_h - self.ctrl_margin
        pw, ph = self.current.width(), self.current.height()
        scale  = min(W / pw, H / ph) * self.zoom
        nw     = pw * scale
        ox     = (W - nw) / 2 + self.pan_x
        split_px = ox + self.split_x * nw

        if not self._dragging_divider and not self._panning_image:
            mx = ev.position().x()
            if abs(mx - split_px) <= 5:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.OpenHandCursor)

        # Now handle actual dragging/panning
        if self._dragging_divider:
            dx = ev.position().x() - self._press_x
            self.split_x = max(0.0, min(1.0, self._start_split + dx / nw))
            self.update()
            ev.accept()
        elif self._panning_image and (ev.buttons() & Qt.MouseButton.LeftButton):
            dx = ev.position().x() - self._pan_start_x
            dy = ev.position().y() - self._pan_start_y
            self.pan_x = self._pan_orig_x + dx
            self.pan_y = self._pan_orig_y + dy
            self.update()
            ev.accept()
        else:
            super().mouseMoveEvent(ev)


    def leaveEvent(self, ev):
        self.unsetCursor()
        super().leaveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._dragging_divider:
                self._dragging_divider = False
                ev.accept()
            elif self._panning_image:
                self._panning_image = False
                ev.accept()
            else:
                super().mouseReleaseEvent(ev)
        else:
            super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev: QMouseEvent):
        """
        Reset only zoom/pan to initial state on double-click.
        (Sliders and divider remain untouched.)
        """
        self.zoom  = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update()
        ev.accept()

    def _update_preview(self):
        r = self.sld_r.value()
        a = self.sld_a.value() / 100.0
        self.current = sharpen_cv2(self.orig_pix, r, a)
        self.update()

# ------------------------------------------------------------------------
# Full-Screen Sharpness Overlay tying it all together
# ------------------------------------------------------------------------
class SharpnessOverlay(QWidget):
    def __init__(self, owner, original_pixmap: QPixmap, current_language="en"):
        super().__init__(owner)
        self._viewer = owner
        self.orig_pix = original_pixmap
        self.setObjectName("SharpnessOverlay")

        # 1) Cover the owner's area
        if owner:
            self.setGeometry(owner.rect())

        # 2) Frameless, always-on-top, solid black
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground,   False)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), Qt.GlobalColor.black)
        self.setPalette(pal)

        # 3) Disable the viewer’s shortcuts & floating menu
        if hasattr(owner, "disable_all_shortcuts"):
            owner.disable_all_shortcuts()
        if getattr(owner, "floating_menu", None):
            owner.floating_menu.setEnabled(False)

        # 4) Grab the keyboard so no child can steal it
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.grabKeyboard()

        # 5) Embed the content
        self.content = SharpnessOverlayContent(self, original_pixmap, current_language)
        self.content.setGeometry(self.rect())

        # 6) Show
        self.show()

    def keyPressEvent(self, ev: QKeyEvent):
        key = ev.key()

        # 1) Escape closes the overlay
        if key == Qt.Key.Key_Escape:
            self.onCancelled()
            ev.accept()

        # 2) All of these should go to the content:
        #    arrows, '0', and Backspace
        elif key in (
            Qt.Key.Key_Left, Qt.Key.Key_Right,
            Qt.Key.Key_Up,   Qt.Key.Key_Down,
            Qt.Key.Key_0,    Qt.Key.Key_Backspace
        ):
            self.content.keyPressEvent(ev)

        # 3) Anything else: default behavior
        else:
            super().keyPressEvent(ev)

    def onAccepted(self, content: SharpnessOverlayContent):
        """
        Called when the user clicks 'Apply' in the sharpness content.
        Snap an undo, apply the sharpen, then close.
        """
        # 1) Read slider values
        r = content.sld_r.value()
        a = content.sld_a.value() / 100.0

        # 2) Snapshot undo now
        self._viewer.push_undo_state(from_crop=False)

        # 3) Perform the sharpen (using your existing function)
        result = sharpen_cv2(self.orig_pix, r, a)

        # 4) Apply the sharpen result (this must not push another undo)
        self._viewer.applySharpenResult(result)

        # 5) Release keyboard and close overlay
        self.releaseKeyboard()
        self.close()

    def onCancelled(self):
        # release the grab and close, just like crop
        self.releaseKeyboard()
        self.close()

    def closeEvent(self, ev):
        # restore shortcuts & menu on the viewer
        owner = self.parent()
        if hasattr(owner, "enable_all_shortcuts"):
            owner.enable_all_shortcuts()
        if getattr(owner, "floating_menu", None):
            owner.floating_menu.setEnabled(True)
        super().closeEvent(ev)


# ------------------------------------------------------------------------
# PhotoViewer
# ------------------------------------------------------------------------
class PhotoViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        QApplication.instance().setStyleSheet("""
            QMainWindow { background-color: black; }
            QScrollArea { background-color: black; border: none; }
            QWidget { background-color: black; }
        """)
        self.image_modified = False
        self.hide_navigation_controls = False
        self.unsaved_crop = None
        self._history = {}
        self._modified = {} 
        self._current_path = None
        self.current_filter = "all"
        self.current_language = "en"
        lang = self.current_language
        t = translations[lang]
        self.export_thread = None
        self.setAcceptDrops(True)
        self.setWindowTitle(translations[self.current_language]["photo_viewer_title"])
        self.setGeometry(100, 100, 1024, 768)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.image_files = []
        self.current_index = -1
        self.current_directory = None
        self.favorites = set()
        self.compare_set = set()
        self.config_file = get_config_file()
        self.is_fullscreen = False
        self.sort_by_date = False
        self.show_all_images = True
        self.reset_zoom_on_new_image = True
        self.image_brightness = {}
        self.rotate_all = False
        self.global_rotation = 0 
        self.image_rotations = {}
        self.menu_dock_left = True
        self.loop_navigation = False
        self._first_image_loaded = True
        self.white_balance_enabled = False
        self.white_balance_gains = (1.0, 1.0, 1.0)
        self.load_config()
        self.init_ui()
        self.init_floating_controls()
        self.set_theme(self.theme)
        self.update_floating_controls()
        self.update_favorite_count()
        self.setup_shortcuts()
        self.floating_menu.settings_button.clicked.connect(self.open_settings_overlay)
        self.floating_menu.brightness_button.clicked.connect(self.open_brightness_overlay)
        self.show()
        QTimer.singleShot(0, self.initialize_viewer)
        self.updateLanguage()
        self.all_tooltips = []
        self.loading_in_progress = False

    def toggle_fullscreen(self, *, make_cover: bool = True):
        """
        make_cover = True   → use fade-out overlay (❌, F11, etc.)
        make_cover = False  → leave FS with NO overlay (click-away path)
        """
        leaving = self.isFullScreen()

        # 1 – pre-exit repaint (to flush GPU buffer)
        if leaving:
            self.image_viewer.viewport().repaint()
            self.repaint()
            QCoreApplication.processEvents(
                QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )

        self.hide_all_tooltips()
        self.setUpdatesEnabled(False)

        cover = None
        if make_cover:
            cover = self.create_screenshot_cover()
            QCoreApplication.processEvents()

        # 2 – switch state
        if not leaving:
            # ---- ENTER ----
            self.stored_geometry = self.geometry()
            super().showFullScreen()
            self.is_fullscreen = True
            self.float_exit.show()

        else:
            # ---- EXIT ----
            if not make_cover:
                # hide window immediately so no flash
                self.setWindowOpacity(0.0)

            super().showNormal()
            if hasattr(self, "stored_geometry"):
                self.setGeometry(self.stored_geometry)
            self.is_fullscreen = False
            self.float_exit.hide()

            if not make_cover:
                # restore opacity and force a repaint
                self.setWindowOpacity(1.0)
                self.image_viewer.viewport().repaint()
                self.repaint()
                QCoreApplication.processEvents(
                    QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                )

        self.setUpdatesEnabled(True)

        # 3 – fade overlay (only if we created one)
        if cover is not None:
            effect = QGraphicsOpacityEffect(cover)
            cover.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", cover)
            anim.setDuration(50)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            anim.finished.connect(lambda: (cover.hide(), cover.deleteLater()))
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

        # 4 – house-keeping
        if not self.floating_menu.isVisible():
            self.floating_menu.show()
        if self.image_viewer.auto_fit:
            self.image_viewer.adjustToFit()
        self.update_floating_controls()

    # ------------------------------------------------------------------
    # 2)  exit_fullscreen  – used by ❌ button and F11
    # ------------------------------------------------------------------
    def exit_fullscreen(self):
        """Leave fullscreen via the normal overlay path."""
        if self.isFullScreen():
            self.toggle_fullscreen(make_cover=True)


    # ------------------------------------------------------------------
    # 3)  _leave_fullscreen_clickaway  – helper for the click-away path
    # ------------------------------------------------------------------
    def _leave_fullscreen_clickaway(self):
        """
        Called once after the window loses focus while in FS.

        Now we just call the same exit path as the ❌ button,
        so we get the identical fade-out overlay instead of a flash.
        """
        if self.isFullScreen():
            self.exit_fullscreen()

    # ------------------------------------------------------------------
    # 4)  event  – detects “click‑away” focus loss
    # ------------------------------------------------------------------
    def event(self, ev):
        if ev.type() == QEvent.Type.WindowDeactivate and self.isFullScreen():
            # give the new frame a few ms to appear before we exit
            QTimer.singleShot(10, self._leave_fullscreen_clickaway)
            return True
        return super().event(ev)

    def create_screenshot_cover(self):
        viewport = self.image_viewer.viewport()
        if isinstance(viewport, QOpenGLWidget):
            viewport.makeCurrent()
            from OpenGL import GL
            GL.glFinish()
            viewport.doneCurrent()

        pix = self.grab()
        label = QLabel(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        label.setPixmap(pix)
        label.setGeometry(self.geometry())
        label.show()
        label.raise_()
        return label

    def updateLanguage(self):
        lang = self.current_language
        t = translations[lang]
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            current_image = self.image_files[self.current_index]
            filename = os.path.basename(current_image)
            position = f"({self.current_index + 1}/{len(self.image_files)})"
            self.setWindowTitle(f"{t['photo_viewer_title']} - {filename}  {position}")
        else:
            self.setWindowTitle(t["photo_viewer_title"])
        self.floating_menu.update_tooltips(t)

    def open_settings_overlay(self):
        if self.windowState() & Qt.WindowState.WindowMinimized:
            self.showNormal()
            QTimer.singleShot(200, self.open_settings_overlay)
            return

        # If already open, bring to front
        if hasattr(self, "settings_overlay") and self.settings_overlay is not None:
            if self.settings_overlay.isVisible():
                self.settings_overlay.raise_()
                return
        else:
            self.settings_overlay = None

        # Disable shortcuts & floating menu while open
        self.disable_all_shortcuts()
        self.floating_menu.setEnabled(False)

        # Create the overlay
        self.settings_overlay = BaseOverlay(self, overlay_name="SettingsOverlay", bg_color="rgba(0, 0, 0, 150)")
        self.settings_overlay.setGeometry(self.rect())

        # Close on ESC
        def overlay_keypress(event):
            if event.key() == Qt.Key.Key_Escape:
                self.close_settings_overlay()
            else:
                event.ignore()
        self.settings_overlay.keyPressEvent = overlay_keypress

        class DraggableContainer(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

                self.drag_offset = None

            def mousePressEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    self.drag_offset = event.position().toPoint()
                super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                if self.drag_offset is not None:
                    new_pos = self.mapToParent(event.position().toPoint() - self.drag_offset)
                    self.move(new_pos)
                super().mouseMoveEvent(event)

            def mouseReleaseEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    self.drag_offset = None
                super().mouseReleaseEvent(event)


        container = DraggableContainer(self.settings_overlay)
        container.setObjectName("SettingsContainer")
        container.setStyleSheet("""
            QWidget#SettingsContainer {
                background-color: rgba(0, 0, 0, 200);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QLabel {
                background-color: rgba(50, 50, 50, 200);
                color: white;
                font-size: 16px;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 6px;
                padding: 8px;
            }
            QCheckBox, QRadioButton {
                min-height: 30px;
                background-color: rgba(50, 50, 50, 200);
                color: white;
                font-size: 16px;
                border-radius: 6px;
                padding: 6px;
            }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 1px solid #777;
                background: #333;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background-color: #3498DB;
                border: 1px solid #3498DB;
            }
            QPushButton {
                background-color: #555555;
                color: white;
                border-radius: 6px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #777777;
            }
            QPushButton#closeSettingsBtn {
                background-color: #DC3545;
            }
            QPushButton#closeSettingsBtn:hover {
                background-color: #B22222;
            }
        """)
        # Make sure it can't exceed overlay size
        container.setMinimumSize(250, 250)
        container.setMaximumSize(
            self.settings_overlay.width() - 40,
            self.settings_overlay.height() - 40
        )

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        t = translations[self.current_language]

        # Title label
        title_label = QLabel(t["options_title"], container)
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            background-color: rgba(25,25,25,200);
            color: white;
            border: 1px solid rgba(25,25,25,200);
            border-radius: 6px;
            padding: 8px;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_label.setFixedHeight(40)
        layout.addWidget(title_label)
        layout.addSpacing(5)        

        # Build checkboxes for settings
        settings_items = [
            (t["reset_zoom"], self.reset_zoom_on_new_image, lambda st: self.set_reset_zoom(bool(st))),
            (t["rotate_all_option"], self.rotate_all, lambda st: self.set_rotate_all(bool(st))),
            (t["show_filename"], self.show_filename, lambda st: self.set_show_filename(bool(st))),
            (t["load_last_folder"], getattr(self, "load_last_folder", False), lambda st: self.set_load_last_folder(bool(st))),
            (t["loop_navigation"], self.loop_navigation, lambda st: self.set_loop_navigation(bool(st))),
            (t["menu_dock_left"], self.menu_dock_left, lambda st: self.toggle_menu_dock(bool(st))),
            #(t["hide_navigation_controls"], self.hide_navigation_controls, lambda st: self.set_hide_navigation_controls(bool(st)))
        ]
        # Sort them by label, so they appear consistently
        sorted_items = sorted(settings_items, key=lambda item: item[0].lower())
        for label_text, init_state, callback in sorted_items:
            cb = QCheckBox(label_text, container)
            cb.setChecked(init_state)
            cb.stateChanged.connect(lambda st, c=callback: c(st))
            layout.addWidget(cb)
        layout.addSpacing(5)

        # --- Sorting Options Section (within your existing settings overlay) ---
        # 'container' is the QWidget for the overlay and 'layout' its QVBoxLayout.
        # Use the translation dictionary 't' defined earlier in open_settings_overlay.

        sort_label = QLabel(t["sort_by"], container)
        sort_label.setStyleSheet("""
            font-size: 18px;
            background-color: rgba(25,25,25,200);
            color: white;
            border: 1px solid rgba(25,25,25,200);
            border-radius: 6px;
            padding: 8px;
        """)
        sort_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        sort_label.setFixedHeight(40)
        layout.addWidget(sort_label)

        # Define a common style for both combo boxes.
        combo_style = """
        QComboBox {
            min-height: 30px;
            background-color: rgba(50,50,50,200);
            color: white;
            font-size: 16px;
            border-radius: 6px;
            padding: 6px 10px;
            border: 1px solid rgba(255,255,255,30);
        }
        QComboBox:hover {
            background-color: #0078D7;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox::down-arrow {
            image: url("data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOCIgdmlld0JveD0iMCAwIDEyIDgiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTEgMSAxMSAxIDYgNyIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiLz48L3N2Zz4=");
        }
        QComboBox QAbstractItemView {
            background-color: rgba(50,50,50,200);
            color: white;
            selection-background-color: rgba(85,85,85,0.7);
            border: 1px solid rgba(255,255,255,30);
        }
        """

        # --- Criterion ComboBox ---
        criterion_combo = OverlayComboBox(container)
        criterion_combo.setStyleSheet(combo_style)
        criterion_combo.addItem(t["sort_file_name"], "file_name")
        criterion_combo.addItem(t["sort_date_modified"], "date_modified")
        criterion_combo.addItem(t["sort_size"], "size")
        if self.sort_option == "file_name":
            criterion_combo.setCurrentIndex(0)
        elif self.sort_option == "date_modified":
            criterion_combo.setCurrentIndex(1)
        elif self.sort_option == "size":
            criterion_combo.setCurrentIndex(2)
        criterion_combo.currentIndexChanged.connect(
            lambda index: self.set_sort_option(criterion_combo.itemData(index))
        )
        layout.addWidget(criterion_combo)

        # --- Order ComboBox ---
        order_combo = OverlayComboBox(container)
        order_combo.setStyleSheet(combo_style)
        order_combo.addItem(t["sort_ascending"], True)
        order_combo.addItem(t["sort_descending"], False)
        if self.sort_ascending:
            order_combo.setCurrentIndex(0)
        else:
            order_combo.setCurrentIndex(1)
        order_combo.currentIndexChanged.connect(
            lambda index: self.set_sort_ascending(order_combo.itemData(index))
        )
        layout.addWidget(order_combo)

        # --- Theme selector ---
        theme_label = QLabel(t["theme"], container)
        theme_label.setStyleSheet("""
            font-size: 18px;
            background-color: rgba(25,25,25,200);
            color: white;
            border: 1px solid rgba(25,25,25,200);
            border-radius: 6px;
            padding: 8px;
        """)
        theme_label.setFixedHeight(38)
        layout.addWidget(theme_label)

        theme_combo = OverlayComboBox(container)
        theme_combo.setStyleSheet(combo_style)
        theme_combo.addItem(t["black"],     "black")
        theme_combo.addItem(t["dark_grey"], "dark_grey")
        theme_combo.addItem(t["inkstone"],  "inkstone")
        
        # select current theme
        keys = ["black", "dark_grey", "inkstone"]
        current = self.theme if self.theme in keys else "black"
        idx = keys.index(current)
        theme_combo.setCurrentIndex(idx)

        theme_combo.currentIndexChanged.connect(
            lambda i: self.set_theme(theme_combo.itemData(i))
        )
        layout.addWidget(theme_combo)
        layout.addSpacing(5)

        # --- Language Options Section ---
        lang_label = QLabel(t["language"], container)
        lang_label.setStyleSheet("""
            font-size: 18px;
            background-color: rgba(25,25,25,200);
            color: white;
            border: 1px solid rgba(25,25,25,200);
            border-radius: 6px;
            padding: 8px;
        """)
        lang_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lang_label.setFixedHeight(40)
        layout.addWidget(lang_label)

        lang_layout = QHBoxLayout()
        layout.addLayout(lang_layout)

        radio_en = QRadioButton("English", container)
        radio_es = QRadioButton("Español", container)
        lang_layout.addWidget(radio_en)
        lang_layout.addWidget(radio_es)

        # Group language radio buttons in their own QButtonGroup:
        lang_group = QButtonGroup(container)
        lang_group.addButton(radio_en)
        lang_group.addButton(radio_es)

        if self.current_language == "en":
            radio_en.setChecked(True)
        else:
            radio_es.setChecked(True)

        radio_en.toggled.connect(lambda checked: self.set_language("en") if checked else None)
        radio_es.toggled.connect(lambda checked: self.set_language("es") if checked else None)

        layout.addWidget(radio_en)
        layout.addWidget(radio_es)
        layout.addStretch()

        # Buttons at bottom
        about_btn = QPushButton(t["about_button"], container)
        help_btn = QPushButton(t["help_button"], container)
        close_btn = QPushButton(t["close_label"], container)
        close_btn.setObjectName("closeSettingsBtn")
        for btn in (about_btn, help_btn, close_btn):
            btn.setMinimumHeight(34)
        layout.addSpacing(5)
        layout.addWidget(about_btn)
        layout.addSpacing(2)
        layout.addWidget(help_btn)
        layout.addSpacing(2)
        layout.addWidget(close_btn)

        about_btn.clicked.connect(self.open_about_overlay)
        help_btn.clicked.connect(self.open_help_overlay)
        close_btn.clicked.connect(self.close_settings_overlay)

        # Clicking outside => close
        def overlay_mousePressEvent(ev):
            if not container.geometry().contains(ev.pos()):
                self.close_settings_overlay()
            else:
                ev.accept()
        self.settings_overlay.mousePressEvent = overlay_mousePressEvent

        # We want the first appearance to anchor near the settings button:
        container.hide()
        self.settings_overlay.show()
        self.settings_overlay.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

        self.settings_overlay.raise_()
        QApplication.processEvents()


        container.adjustSize()
        # Then place it next to the floating_menu.settings_button, like before
        btn_local_pos = self.floating_menu.settings_button.pos()
        pos_in_main = self.floating_menu.mapTo(self, btn_local_pos)
        x = pos_in_main.x() + self.floating_menu.settings_button.width() + 15
        y = pos_in_main.y() - 170
        # If that goes offscreen, clamp it:
        if y < 0:
            y = 0
        if x + container.width() > self.settings_overlay.width():
            x = self.settings_overlay.width() - container.width() - 20
        if y + container.height() > self.settings_overlay.height():
            y = self.settings_overlay.height() - container.height() - 20

        container.move(x, y)
        container.show()
        container.raise_()

    
    def close_settings_overlay(self):
        if hasattr(self, "settings_overlay") and self.settings_overlay is not None:
            self.settings_overlay.hide()
            self.settings_overlay.deleteLater()
            self.settings_overlay = None
        self.enable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(True)

    def set_sort_option(self, option: str):
        # 1) Remember the current image and filter
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            current_image = self.image_files[self.current_index]
        else:
            current_image = None
        active_filter = getattr(self, 'current_filter', 'all')

        # 2) Change sort criterion and persist
        self.sort_option = option
        self.save_config()

        # 3) Get the full list, sorted
        sorted_full = self.get_all_images()

        # 4) Re-apply the active filter
        if active_filter == 'favorites':
            new_files = [f for f in sorted_full if f in self.favorites]
        elif active_filter == 'non_favorites':
            new_files = [f for f in sorted_full if f not in self.favorites]
        elif active_filter == 'compare':
            new_files = [f for f in sorted_full if f in self.compare_set]
        else:
            new_files = sorted_full

        # 5) Restore index to the same image if possible
        if current_image and current_image in new_files:
            self.current_index = new_files.index(current_image)
        else:
            # If we fell off, go back to 0
            self.current_index = 0

        # 6) Swap in the newly-sorted, re-filtered list
        self.image_files = new_files

        # 7) Refresh the view, preserving zoom/pan on the same image
        self.show_image(reset_zoom=False, preserve_zoom=True)

        # 8) And now update the floating filter icon/count & position
        self.update_favorite_count()
        self.update_floating_controls()


    def set_sort_ascending(self, ascending: bool):
        # 1) Remember the current image and filter
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            current_image = self.image_files[self.current_index]
        else:
            current_image = None
        active_filter = getattr(self, 'current_filter', 'all')

        # 2) Change sort order and persist
        self.sort_ascending = ascending
        self.save_config()

        # 3) Get the full list, sorted
        sorted_full = self.get_all_images()

        # 4) Re-apply the active filter
        if active_filter == 'favorites':
            new_files = [f for f in sorted_full if f in self.favorites]
        elif active_filter == 'non_favorites':
            new_files = [f for f in sorted_full if f not in self.favorites]
        elif active_filter == 'compare':
            new_files = [f for f in sorted_full if f in self.compare_set]
        else:
            new_files = sorted_full

        # 5) Restore index to the same image if possible
        if current_image and current_image in new_files:
            self.current_index = new_files.index(current_image)
        else:
            self.current_index = 0

        # 6) Swap in the newly-sorted, re-filtered list
        self.image_files = new_files

        # 7) Refresh the view, preserving zoom/pan on the same image
        self.show_image(reset_zoom=False, preserve_zoom=True)

        # 8) And now update the floating filter icon/count & position
        self.update_favorite_count()
        self.update_floating_controls()


    def open_help_overlay(self):
        """
        Opens a Help overlay with only the Shortcuts section.
        Closes any open settings overlay.
        """
        # Close settings overlay if it is open
        if hasattr(self, "settings_overlay") and self.settings_overlay is not None:
            self.close_settings_overlay()

        # If help overlay is already open, raise it and return.
        if hasattr(self, "help_overlay") and self.help_overlay is not None:
            if self.help_overlay.isVisible():
                self.help_overlay.raise_()
                return
        else:
            self.help_overlay = None

        # Use current language strings
        lang = self.current_language
        t = translations.get(lang, translations["en"])

        # Define the shortcut categories with sorted tuples.
        # (Note: we store our rows as dictionaries for later use in the search.)
        SHORTCUT_CATEGORIES = [
            (
                t["help_cat_favorites_compare"],
                 [
                    (t["shortcut_mark_favorite_key"], t["shortcut_mark_favorite_key_desc"]),
                    (t["shortcut_toggle_favorite_filter_key"], t["shortcut_toggle_favorite_filter_desc"]),
                    (t["shortcut_toggle_compare_key"], t["shortcut_toggle_compare_desc"]),
                    (t["shortcut_toggle_compare_filter_key"], t["shortcut_toggle_compare_filter_desc"]),
                ]
            ),
            (
                t["help_cat_advanced_options"],
                sorted([
                    (t["shortcut_clear_compare_key"], t["shortcut_clear_compare_desc"]),
                    (t["shortcut_clear_favorites_key"], t["shortcut_clear_favorites_desc"]),
                    (t["shortcut_delete_non_favorites_key"], t["shortcut_delete_non_favorites_desc"]),
                ], key=lambda item: item[0].lower())
            ), 
            (
                t["help_cat_navigation"],
                sorted([
                     (t["shortcut_left_key"], t["shortcut_left_desc"]),
                     (t["shortcut_right_key"], t["shortcut_right_desc"]),
                     (t["shortcut_home_key"], t["shortcut_home_desc"]),
                     (t["shortcut_end_key"], t["shortcut_end_desc"]),
                     (t["shortcut_loop_key"], t["shortcut_loop_desc"]),
                ], key=lambda item: item[0].lower())
            ),
            (
                t["help_cat_zoom_pan"],
                sorted([
                    (t["shortcut_pan_up_key"], t["shortcut_pan_up_desc"]),
                    (t["shortcut_pan_down_key"], t["shortcut_pan_down_desc"]),
                    (t["shortcut_pan_left_key"], t["shortcut_pan_left_desc"]),
                    (t["shortcut_pan_right_key"], t["shortcut_pan_right_desc"]),
                    (t["shortcut_zoom_in_key"], t["shortcut_zoom_in_desc"]),
                    (t["shortcut_zoom_out_key"], t["shortcut_zoom_out_desc"]),
                    (t["shortcut_mouse_key"], t["shortcut_mouse_desc"]),
                    (t["shortcut_doubleclick_key"], t["shortcut_doubleclick_desc"]),
                ], key=lambda item: item[0].lower())
            ),
            (
                t["help_cat_file_operations"],
                sorted([
                    (t["shortcut_delete_key"], t["shortcut_delete_desc"]),
                    (t["shortcut_copy_key"], t["shortcut_copy_desc"]),
                    (t["shortcut_save_modified_file_key"], t["shortcut_save_modified_file_desc"]),
                    (t["shortcut_open_key"], t["shortcut_open_desc"]),
                    (t["shortcut_export_key"], t["shortcut_export_desc"]),
                    (t["shortcut_undo_key"], t["shortcut_undo_desc"]),
                    (t["shortcut_redo_key"], t["shortcut_redo_desc"]),

                ], key=lambda item: item[0].lower())
            ),
            (
                t["help_cat_view_toggles"],
                sorted([
                    (t["shortcut_f11_key"], t["shortcut_f11_desc"]),
                    (t["shortcut_escape_key"], t["shortcut_escape_desc"]),
                    (t["shortcut_hide_nav_key"], t["shortcut_hide_nav_desc"]),
                    (t["shortcut_dock_key"], t["shortcut_dock_desc"]),
                    (t["shortcut_show_filename_key"], t["shortcut_show_filename_desc"]),
                    (t["shortcut_reset_zoom_key"], t["shortcut_reset_zoom_desc"]),
                    (t["shortcut_rotate_key"], t["shortcut_rotate_desc"]),
                    (t["shortcut_toggle_menu_key"], t["shortcut_toggle_menu_desc"]),
                ], key=lambda item: item[0].lower())
            ),                        
            (
                t["help_cat_brightness_slider"],
                [
                    (t["shortcut_brightness_key"], t["shortcut_brightness_desc"]),
                    (t["shortcut_brightness_arrow_keys"], t["shortcut_brightness_arrow_desc"]),
                    (t["shortcut_brightness_reset_key"], t["shortcut_brightness_reset_desc"]),
                ],
            ),
            (
                t["help_cat_crop_function"],
                [
                    (t["shortcut_crop_reset_key"], t["shortcut_crop_reset_desc"]),
                    (t["shortcut_crop_increase_large_key"], t["shortcut_crop_increase_large_desc"]),
                    (t["shortcut_crop_decrease_large_key"], t["shortcut_crop_decrease_large_desc"]),
                    (t["shortcut_crop_increase_small_key"], t["shortcut_crop_increase_small_desc"]),
                    (t["shortcut_crop_decrease_small_key"], t["shortcut_crop_decrease_small_desc"]),
                    (t["shortcut_crop_Esc_key"], t["shortcut_crop_Esc_desc"]),
                ]
            ),
            (
                t["help_cat_sharpness_function"],
                [
                    (t["shortcut_sharpness_backspace_key"],   t["shortcut_sharpness_backspace_desc"]),
                    (t["shortcut_sharpness_reset_key"],    t["shortcut_sharpness_reset_desc"]),
                    (t["shortcut_sharpness_split_left"],   t["shortcut_sharpness_split_left_desc"]),
                    (t["shortcut_sharpness_split_right"],  t["shortcut_sharpness_split_right_desc"]),
                    (t["shortcut_sharpness_amount_up"],    t["shortcut_sharpness_amount_up_desc"]),
                    (t["shortcut_sharpness_amount_down"],  t["shortcut_sharpness_amount_down_desc"]),
                    (t["shortcut_sharpness_Esc_key"],   t["shortcut_sharpness_Esc_desc"]),

                ]
            ),                        
        ]

        # Create the overlay with a semi-transparent background.
        self.help_overlay = QWidget(self)
        self.help_overlay.setObjectName("HelpOverlay")
        self.help_overlay.setGeometry(self.rect())
        self.help_overlay.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.help_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.help_overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.help_overlay.setStyleSheet("#HelpOverlay { background-color: rgba(0, 0, 0, 150); }")

        def overlay_keyPressEvent(event):
            if event.key() == Qt.Key.Key_Escape:
                self.close_help_overlay()
            else:
                event.ignore()
        self.help_overlay.keyPressEvent = overlay_keyPressEvent

        # Main container for the help pop-up – using a draggable container.
        container = DraggableContainer(self.help_overlay)
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setObjectName("HelpContainer")
        container.setStyleSheet("""
            QWidget#HelpContainer {
                background-color: rgba(0, 0, 0, 200);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QLabel {
                background-color: transparent;
                color: #fff;
            }
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                background-color: #333333;
                border-radius: 8px;
                padding: 10px 15px;
                margin: 2px;
                font-size: 16px;
                color: white;
            }
            QTabBar::tab:selected {
                background-color: #0056b3;
            }
        """)

        # Instead of forcing a fixed size, set an initial size and use size policies.
        container.resize(1025, 1000)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container.show()
        container.adjustSize()

        # Obtain available screen geometry and set maximum size so it adapts responsively.
        parent_rect = self.rect()  # Use the main window’s rect directly
        margin = 40

        # Clamp container size based on the parent window’s geometry:
        max_width = parent_rect.width() - margin
        max_height = parent_rect.height() - margin
        container.setMaximumSize(max_width, max_height)

        # Center container horizontally; keep a 40px margin at the top:
        x = (parent_rect.width() - container.width()) // 2
        y = 40
        container.move(x, y)

        # Set up the main layout inside the container.
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Create a single-tab QTabWidget containing only the "Shortcuts" tab.
        tab_widget = QTabWidget(container)
        main_layout.addWidget(tab_widget)

        # Shortcuts tab – build the content.
        shortcuts_tab = QWidget()
        shortcuts_tab_layout = QVBoxLayout(shortcuts_tab)
        shortcuts_tab_layout.setContentsMargins(10, 10, 10, 10)
        shortcuts_tab_layout.setSpacing(12)

        # --- Search Row ---
        search_row = QHBoxLayout()
        search_label = QLabel(t["help_search_label"])  # e.g., "🔍 Search Shortcuts:"
        search_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-right: 1px;")
        self.shortcuts_search_line = QLineEdit()
        self.shortcuts_search_line.setPlaceholderText(t["help_search_placeholder"])
        self.shortcuts_search_line.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                font-size: 16px;
                padding: 6px;
                border: 1px solid #444444;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border: 1px solid #666666;
            }
        """)
        self.shortcuts_search_line.setFixedHeight(36)
        search_row.addWidget(search_label, 0, alignment=Qt.AlignmentFlag.AlignVCenter)
        search_row.addWidget(self.shortcuts_search_line, 1)
        shortcuts_tab_layout.addLayout(search_row)

        # --- Scroll Area for the Shortcut Categories ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollBar:vertical {
                background: #333;
                width: 14px;
                margin: 0;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #555;
                min-height: 20px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #777;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        shortcuts_tab_layout.addWidget(scroll_area, 1)

        cat_container = QWidget()
        cat_layout = QVBoxLayout(cat_container)
        cat_layout.setContentsMargins(0, 0, 0, 0)
        cat_layout.setSpacing(20)

        # Clear out the previous shortcut rows list.
        self.shortcut_rows = []

        # Build the categories.
        for category_name, items in SHORTCUT_CATEGORIES:
            cat_label = QLabel(category_name)
            cat_label.setStyleSheet("""
                font-size: 18px;
                font-weight: bold;
                color: #3399ff;
                border-bottom: 1px solid #777;
                margin-bottom: 4px;
                padding-bottom: 8px;
            """)
            cat_layout.addWidget(cat_label)
            for (k, desc) in items:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 4, 0, 4)
                row_layout.setSpacing(12)
                key_label = QLabel(k)
                key_label.setStyleSheet("font-size: 17px; font-weight: bold;")
                key_label.setFixedWidth(130)
                desc_label = QLabel(desc)
                desc_label.setStyleSheet("font-size: 18px;")
                desc_label.setWordWrap(False)
                row_layout.addWidget(key_label, 0, alignment=Qt.AlignmentFlag.AlignLeft)
                row_layout.addWidget(desc_label, 1, alignment=Qt.AlignmentFlag.AlignLeft)
                cat_layout.addWidget(row_widget)
                # Store each row for search filtering.
                self.shortcut_rows.append({
                    "row_widget": row_widget,
                    "key_orig": k,
                    "desc_orig": desc,
                    "category_orig": category_name,
                    "key_label": key_label,
                    "desc_label": desc_label,
                })

        cat_layout.addStretch()
        scroll_area.setWidget(cat_container)

        # Add the shortcuts tab to the tab widget.
        tab_widget.addTab(shortcuts_tab, t["shortcuts_title"])

        # --- Close Button ---
        close_button = QPushButton(t["close_label"], container)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #DC3545;
                color: white;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #B22222;
            }
        """)
        main_layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignCenter)
        close_button.clicked.connect(self.close_help_overlay)

        # Finally, show and raise the overlay.
        container.show()
        self.help_overlay.show()
        self.help_overlay.raise_()

        # Ensure the search bar gets focus immediately.
        QTimer.singleShot(0, lambda: self.shortcuts_search_line.setFocus(Qt.FocusReason.ActiveWindowFocusReason))

        # --- Improved Search Behavior ---
        import re

        def strip_html_and_asterisk(raw_text: str) -> str:
            # Remove any HTML tags
            text_no_tags = re.sub(r'<[^>]*>', '', raw_text)
            # Remove literal asterisks and extra whitespace
            return text_no_tags.replace('*', '').strip()

        def on_shortcuts_search_changed(text):
            text = text.lower().strip()
            for row_info in self.shortcut_rows:
                row_widget = row_info["row_widget"]
                # Clean the key and description text
                key_clean = strip_html_and_asterisk(row_info["key_orig"]).lower()
                desc_clean = strip_html_and_asterisk(row_info["desc_orig"]).lower()
                
                if not text:
                    row_widget.setVisible(True)
                else:
                    if len(text) == 1:
                        # For a single character, show the row only if the key matches exactly.
                        row_widget.setVisible(key_clean == text)
                    else:
                        # For longer search strings, check if the text is anywhere in the key or description.
                        combined = key_clean + " " + desc_clean
                        row_widget.setVisible(text in combined)

        self.shortcuts_search_line.textChanged.connect(on_shortcuts_search_changed)


        # --- Clicking Outside the Container Closes the Overlay ---
        def overlay_mousePressEvent(event):
            if not container.geometry().contains(event.pos()):
                self.close_help_overlay()
            else:
                event.accept()
        self.help_overlay.mousePressEvent = overlay_mousePressEvent

        # Disable shortcuts and the floating menu while the help overlay is open.
        self.disable_all_shortcuts()
        if hasattr(self, "floating_menu"):
            self.floating_menu.setEnabled(False)

    def close_help_overlay(self):
        if hasattr(self, "help_overlay") and self.help_overlay is not None:
            self.help_overlay.hide()
            self.help_overlay.deleteLater()
            self.help_overlay = None
        # Re-enable the shortcuts and floating menu so settings can be re-opened.
        self.enable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(True)

    def open_about_overlay(self):
        """
        Minimal 'About' overlay, matching your other overlays' approach:
         - Disables parent's shortcuts so they can't intercept keys
         - Frameless child widget that covers self.rect()
         - Closes on Esc (QShortcut)
         - Close button is focused so space/enter triggers it
         - Clicking outside the container closes
        """

        # Close the settings overlay if open
        if hasattr(self, "settings_overlay") and self.settings_overlay is not None:
            self.close_settings_overlay()

        # If About overlay already open, bring to front
        if hasattr(self, "about_overlay") and self.about_overlay is not None:
            if self.about_overlay.isVisible():
                self.about_overlay.raise_()
                return
        else:
            self.about_overlay = None

        # Disable all shortcuts in the parent so they don't interfere
        self.disable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(False)

        lang = self.current_language
        t = translations.get(lang, translations["en"])

        # Create a frameless overlay covering self.rect()
        self.about_overlay = QWidget(self)
        self.about_overlay.setObjectName("AboutOverlay")
        self.about_overlay.setGeometry(self.rect())
        self.about_overlay.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.about_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.about_overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.about_overlay.setStyleSheet("#AboutOverlay { background-color: rgba(0, 0, 0, 150); }")

        # QShortcut for Esc, just like your other overlays
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.about_overlay)
        esc_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc_shortcut.activated.connect(self.close_about_overlay)

        # Container for About info
        container = QWidget(self.about_overlay)
        container.setObjectName("AboutContainer")
        container.setStyleSheet("""
            QWidget#AboutContainer {
                background-color: rgba(0, 0, 0, 200);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QLabel {
                background-color: transparent;
                color: white;
                font-size: 16px;
            }
            QPushButton {
                background-color: #555555;
                color: white;
                border-radius: 6px;
                padding: 8px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #777777;
            }
            QPushButton#closeButton {
                background-color: #DC3545;
            }
            QPushButton#closeButton:hover {
                background-color: #B22222;
            }
        """)
        container.setFixedSize(315, 200)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title_label = QLabel(t["about_button"], container)
        title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        version_label = QLabel(t["app_version_label"], container)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        copyright_label = QLabel(t["copyright_label"], container)
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(copyright_label)

        close_btn = QPushButton(t["close_label"], container)
        close_btn.setObjectName("closeButton")
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Ensure space/enter triggers the button:
        close_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        close_btn.setDefault(True)
        close_btn.setAutoDefault(True)
        close_btn.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        close_btn.clicked.connect(self.close_about_overlay)

        container.adjustSize()

        # Center container in overlay
        overlay_w = self.about_overlay.width()
        overlay_h = self.about_overlay.height()
        x = (overlay_w - container.width()) // 2
        y = (overlay_h - container.height()) // 2
        container.move(x, y)
        container.show()

        # Close if clicking outside container
        def about_overlay_mousePressEvent(ev):
            if not container.geometry().contains(ev.pos()):
                self.close_about_overlay()
            else:
                ev.ignore()
        self.about_overlay.mousePressEvent = about_overlay_mousePressEvent

        # Show the overlay
        self.about_overlay.show()
        self.about_overlay.raise_()
        # Make sure it can receive key events (for the QShortcut)
        self.about_overlay.show()
        self.about_overlay.raise_()
        # Explicitly transfer focus to the close button:
        close_btn.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def close_about_overlay(self):
        """
        Close the About overlay and re-enable parent shortcuts.
        """
        if hasattr(self, "about_overlay") and self.about_overlay is not None:
            self.about_overlay.hide()
            self.about_overlay.deleteLater()
            self.about_overlay = None

        # Re-enable shortcuts/floating menu
        self.enable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(True)


    def smooth_scroll_up(self):
        step = int(self.image_viewer.viewport().height() * 0.1)
        self.image_viewer.verticalScrollBar().setValue(
            self.image_viewer.verticalScrollBar().value() - step
        )

    def smooth_scroll_down(self):
        step = int(self.image_viewer.viewport().height() * 0.1)
        self.image_viewer.verticalScrollBar().setValue(
            self.image_viewer.verticalScrollBar().value() + step
        )

    def toggle_menu_dock(self, enabled: bool):
        self.menu_dock_left = enabled
        self.update_scroll_area_margins()
        self.save_config()

    def set_reset_zoom(self, value: bool):
        self.reset_zoom_on_new_image = value
        self.save_config()

    def set_show_filename(self, value: bool):
        self.show_filename = value
        self.save_config()
        if self.show_filename and self.image_files:
            current_image = self.image_files[self.current_index]
            original_path = self.norm_to_original.get(current_image, current_image)
            filename = os.path.basename(original_path)
            position = f"({self.current_index + 1}/{len(self.image_files)})"
            self.filename_label.setText(f"{filename}  {position}")
            self.filename_label.adjustSize()
            self.filename_label.show()
            self.update_filename_position()
        else:
            self.filename_label.hide()

    def set_language(self, lang: str):
        if self.current_language != lang:
            global current_language
            current_language = lang
            self.current_language = lang
            self.save_config()
            self.updateLanguage()


    def initialize_viewer(self):
        if self.menu_dock_left:
            self.update_scroll_area_margins()
            QTimer.singleShot(50, self.restore_dock_menu)
        else:
            self.update_scroll_area_margins()
            self.force_first_image_fit()
            self.update_favorite_count()
            self.show_floating_menu()

    def restore_dock_menu(self):
        self.force_first_image_fit()
        self.update_favorite_count()
        self.show_floating_menu()

    def show_floating_menu(self):
        if not (hasattr(self, "menu_button") and hasattr(self, "floating_menu")):
            return
        self.floating_menu.show()
        QApplication.processEvents()
        left_margin = -5
        top_margin = 20
        self.menu_button.move(left_margin, top_margin)
        bx = self.menu_button.x()
        by = self.menu_button.y()
        bw = self.menu_button.width()
        bh = self.menu_button.height()
        mw = self.floating_menu.width()
        menu_x = bx + (bw - mw) // 2
        menu_y = by + bh + 5
        self.floating_menu.move(menu_x, menu_y)

    def get_all_images(self):
        if self.current_directory and os.path.exists(self.current_directory):
            images_original = [
                os.path.join(self.current_directory, f)
                for f in os.listdir(self.current_directory)
                if f.lower().endswith(('png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp', 'tiff', 'tif'))
            ]
            self.norm_to_original = {}
            for path in images_original:
                normed = os.path.normcase(os.path.abspath(path))
                self.norm_to_original[normed] = path
            images = list(self.norm_to_original.keys())

            # Sort based on the chosen criterion.
            if self.sort_option == "date_modified":
                # sort by modification time
                images.sort(key=lambda p: os.path.getmtime(p))
            elif self.sort_option == "file_name":
                images.sort(key=lambda p: os.path.basename(p).lower())
            elif self.sort_option == "size":
                images.sort(key=lambda p: os.path.getsize(p))

            # Reverse list if sort order is descending.
            if not self.sort_ascending:
                images.reverse()

            return images
        return []


    def update_scroll_area_margins(self):
        dock_width = 80
        container = self.centralWidget()
        if self.menu_dock_left:
            container.layout().setContentsMargins(dock_width, 0, 0, 0)
        else:
            container.layout().setContentsMargins(0, 0, 0, 0)

    def update_favorite_count(self):
        t = translations[self.current_language]
        total_images = len(self.get_all_images())
        favorite_count = len(self.favorites)
        compare_count = len(self.compare_set)
        non_favorite_count = total_images - favorite_count
        layout = self.floating_menu.filter_button.layout()
        if layout is None:
            layout = QVBoxLayout(self.floating_menu.filter_button)
            self.floating_menu.filter_button.setLayout(layout)
        else:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
        # Use the desired filter to determine the icon even if the displayed list fell back to "all".
        desired = self.desired_filter if hasattr(self, 'desired_filter') else self.current_filter
        if desired == "all":
            icon = IconFactory.get_icon("all_images", 36)
            count_text = f"({total_images})"
        elif desired == "favorites":
            icon = IconFactory.get_icon("filled_star", 36)
            count_text = f"({favorite_count})"
        elif desired == "non_favorites":
            icon = IconFactory.get_icon("empty_star", 36)
            count_text = f"({non_favorite_count})"
        elif desired == "compare":
            icon = IconFactory.get_icon("compare", 36)
            count_text = f"({compare_count})"
        else:
            icon = IconFactory.get_icon("all_images", 36)
            count_text = f"({total_images})"
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(36, 36))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        text_label = QLabel(count_text)
        text_label.setStyleSheet("color: white; font-size: 21px;")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(4)
        shadow.setColor(QColor(0, 0, 0))
        shadow.setOffset(1, 1)
        text_label.setGraphicsEffect(shadow)
        layout.addSpacing(2)
        layout.addWidget(text_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.floating_menu.filter_button.setFixedSize(75, 95)

    def open_filter_overlay(self):
        t = translations[self.current_language]
        if hasattr(self, "filter_overlay") and self.filter_overlay is not None:
            if self.filter_overlay.isVisible():
                self.filter_overlay.raise_()
                return
        else:
            self.filter_overlay = None

        self.disable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(False)
        
        # Create the overlay
        self.filter_overlay = BaseOverlay(parent=self, overlay_name="FilterOverlay", bg_color="rgba(0, 0, 0, 150)")
        self.filter_overlay.setObjectName("FilterOverlay")
        self.filter_overlay.setGeometry(self.rect())

        # Determine the current screen using QGuiApplication.screenAt
        current_screen = QGuiApplication.screenAt(self.geometry().center())
        if current_screen and self.filter_overlay.windowHandle():
            self.filter_overlay.windowHandle().setScreen(current_screen)

        def overlay_keypress(event):
            if event.key() == Qt.Key.Key_Escape:
                self.close_filter_overlay()
            else:
                event.ignore()
        self.filter_overlay.keyPressEvent = overlay_keypress

        # Create a container for the filter options
        container = QWidget(self.filter_overlay)
        container.setObjectName("FilterContainer")
        container.setStyleSheet("""
            QWidget#FilterContainer {
                background-color: transparent;
                border-radius: 8px;
            }
            QPushButton {
                background-color: rgba(50, 50, 50, 200);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 16px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: rgba(85, 85, 85, 0.7);
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(5)

        # Create filter option buttons
        all_images_count = len(self.get_all_images())
        fav_count = len(self.favorites)
        nonfav_count = all_images_count - fav_count
        compare_count = len(self.compare_set)

        btn_all = QPushButton(f"{t['all_images']} ({all_images_count})", container)
        btn_all.clicked.connect(lambda: (self.set_image_view("all"), self.close_filter_overlay()))
        layout.addWidget(btn_all)

        btn_fav = QPushButton(f"⭐ {t['favorites']} ({fav_count})", container)
        btn_fav.clicked.connect(lambda: (self.set_image_view("favorites"), self.close_filter_overlay()))
        layout.addWidget(btn_fav)

        btn_non = QPushButton(f"☆ {t['non_favorites']} ({nonfav_count})", container)
        btn_non.clicked.connect(lambda: (self.set_image_view("non_favorites"), self.close_filter_overlay()))
        layout.addWidget(btn_non)

        btn_compare = QPushButton(f"<> {t['compare']} ({compare_count})", container)
        btn_compare.clicked.connect(lambda: (self.set_image_view("compare"), self.close_filter_overlay()))
        layout.addWidget(btn_compare)

        def overlay_mousePressEvent(event):
            if not container.geometry().contains(event.pos()):
                self.close_filter_overlay()
            else:
                event.accept()
        self.filter_overlay.mousePressEvent = overlay_mousePressEvent

        container.hide()
        self.filter_overlay.show()
        self.filter_overlay.raise_()
        self.filter_overlay.setFocus()
        QApplication.processEvents()

        # Position the container relative to the floating menu’s filter button, if available.
        if hasattr(self.floating_menu, "filter_button"):
            btn_rect = self.floating_menu.filter_button.geometry()
            global_top_left = self.floating_menu.mapToGlobal(btn_rect.topLeft())
            # Calculate the desired position relative to the overlay:
            desired_x = global_top_left.x() + btn_rect.width() - 10
            desired_y = global_top_left.y() - 59
            new_pos = self.filter_overlay.mapFromGlobal(QPoint(desired_x, desired_y))
            container.move(new_pos)
        else:
            overlay_rect = self.filter_overlay.rect()
            cont_geo = container.frameGeometry()
            container.move(overlay_rect.center() - cont_geo.center())

        container.show()
        container.raise_()
        QApplication.processEvents()
        # Clamp the container inside the overlay (pass self.filter_overlay as the second argument)
        self.clamp_widget_to_overlay(container, self.filter_overlay)

    def close_filter_overlay(self):
        if hasattr(self, "filter_overlay") and self.filter_overlay is not None:
            self.filter_overlay.hide()
            self.filter_overlay.deleteLater()
            self.filter_overlay = None
        self.enable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(True)

    def open_image_in_path(self):
        # 1) ensure valid image
        if not (self.image_files and 0 <= self.current_index < len(self.image_files)):
            return

        image_path = os.path.abspath(self.image_files[self.current_index])
        if not os.path.exists(image_path):
            self.show_custom_dialog(
                translations[self.current_language]["error_file_not_exist"],
                icon_type="error", buttons="ok"
            )
            return

        try:
            open_folder_and_select_item(image_path)
        except OSError as e:
            msg = translations[self.current_language]["error_open_explorer"].format(str(e))
            self.show_custom_dialog(msg, icon_type="error", buttons="ok")


    def set_rotate_all(self, value: bool):
        was_enabled = self.rotate_all
        self.rotate_all = value
        if was_enabled and not value:
            if 0 <= self.current_index < len(self.image_files):
                current_image = self.image_files[self.current_index]
                current_angle = self.image_rotations.get(current_image, 0)
            else:
                current_image = None
                current_angle = 0
            for img in self.image_files:
                if img != current_image:
                    self.image_rotations[img] = 0
            self.global_rotation = current_angle
            self.show_image()
        self.save_config()

    def rotate_action(self):
        if not self.image_files or self.current_index < 0:
            return
        current_image = self.image_files[self.current_index]
        if self.rotate_all:
            self.global_rotation = (self.global_rotation + 90) % 360
            for img in self.image_files:
                self.image_rotations[img] = self.global_rotation
            self.image_viewer.rotation_angle = self.global_rotation
            self.image_viewer.cached_texture = None
            if self.image_viewer.auto_fit or abs(self.image_viewer.zoom_factor - 1.0) < 0.01:
                self.image_viewer.auto_fit = True
                self.image_viewer.adjustToFit()
            else:
                self.image_viewer.updatePixmap()
        else:
            # Push undo state before rotating.
            self.push_undo_state()
            self.image_viewer.rotate_clockwise()
            new_angle = self.image_viewer.rotation_angle
            self.image_rotations[current_image] = new_angle


    def copy_current_image(self):
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            image_path = self.image_files[self.current_index]
            if not os.path.exists(image_path):
                self.show_custom_dialog(
                    translations[self.current_language]["error_file_not_exist"],
                    icon_type="error",
                    buttons="ok"
                )
                return
            mime_data = QMimeData()
            mime_data.setUrls([QUrl.fromLocalFile(image_path)])
            clipboard = QApplication.clipboard()
            clipboard.setMimeData(mime_data)
            
            # Retrieve the current language translations
            t = translations[self.current_language]
            # Display an ephemeral message indicating success
            self.show_ephemeral_message(t["copy_image_success"])


    def set_image_view(self, filter_mode):
        t = translations.get(self.current_language, translations["en"])
        full_list = self.get_all_images()

        # 1) Remember what’s currently on-screen
        old_current = None
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            old_current = self.image_files[self.current_index]

        # 2) Build the new filtered list
        if filter_mode == "all":
            new_files = full_list

        elif filter_mode == "favorites":
            new_files = [f for f in full_list if f in self.favorites]
            if not new_files:
                self.show_custom_dialog(
                    t["no_favorites_marked"], icon_type="warning", buttons="ok"
                )
                new_files, filter_mode = full_list, "all"

        elif filter_mode == "non_favorites":
            new_files = [f for f in full_list if f not in self.favorites]
            if not new_files:
                self.show_custom_dialog(
                    t["no_non_favorites_marked"], icon_type="warning", buttons="ok"
                )
                new_files, filter_mode = full_list, "all"

        elif filter_mode == "compare":
            new_files = [f for f in full_list if f in self.compare_set]
            if not new_files:
                self.show_custom_dialog(
                    t["no_compare_marked"], icon_type="warning", buttons="ok"
                )
                new_files, filter_mode = full_list, "all"

        else:
            new_files, filter_mode = full_list, "all"

        self.current_filter = filter_mode
        self.image_files    = new_files

        # 3) Compute new index, trying to stay on the same file or its neighbor
        if old_current in new_files:
            new_index = new_files.index(old_current)
        else:
            new_index = None
            if old_current in full_list:
                idx = full_list.index(old_current)
                for i in range(idx + 1, len(full_list)):
                    if full_list[i] in new_files:
                        new_index = new_files.index(full_list[i])
                        break
                if new_index is None:
                    for i in range(idx - 1, -1, -1):
                        if full_list[i] in new_files:
                            new_index = new_files.index(full_list[i])
                            break
            if new_index is None:
                new_index = 0

        self.current_index = new_index

        # 4) If it really is the same file, _only_ refresh UI chrome;
        #    otherwise reload via show_image (which will snap/fetch/etc).
        if old_current and old_current in new_files:
            # — update filter icon/count
            self.update_favorite_count()
            self.update_floating_controls()

            # — update window title + 'filename (i/total)' label
            base = translations[self.current_language]["photo_viewer_title"]
            curr = self.image_files[self.current_index]
            real = self.norm_to_original.get(curr, curr)
            name = os.path.basename(real)
            total = len(self.image_files)
            title = f"{base} - {name} ({self.current_index+1}/{total})"
            if self.windowTitle() != title:
                self.setWindowTitle(title)

            disp = f"{name} ({self.current_index+1}/{total})"
            self.filename_label.setText(disp)
            self.filename_label.adjustSize()
            if self.show_filename:
                self.filename_label.show()
                self.update_filename_position()

        else:
            # real navigation → load/reset zoom according to your settings
            self.show_image(
                reset_zoom=self.reset_zoom_on_new_image,
                preserve_zoom=False
            )
            # after loading, show_image will have updated title/count,
            # but we still need to refresh the filter icon/count:
            self.update_favorite_count()


    def force_first_image_fit(self):
        if self.image_files and self.current_index >= 0:
            self.image_viewer.adjustToFit()
            self.update_floating_controls()

    def init_ui(self):
        container = QWidget()
        self.setCentralWidget(container)
        layout = QHBoxLayout(container)
        self.update_scroll_area_margins()
        self.floating_menu = FloatingMenu(self)
        self.floating_menu.open_button.clicked.connect(self.open_directory)
        self.floating_menu.export_button.clicked.connect(self.open_export_overlay)
        self.floating_menu.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.menu_button = QPushButton(self)
        self.menu_button.setIcon(IconFactory.get_icon("menu", 36))
        self.menu_button.setIconSize(QSize(36, 36))
        self.menu_button.setText("")
        self.menu_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 5px 0px 0px 32px; 
                font-size: 24px;
                min-width: 50px;
                min-height: 50px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: transparent;
            }
        """)
        self.menu_button.setMinimumSize(50, 50)
        self.menu_button.clicked.connect(self.toggle_menu)
        self.menu_button.move(20, 20)
        self.menu_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.image_viewer = AdvancedGraphicsImageViewer(self)
        layout.addWidget(self.image_viewer)
        self.filename_label = QLabel(self)
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.filename_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.5);
            color: white;
            font-size: 23px;
            border-radius: 25px;
            padding-left: 15px;
            padding-right: 15px;
        """)
        self.filename_label.setFixedHeight(50)
        self.filename_label.hide()
        if self.current_directory and os.path.exists(self.current_directory):
            self.load_directory(self.current_directory)
        else:
            self.current_directory = None
            self.image_files = []
            self.favorites = set()
            self.current_index = -1

    def toggle_menu(self):
        if self.floating_menu.isVisible():
            self.floating_menu.hide()
        else:
            self.show_floating_menu()

    def init_floating_controls(self):
        if hasattr(self, "float_favorite") and hasattr(self, "float_exit"):
            return
        self.float_favorite = QPushButton("", self)
        self.float_favorite.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 20px;
                color: white;
                font-size: 24px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.5);
            }
        """)
        self.float_favorite.setFixedSize(50, 50)
        self.float_favorite.setIcon(IconFactory.get_icon("empty_star", 36))
        self.float_favorite.setIconSize(QSize(32, 32))
        self.float_favorite.clicked.connect(self.toggle_favorite)
        self.floating_menu.filter_button.clicked.connect(self.open_filter_overlay)
        self.float_favorite.show()
        self.float_previous = QPushButton("◀", self)
        self.float_previous.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 20px;
                color: white;
                font-size: 24px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.7);
            }
        """)
        self.float_previous.setFixedSize(50, 50)
        self.float_previous.clicked.connect(self.show_previous_image)
        self.float_previous.show()
        self.float_next = QPushButton("▶", self)
        self.float_next.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 20px;
                color: white;
                font-size: 24px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.7);
            }
        """)
        self.float_next.setFixedSize(50, 50)
        self.float_next.clicked.connect(self.show_next_image)
        self.float_next.show()
        self.float_exit = QPushButton(self)
        self.float_exit.setIcon(IconFactory.get_icon("close", 36))
        self.float_exit.setIconSize(QSize(36, 36))
        self.float_exit.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border-radius: 15px;
                padding: 5px;
                min-width: 50px;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: transparent;
            }
        """)
        self.float_exit.setFixedSize(50, 50)
        self.float_exit.clicked.connect(self.toggle_fullscreen)
        self.float_exit.hide()
        try:
            self.floating_menu.rotate_button.clicked.disconnect()
        except Exception:
            pass
        self.floating_menu.rotate_button.clicked.connect(self.rotate_action)
        QTimer.singleShot(100, self.update_floating_controls)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_floating_controls()
        self.update_filename_position()
        if hasattr(self, "settings_overlay") and self.settings_overlay is not None:
            self.close_settings_overlay()
        # New: If a crop overlay is open, let it handle the resize
        if hasattr(self, "crop_overlay") and self.crop_overlay is not None and self.crop_overlay.isVisible():
            self.crop_overlay.handleParentResize()

    def update_floating_controls(self):
        # If the floating controls aren't created yet, exit early.
        if not hasattr(self, "float_favorite"):
            return

        # Should we skip ★ updates right now?
        skip_star = getattr(self, "image_loading", False)

        # 1) Update filename label & window title
        if self.image_files and hasattr(self, "filename_label"):
            raw = self.image_files[self.current_index]
            real = self.norm_to_original.get(raw, raw)
            name = os.path.basename(real)
            pos  = f"({self.current_index+1}/{len(self.image_files)})"

            # Window title
            title = f"{translations[self.current_language]['photo_viewer_title']} - {name} {pos}"
            if self.windowTitle() != title:
                self.setWindowTitle(title)

            # Filename label
            display_text = f"{name} {pos}"
            if self.filename_label.text() != display_text:
                self.filename_label.setText(display_text)
                self.filename_label.adjustSize()
            if self.show_filename:
                self.filename_label.show()
                self.update_filename_position()
            else:
                self.filename_label.hide()

        # 2) If no images are loaded, hide everything
        if not self.image_files:
            self.float_favorite.hide()
            self.float_previous.hide()
            self.float_next.hide()
            self.float_exit.hide()
            return

        # 3) Show nav & ★ controls (positioning done below)
        self.float_previous.show()
        self.float_next    .show()
        self.float_favorite.show()

        # 4) ★-icon update (only when not loading)
        if 0 <= self.current_index < len(self.image_files) and not skip_star:
            raw_current   = self.image_files[self.current_index]
            current_image = os.path.normcase(os.path.abspath(raw_current))
            if current_image in self.favorites:
                self.float_favorite.setIcon(IconFactory.get_icon("filled_star", 36))
            else:
                self.float_favorite.setIcon(IconFactory.get_icon("empty_star", 36))
        elif not skip_star:
            # fallback state
            self.float_favorite.setIcon(IconFactory.get_icon("empty_star", 36))
            self.float_favorite.setText("")

        # 5) Position the star
        star_x = self.width()  - 140
        star_y = self.height() -  75
        self.float_favorite.move(star_x, star_y)

        # 6) Navigation arrows logic (unchanged)
        if self.hide_navigation_controls:
            self.float_previous.hide()
            self.float_next    .hide()
        else:
            if self.loop_navigation:
                self.float_previous.show()
                self.float_next    .show()
            else:
                self.float_previous.setVisible(self.current_index > 0)
                self.float_next    .setVisible(self.current_index < len(self.image_files)-1)

            self.float_previous.move(star_x - 60, star_y)
            self.float_next    .move(star_x + 60, star_y)

        # 7) Fullscreen exit button
        if self.is_fullscreen:
            self.float_exit.move(self.width() - 90, 20)
            self.float_exit.show()
        else:
            self.float_exit.hide()

        # 8) Enable/disable arrows based on availability
        self.float_previous.setEnabled(bool(self.image_files))
        self.float_next    .setEnabled(bool(self.image_files))


    def hide_all_tooltips(self):
        for tip in self.all_tooltips:
            tip.fadeOut()
            tip.hide()
        self.all_tooltips.clear()

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.load_last_folder         = config.get('load_last_folder', False)
                self.current_directory        = config.get('last_directory', None) if self.load_last_folder else None
                self.show_all_images          = config.get('show_all_images', True)
                self.reset_zoom_on_new_image  = config.get('reset_zoom_on_new_image', True)
                self.show_filename            = config.get('show_filename', False)
                self.current_language         = config.get('current_language', "en")
                self.rotate_all               = config.get('rotate_all', False)
                self.menu_dock_left           = config.get('menu_dock_left', True)
                self.loop_navigation          = config.get('loop_navigation', False)
                self.last_index               = config.get('last_index', 0)
                self.sort_option              = config.get('sort_option', 'file_name')
                self.sort_ascending           = config.get('sort_ascending', True)
                self.theme                    = config.get('theme', 'black')
            else:
                self.load_last_folder         = False
                self.current_directory        = None
                self.show_all_images          = True
                self.reset_zoom_on_new_image  = True
                self.show_filename            = False
                self.current_language         = "en"
                self.rotate_all               = False
                self.menu_dock_left           = True
                self.loop_navigation          = False
                self.last_index               = 0
                self.sort_option              = 'file_name'
                self.sort_ascending           = True
                self.theme                    = 'black'
        except Exception as e:
            print(f"Error loading config: {e}")
            self.load_last_folder         = False
            self.current_directory        = None
            self.show_all_images          = True
            self.reset_zoom_on_new_image  = True
            self.show_filename            = False
            self.current_language         = "en"
            self.rotate_all               = False
            self.menu_dock_left           = True
            self.loop_navigation          = False
            self.last_index               = 0
            self.sort_option              = 'file_name'
            self.sort_ascending           = True
            self.theme                    = 'black'

    def save_config(self):
        try:
            config = {
                'load_last_folder':        self.load_last_folder,
                'last_directory':          self.current_directory,
                'show_all_images':         self.show_all_images,
                'reset_zoom_on_new_image': self.reset_zoom_on_new_image,
                'show_filename':           self.show_filename,
                'current_language':        self.current_language,
                'rotate_all':              self.rotate_all,
                'menu_dock_left':          self.menu_dock_left,
                'loop_navigation':         self.loop_navigation,
                'last_index':              self.current_index,
                'sort_option':             self.sort_option,
                'sort_ascending':          self.sort_ascending,
                'theme':                   self.theme,
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def save_marked_images(self):
        if not self.current_directory:
            return
        favorites_list = []
        for fav_path in self.favorites:
            norm_path = os.path.normcase(os.path.abspath(fav_path))
            if os.path.exists(norm_path):
                favorites_list.append({
                    'filename': os.path.basename(norm_path),
                    'full_path': norm_path,
                    'modification_date': os.path.getmtime(norm_path),
                    'starred_at': None
                })
        compare_list = []
        for cmp_path in self.compare_set:
            norm_path = os.path.normcase(os.path.abspath(cmp_path))
            if os.path.exists(norm_path):
                compare_list.append({
                    'filename': os.path.basename(norm_path),
                    'full_path': norm_path,
                    'modification_date': os.path.getmtime(norm_path),
                    'starred_at': None
                })
        if self.sort_by_date:
            favorites_list.sort(key=lambda x: x['modification_date'])
            compare_list.sort(key=lambda x: x['modification_date'])
        else:
            favorites_list.sort(key=lambda x: x['filename'])
            compare_list.sort(key=lambda x: x['filename'])
        data = {
            'directory': self.current_directory,
            'favorites': favorites_list,
            'compare': compare_list
        }
        json_path = os.path.join(self.current_directory, 'Favorites.json')
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.show_custom_dialog(
                f"{translations[self.current_language]['error_loading_image']}\n{str(e)}",
                icon_type="error",
                buttons="ok"
            )

    def setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self.show_previous_image)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self.show_next_image)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, lambda: self.image_viewer._manual_zoom(True))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, lambda: self.image_viewer._manual_zoom(False))
        QShortcut(QKeySequence(Qt.Key.Key_PageUp), self, self.smooth_scroll_up)
        QShortcut(QKeySequence(Qt.Key.Key_PageDown), self, self.smooth_scroll_down)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, self.toggle_favorite)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, self.toggle_favorite)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self.delete_current_image)
        QShortcut(QKeySequence(Qt.Key.Key_F11), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.exit_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, self.backspace_toggle_fit)
        QShortcut(QKeySequence("B"), self, self.toggle_brightness_overlay)
        QShortcut(QKeySequence("C"), self, self.toggle_compare)
        QShortcut(QKeySequence("Shift+C"), self, self.toggle_compare_filter_shortcut)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self.clear_compare)
        QShortcut(QKeySequence("Ctrl+C"), self, self.copy_current_image)
        QShortcut(QKeySequence("D"), self, self.toggle_menu_dock_shortcut)
        QShortcut(QKeySequence("Ctrl+Shift+Delete"), self, self.delete_non_favorites_action)
        QShortcut(QKeySequence("E"), self, self.open_export_overlay)
        QShortcut(QKeySequence("F"), self, self.toggle_favorite)
        QShortcut(QKeySequence("Shift+F"), self, self.toggle_favorites_filter_shortcut)
        QShortcut(QKeySequence("Ctrl+F"), self, self.toggle_favorites_filter_shortcut)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, self.clear_favorites)
        #QShortcut(QKeySequence("H"), self, self.toggle_navigation_controls_shortcut)
        QShortcut(QKeySequence("L"), self, self.toggle_loop_shortcut)
        QShortcut(QKeySequence("M"), self, self.toggle_menu)
        QShortcut(QKeySequence("N"), self, self.toggle_show_filename_shortcut)
        QShortcut(QKeySequence("R"), self, self.rotate_action)
        QShortcut(QKeySequence("S"), self, self.open_directory)
        QShortcut(QKeySequence("Ctrl+S"), self, lambda: self.saveModifiedImage(True))
        QShortcut(QKeySequence("Z"), self, self.toggle_reset_zoom_shortcut)
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_action)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.redo_action)
        QShortcut(QKeySequence(Qt.Key.Key_Home), self, self.go_to_first_image)
        QShortcut(QKeySequence(Qt.Key.Key_End), self, self.go_to_last_image)


    def go_to_first_image(self):
        if self.image_files and self.current_index != 0:
            # Save the currently displayed image as the "previous"
            self.previous_image = self.image_files[self.current_index]
            self.current_index = 0
            self.show_image()

    def go_to_last_image(self):
        if self.image_files and self.current_index != len(self.image_files) - 1:
            # Save the currently displayed image as the "previous"
            self.previous_image = self.image_files[self.current_index]
            self.current_index = len(self.image_files) - 1
            self.show_image()
        

    def toggle_menu_dock_shortcut(self):
        self.menu_dock_left = not self.menu_dock_left
        self.update_scroll_area_margins()
        self.save_config()
        t = translations[self.current_language]
        message = t["menu_dock_enabled_message"] if self.menu_dock_left else t["menu_dock_disabled_message"]
        self.show_ephemeral_message(message)

    def toggle_show_filename_shortcut(self):
        self.set_show_filename(not self.show_filename)
        t = translations[self.current_language]
        message = t["filename_display_enabled_message"] if self.show_filename else t["filename_display_disabled_message"]
        self.show_ephemeral_message(message)

    def toggle_reset_zoom_shortcut(self):
        new_value = not self.reset_zoom_on_new_image
        self.reset_zoom_on_new_image = new_value
        self.save_config()
        t = translations[self.current_language]
        if new_value:
            self.show_ephemeral_message(t["reset_zoom_enabled_message"])
        else:
            self.show_ephemeral_message(t["reset_zoom_disabled_message"])

    def open_directory(self):
        t = translations[self.current_language]
        self.dialog = QFileDialog(self, t["select_folder"])
        # Allow multiple selection
        self.dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        self.dialog.setNameFilter("Images (*.png *.jpg *.jpeg *.tif *.tiff *.webp *.bmp *.gif)")
        self.dialog.setViewMode(QFileDialog.ViewMode.List)
        if self.current_directory and os.path.exists(self.current_directory):
            self.dialog.setDirectory(self.current_directory)
        else:
            user_home = os.path.expanduser("~")
            self.dialog.setDirectory(user_home)
        if self.dialog.exec():
            selected_files = self.dialog.selectedFiles()
            if not selected_files:
                return
            # Assume all selected files are in the same folder.
            # Use the last selected file as the "primary" selection.
            chosen_file = selected_files[0]
            chosen_folder = os.path.dirname(chosen_file)
            images_in_folder = [
                f for f in os.listdir(chosen_folder)
                if f.lower().endswith(('png', 'jpg', 'jpeg', 'tif', 'tiff', 'webp', 'bmp', 'gif'))
            ]
            if not images_in_folder:
                self.show_custom_dialog(
                    t["folder_no_images"],
                    icon_type="warning",
                    buttons="ok"
                )
                self.dialog.selectFile("")
                return
            self.load_directory(chosen_folder, selected_file=chosen_file)

    def set_load_last_folder(self, value: bool):
        self.load_last_folder = value
        self.save_config()

    def load_directory(self, directory, selected_file=None, do_show=True):
        # ——— Clear all per-image history when loading a new folder ———
        self._history.clear()
        self._modified.clear()
        self._current_path = None
        # ————————————————————————————————————————————————————————

        # Unsaved‐crop check (unchanged)
        if self.unsaved_crop is not None:
            if not self.prompt_unsaved_crop_warning():
                return
            self.unsaved_crop = None

        # If no valid directory, reset state
        if not directory or not os.path.exists(directory):
            self.current_directory = None
            self.image_files = []
            self.favorites = set()
            self.current_index = -1
            self.save_config()
            self.update_favorite_count()
            return

        # Set up new directory & reset filters
        prev_filter = getattr(self, "current_filter", "all")
        self.current_directory = directory
        if prev_filter != "all":
            self.show_ephemeral_message(translations[self.current_language]["filter_reset_to_all"])
        self.current_filter = "all"
        self.show_all_images = True

        # Reload image list
        self.image_files = self.get_all_images()
        self.favorites = set()
        self.load_marked_images()

        # Choose starting index
        if self.image_files:
            norm_selected = (
                os.path.normcase(os.path.normpath(selected_file))
                if selected_file else None
            )
            norm_images = [os.path.normcase(os.path.normpath(p)) for p in self.image_files]
            if norm_selected and norm_selected in norm_images:
                self.current_index = norm_images.index(norm_selected)
            else:
                self.current_index = getattr(self, "last_index", 0)
            if do_show:
                self.show_image()

        # Final UI updates
        self.save_config()
        self.update_favorite_count()
        self.update_floating_controls()

    def show_image(self, reset_zoom=None, preserve_zoom=False):
        # ——— Per-image history & modified-flag setup ———
        if self.image_files:
            path = self.image_files[self.current_index]
            self._current_path = path
            self._history.setdefault(path, {"undo": [], "redo": []})
            self.image_modified = self._modified.get(path, False)
        else:
            self._current_path = None
            self.image_modified = False

        # update undo/redo buttons early
        self._update_undo_redo_actions()

        if reset_zoom is None:
            reset_zoom = self.reset_zoom_on_new_image

        if not self.image_files:
            self.image_viewer.clear()
            self.current_index = -1
            self.setWindowTitle(translations[self.current_language]["photo_viewer_title"])
            return

        # rotation & brightness setup
        if self.rotate_all:
            angle = self.global_rotation
        else:
            angle  = self.image_rotations.get(path, 0)
            bright = self.image_brightness.get(path, 1.0)
            self.image_viewer.desired_rotation   = angle
            self.image_viewer.desired_brightness = bright

        # ——— Phase 1: mark loading so star updates are skipped ———
        self.image_loading = True

        # ——— Phase 2: preload neighbors into cache ———
        from PyQt6.QtCore import QThreadPool
        for neighbor_index in (self.current_index - 1, self.current_index + 1):
            if 0 <= neighbor_index < len(self.image_files):
                neighbor_path = self.image_files[neighbor_index]
                loader = ImageLoaderRunnable(neighbor_path)
                QThreadPool.globalInstance().start(loader)

        # ——— Phase 3: display current image (cache-first) ———
        cache = getattr(ImageLoaderRunnable, "_pixmap_cache", {})
        viewer = self.image_viewer
        if path in cache:
            # immediate show from cache
            viewer.load_counter = getattr(viewer, "load_counter", 0) + 1
            viewer.current_load_id = viewer.load_counter
            viewer.onImageLoaded(cache[path], reset_zoom, preserve_zoom, viewer.current_load_id)
        else:
            # fallback to threaded load
            viewer.setImage(path, reset_zoom, preserve_zoom)

        # ——— Phase 4: refresh controls ———
        self.update_floating_controls()



    def update_window_title_and_label(self, image_path):
        t = translations[self.current_language]
        original_path = self.norm_to_original.get(image_path, image_path)
        filename = os.path.basename(original_path)
        total = len(self.image_files)
        position_str = f"({self.current_index + 1}/{total})" if total else ""
        self.setWindowTitle(f"{t['photo_viewer_title']} - {filename}  {position_str}")
        if self.show_filename:
            self.filename_label.setText(f"{filename}  {position_str}")
            self.filename_label.adjustSize()
            self.filename_label.show()
            self.update_filename_position()
        else:
            self.filename_label.hide()

    def show_next_image(self):
        if self.unsaved_crop is not None:
            # If there are unsaved crop modifications, warn the user.
            if not self.prompt_unsaved_crop_warning():
                return
            else:
                self.unsaved_crop = None

        if not self.image_files:
            return
        self.previous_image = self.image_files[self.current_index]
        if self.current_index == len(self.image_files) - 1 and not self.loop_navigation:
            return
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
        elif self.loop_navigation:
            self.current_index = 0
        self.show_image()
        
    def show_previous_image(self):
        if self.unsaved_crop is not None:
            if not self.prompt_unsaved_crop_warning():
                return
            else:
                self.unsaved_crop = None

        if not self.image_files:
            return
        self.previous_image = self.image_files[self.current_index]
        if self.current_index == 0 and not self.loop_navigation:
            return
        if self.current_index > 0:
            self.current_index -= 1
        elif self.loop_navigation:
            self.current_index = len(self.image_files) - 1
        self.show_image()

    def toggle_favorite(self):
        # 1) Don’t do anything while an image is loading
        if getattr(self, "image_loading", False):
            return

        # 2) Guard against invalid index
        if not self.image_files or not (0 <= self.current_index < len(self.image_files)):
            return

        current_image = self.image_files[self.current_index]

        # 3) Toggle in your set
        if current_image in self.favorites:
            self.favorites.remove(current_image)
            toggled_off = True
        else:
            self.favorites.add(current_image)
            toggled_off = False

        self.save_marked_images()
        self.update_favorite_count()

        # 4) Handle your filtered views exactly as before:
        if self.current_filter == "favorites":
            if toggled_off:
                # rebuild the favorites list
                new_filtered = [img for img in self.get_all_images() if img in self.favorites]
                if not new_filtered:
                    self.set_image_view("all")
                else:
                    # keep or wrap the index
                    if self.current_index < len(new_filtered):
                        new_idx = self.current_index
                    else:
                        new_idx = 0 if self.loop_navigation else self.current_index - 1
                    self.image_files   = new_filtered
                    self.current_index = new_idx
                self.show_image(reset_zoom=self.reset_zoom_on_new_image,
                                preserve_zoom=False)
            else:
                self.show_image(reset_zoom=False, preserve_zoom=True)
            return

        if self.current_filter == "non_favorites":
            if not toggled_off:
                # moved out of non-favs
                old_index = self.current_index
                full_list = self.get_all_images()
                non_favs  = [img for img in full_list if img not in self.favorites]

                if non_favs:
                    if self.loop_navigation:
                        new_idx = old_index % len(non_favs)
                    else:
                        if old_index < len(non_favs):
                            new_idx = old_index
                        else:
                            new_idx = len(non_favs) - 1
                    self.image_files   = non_favs
                    self.current_index = new_idx
                else:
                    # No non-favorites remain: revert to "all" view and stay on this image
                    self.set_image_view("all")  # updates filter, counts, controls
                    if current_image in self.image_files:
                        self.current_index = self.image_files.index(current_image)
                    else:
                        self.current_index = 0

                self.show_image(reset_zoom=self.reset_zoom_on_new_image,
                                preserve_zoom=False)
            else:
                # just un‐marked in non_favs: keep zoom
                self.show_image(reset_zoom=False, preserve_zoom=True)
            return

        # 5) In the “all” filter we **never** reload or re‐zoom the picture—
        #    we only need to update that little star icon in the corner.
        self.update_floating_controls()

    def clear_favorites(self):
        if hasattr(self, "context_menu_overlay") and self.context_menu_overlay is not None:
            self.context_menu_overlay.close()
            self.context_menu_overlay = None
        t = translations.get(self.current_language, translations["en"])
        if not self.favorites:
            self.show_custom_dialog(
                t["no_favorites_to_clear"],
                icon_type="warning",
                buttons="ok"
            )
            return
        favorite_count = len(self.favorites)
        confirm = self.show_custom_dialog(
            t["clear_favorites_confirm"].format(count=favorite_count),
            icon_type="warning",
            buttons="yesno"
        )

        if confirm != QDialog.DialogCode.Accepted:
            return
        self.favorites.clear()
        self.save_marked_images()  # Persist changes to Favorites.json
        self.update_favorite_count()
        self.update_floating_controls()
        if getattr(self, "current_filter", "all") == "favorites":
            self.set_image_view("all")
        self.show_ephemeral_message(t["favorites_cleared"])


    def load_marked_images(self):
        self.favorites = set()
        self.compare_set = set()
        if not self.current_directory:
            return
        json_path = os.path.join(self.current_directory, 'Favorites.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('directory') == self.current_directory:
                    self.favorites = {
                        os.path.normcase(os.path.abspath(item['full_path']))
                        for item in data.get('favorites', [])
                    }
                    self.compare_set = {
                        os.path.normcase(os.path.abspath(item['full_path']))
                        for item in data.get('compare', [])
                    }
            except Exception as e:
                print(f"Error loading marked images: {e}")

    def get_display_filename(self):
        current_image = self.image_files[self.current_index]
        directory = os.path.dirname(current_image)
        filename_lower = os.path.basename(current_image).lower()
        try:
            for filename in os.listdir(directory):
                if filename.lower() == filename_lower:
                    return filename
        except Exception:
            pass
        return os.path.basename(current_image)

    def delete_current_image(self):
        if not self.image_files or self.current_index < 0:
            return

        t = translations[self.current_language]
        # Save the current filtered index for the non-fallback case.
        old_index_filtered = self.current_index
        current_image = self.image_files[self.current_index]

        # Also determine where this image sits in the full list BEFORE deletion.
        full_list_before = self.get_all_images()
        try:
            old_full_index = full_list_before.index(current_image)
        except ValueError:
            old_full_index = 0

        if not os.path.exists(current_image):
            self.show_custom_dialog(
                t["error_file_not_exist"],
                icon_type="error",
                buttons="ok"
            )
            return

        confirm = self.show_custom_dialog(
            t["delete_image_confirm"].format(current_image=self.get_display_filename()),
            icon_type="warning",
            buttons="yesno"
        )
        if confirm != QDialog.DialogCode.Accepted:
            return

        try:
            # 1) Move to trash
            send2trash.send2trash(os.path.abspath(current_image))

            # 2) Remove from the filtered list in memory
            self.image_files.pop(self.current_index)

            # 3) If it was a favorite, drop it
            if current_image in self.favorites:
                self.favorites.remove(current_image)

            # 4) If it was in compare, drop it too
            if current_image in self.compare_set:
                self.compare_set.remove(current_image)

            # 5) Persist both sets exactly once
            self.save_marked_images()

            # 6) Decide next image to show
            if not self.image_files:
                # Fell out of the filtered list; reset to “all” mode
                full_list_after = self.get_all_images()
                self.current_filter = "all"
                self.image_files = full_list_after
                if full_list_after:
                    # pick based on old_full_index
                    if old_full_index < len(full_list_after):
                        new_index = old_full_index
                    else:
                        new_index = 0 if self.loop_navigation else max(0, old_full_index - 1)
                    self.current_index = new_index
                    self.show_image(reset_zoom=self.reset_zoom_on_new_image)
                else:
                    # no images remain at all
                    self.image_viewer.clear()
                    self.current_index = -1
                    self.filename_label.hide()
                    self.float_favorite.setIcon(IconFactory.get_icon("empty_star", 36))
                    self.setWindowTitle(t["photo_viewer_title"])
            else:
                # still have images in the current filtered view
                if old_index_filtered < len(self.image_files):
                    new_index = old_index_filtered
                else:
                    new_index = 0 if self.loop_navigation else max(0, old_index_filtered - 1)
                self.current_index = new_index
                self.show_image(reset_zoom=self.reset_zoom_on_new_image)

            # 7) Refresh UI counts and controls
            self.update_favorite_count()
            self.update_floating_controls()

        except Exception as e:
            self.show_custom_dialog(
                f"{t['error_loading_image']}\n{str(e)}",
                icon_type="error",
                buttons="ok"
            )


    def open_export_overlay(self):
        t = translations[self.current_language]
        if not self.favorites:
            self.show_custom_dialog(
                t["no_favorites_to_export"],
                icon_type="warning",
                buttons="ok",
                anchor_widget=self.floating_menu.export_button
            )
            return
        self.disable_all_shortcuts()
        if hasattr(self, "export_thread") and self.export_thread is not None and self.export_thread.isRunning():
            return
        self.export_overlay = BaseOverlay(parent=self, overlay_name="ExportOverlay", bg_color="rgba(0, 0, 0, 150)")
        self.export_overlay.setObjectName("ExportOverlay")
        def overlay_keypress(event):
            if event.key() == Qt.Key.Key_Escape:
                event.accept()
                self.close_export_overlay()
            else:
                event.ignore()
        self.export_overlay.keyPressEvent = overlay_keypress
        container = QWidget(self.export_overlay)
        container.setObjectName("ExportContainer")
        container.setStyleSheet("""
            QWidget#ExportContainer {
                background-color: rgba(0, 0, 0, 200);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QLabel {
                background-color: rgba(50, 50, 50, 200);
                color: white;
                font-size: 15px;
                border-radius: 6px;
            }
            QLineEdit {
                background-color: rgba(50, 50, 50, 200);
                color: white;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 6px;
                font-size: 15px;
                padding: 6px 10px;
            }
            QPushButton#exportBtn {
                background-color: #007BFF;
                color: white;
                border-radius: 6px;
                font-size: 15px;
                padding: 8px 12px;
            }
            QPushButton#exportBtn:hover {
                background-color: #0056b3;
            }
            QPushButton#cancelBtn {
                background-color: #DC3545;
                color: white;
                border-radius: 6px;
                font-size: 15px;
                padding: 8px 12px;
            }
            QPushButton#cancelBtn:hover {
                background-color: #B22222;
            }
        """)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)
        title_label = QLabel(t["export_dialog_title"], container)
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            background-color: rgba(25,25,25,200);
            color: white;
            border: 1px solid rgba(25,25,25,200);
            border-radius: 6px;
            padding: 8px;
        """)
        main_layout.addWidget(title_label)
        text_input = QLineEdit(container)
        text_input.setText(t["default_folder"])
        text_input.selectAll()
        main_layout.addWidget(text_input)
        button_layout = QHBoxLayout()
        main_layout.addLayout(button_layout)
        export_text = f"{t['export_favorites']} ({len(self.favorites)})"
        ok_button = QPushButton(export_text, container)
        ok_button.setObjectName("exportBtn")
        ok_button.setFixedHeight(38)
        button_layout.addWidget(ok_button)
        cancel_button = QPushButton(t["cancel"], container)
        cancel_button.setObjectName("cancelBtn")
        cancel_button.setFixedHeight(38)
        button_layout.addWidget(cancel_button)
        ok_button.setDefault(True)
        ok_button.setAutoDefault(True)
        def is_valid_folder_name(name: str) -> bool:
            invalid_chars = '<>:"/\\|?*'
            reserved_names = {
                'CON','PRN','AUX','NUL','COM1','COM2','COM3','COM4',
                'COM5','COM6','COM7','COM8','COM9','LPT1','LPT2',
                'LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9'
            }
            if not 1 <= len(name) <= 50:
                return False
            if any(char in invalid_chars for char in name):
                return False
            if name.upper() in reserved_names:
                return False
            if name.startswith((' ', '.')) or name.endswith((' ', '.')):
                return False
            return True
        def do_export():
            folder_name = text_input.text().strip()
            if not folder_name:
                self.show_custom_dialog(t["folder_name_empty"], icon_type="warning", buttons="ok",
                                        anchor_widget=self.floating_menu.export_button)
                return
            if not is_valid_folder_name(folder_name):
                self.show_custom_dialog(t["folder_name_invalid"], icon_type="error", buttons="ok",
                                        anchor_widget=self.floating_menu.export_button)
                return
            export_dir = os.path.join(self.current_directory, folder_name)
            if os.path.exists(export_dir):
                confirm = self.show_custom_dialog(
                    t["folder_exists_confirm"].format(folder_name=folder_name),
                    icon_type="warning", buttons="yesno",
                )
                if confirm != QDialog.DialogCode.Accepted:
                    return
            try:
                os.makedirs(export_dir, exist_ok=True)
            except Exception as e:
                self.show_custom_dialog(f"Error creating folder: {e}", icon_type="error", buttons="ok")
                return
            progress_overlay = OverlayProgressDialog(
                t["export_progress_title"],
                t["export_progress_message"],
                parent=self
            )
            progress_overlay.setValue(0)
            progress_overlay.show()
            progress_overlay.raise_()
            self.close_export_overlay()
            self.export_worker = ExportWorker(self.favorites, export_dir, self.norm_to_original)
            self.export_thread = QThread()
            self.export_worker.moveToThread(self.export_thread)
            self.export_worker.progressChanged.connect(progress_overlay.setValue)
            progress_overlay.cancelButton.clicked.connect(self.export_worker.cancel)
            def on_finished(count):
                progress_overlay.hide()
                progress_overlay.deleteLater()
                self.show_custom_dialog(
                    t["export_success"].format(count=count, folder_name=folder_name),
                    icon_type="info", buttons="ok"
                )
                self.export_thread.quit()
                self.export_thread.wait()
                self.export_thread = None
                self.export_worker = None
            self.export_worker.finished.connect(on_finished)
            def on_error(err):
                progress_overlay.hide()
                progress_overlay.deleteLater()
                self.show_custom_dialog(f"Error: {err}", icon_type="error", buttons="ok")
                self.export_thread.quit()
                self.export_thread.wait()
                self.export_thread = None
                self.export_worker = None
            self.export_worker.errorOccurred.connect(on_error)
            self.export_thread.started.connect(self.export_worker.run)
            self.export_thread.start()
        ok_button.clicked.connect(do_export)
        cancel_button.clicked.connect(self.close_export_overlay)
        def export_overlay_mousePressEvent(event):
            if not container.geometry().contains(event.pos()):
                self.close_export_overlay()
            else:
                event.accept()
        self.export_overlay.mousePressEvent = export_overlay_mousePressEvent
        container.hide()
        self.export_overlay.show()
        self.export_overlay.raise_()
        self.export_overlay.setFocus()
        QApplication.processEvents()
        button_rect = self.floating_menu.export_button.geometry()
        global_pos = self.floating_menu.export_button.mapToGlobal(QPoint(button_rect.width() + 10, 0))
        container.move(self.export_overlay.mapFromGlobal(global_pos))
        container.show()
        QTimer.singleShot(0, lambda: text_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason))

    def close_export_overlay(self):
        if hasattr(self, "export_overlay") and self.export_overlay is not None:
            self.export_overlay.hide()
            self.export_overlay.deleteLater()
            self.export_overlay = None
        self.enable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(True)

    def update_filename_position(self):
        if not self.filename_label.isVisible():
            return
        star_geo = self.float_favorite.geometry()
        label_size = self.filename_label.sizeHint()
        left_margin = 75
        x = star_geo.x() - label_size.width() - left_margin
        y = star_geo.y() + (star_geo.height() - label_size.height()) // 3
        self.filename_label.setGeometry(x, y, label_size.width(), label_size.height())

    def toggle_brightness_overlay(self):
        if hasattr(self, "brightness_overlay") and self.brightness_overlay is not None and self.brightness_overlay.isVisible():
            self.close_brightness_overlay()
        else:
            self.open_brightness_overlay()


    def open_brightness_overlay(self):
        t = translations[self.current_language]

        # 1) Disable shortcuts & floating menu
        self.disable_all_shortcuts()
        if getattr(self, "floating_menu", None):
            self.floating_menu.setEnabled(False)

        # 2) If overlay already exists and is visible, just raise it
        if getattr(self, "brightness_overlay", None) and self.brightness_overlay.isVisible():
            self.brightness_overlay.raise_()
            return
        self.brightness_overlay = None

        # 3) Create the BaseOverlay
        self.brightness_overlay = BaseOverlay(
            parent=self,
            overlay_name="BrightnessOverlay",
            bg_color="rgba(0, 0, 0, 150)"
        )
        self.brightness_overlay.setObjectName("BrightnessOverlay")
        self.brightness_overlay.setGeometry(self.rect())

        # 4) Intercept B/Escape to close
        def overlay_key_press(event):
            if event.key() in (Qt.Key.Key_B, Qt.Key.Key_Escape):
                self.close_brightness_overlay()
            else:
                QWidget.keyPressEvent(self.brightness_overlay, event)
        self.brightness_overlay.keyPressEvent = overlay_key_press

        # 5) Build centered container
        container = QWidget(self.brightness_overlay)
        container.setObjectName("BrightnessContainer")
        container.setStyleSheet("""
            QWidget#BrightnessContainer {
                background-color: rgba(0, 0, 0, 200);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QLabel { background-color: transparent; color: white; font-size: 16px; }
            QSlider { background-color: transparent; }
        """)
        container.setFixedSize(250, 80)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        label = QLabel(t["brightness"], container)
        label.setStyleSheet("font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label)

        # 6) Create & expose the slider
        slider = QSlider(Qt.Orientation.Horizontal, container)
        slider.setTracking(True)
        slider.setRange(-100, 100)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(50)
        slider.setSingleStep(1)
        layout.addWidget(slider)
        self.brightness_slider = slider

        # 7) Initialize slider to current brightness
        gamma_now = self.image_viewer.brightness_factor
        slider.setValue(int((1.0 - gamma_now) * 200))

        # 8) Capture the initial state for undo (but do NOT push yet)
        self._brightness_initial_state = {
            "pixmap":          self.image_viewer.original_pixmap.copy(),
            "rotation":        self.image_viewer.rotation_angle,
            "brightness":      self.image_viewer.brightness_factor,
            "image_modified":  self.image_modified,
            "from_crop":       False,
        }
        # flag to ensure we push only once
        self._brightness_after_pushed = False

        # 9) Suppress auto‐fit during dragging
        self.image_viewer._suppress_adjust = True

        # 10) Live‐update handler — only setBrightness(), no extra repaint
        def on_value_changed(value):
            gamma = 1.0 - (value / 200.0)
            # setBrightness clears compare‐mode & texture cache and repaints
            self.image_viewer.setBrightness(gamma)
            # persist per‐path if desired
            curr = getattr(self, "_current_path", None)
            if curr:
                self.image_brightness[curr] = gamma

        slider.valueChanged.connect(on_value_changed)

        # 11) Custom “0” key to reset
        def custom_key_press(event):
            if event.key() == Qt.Key.Key_0:
                slider.setValue(0)
                on_value_changed(0)
                event.accept()
            else:
                QSlider.keyPressEvent(slider, event)
        slider.keyPressEvent = custom_key_press

        # 12) Snap & push *only the initial* state on first real change
        def on_slider_released():
            val = slider.value()
            for target in (-100, -50, 0, 50, 100):
                if abs(val - target) <= 5:
                    slider.setValue(target)
                    on_value_changed(target)
                    break

            if not self._brightness_after_pushed:
                path = getattr(self, "_current_path", None)
                if path and path in self._history:
                    hist = self._history[path]
                    hist["undo"].append(self._brightness_initial_state)
                    hist["redo"].clear()
                self._brightness_after_pushed = True

        slider.sliderReleased.connect(on_slider_released)

        # 13) Position container and show everything
        if getattr(self, "floating_menu", None) and hasattr(self.floating_menu, "brightness_button"):
            btn = self.floating_menu.brightness_button
            center = btn.mapToGlobal(btn.rect().center())
            geo = container.frameGeometry()
            gap = 15
            x = center.x() + btn.width()//2 + gap
            y = center.y() - geo.height()//2
            container.move(self.brightness_overlay.mapFromGlobal(QPoint(x, y)))
        else:
            o = self.brightness_overlay.rect()
            g = container.frameGeometry()
            container.move(o.center() - g.center())

        container.show()
        self.brightness_overlay.show()
        self.brightness_overlay.raise_()
        QTimer.singleShot(0, lambda: slider.setFocus(Qt.FocusReason.ActiveWindowFocusReason))

        # 14) Close on outside click
        def brightness_overlay_mousePressEvent(event):
            if not container.geometry().contains(event.pos()):
                self.close_brightness_overlay()
            else:
                event.accept()
        self.brightness_overlay.mousePressEvent = brightness_overlay_mousePressEvent

        # 15) Clamp & finalize
        self.clamp_widget_to_overlay(container, self.brightness_overlay)
        QApplication.processEvents()


    def close_brightness_overlay(self):
        # 1) Tear down the overlay
        if getattr(self, "brightness_overlay", None):
            self.brightness_overlay.hide()
            self.brightness_overlay.deleteLater()
            self.brightness_overlay = None

        # 2) Remove the slider reference
        if getattr(self, "brightness_slider", None):
            del self.brightness_slider

        # 3) Restore our original auto_fit state
        prev = getattr(self.image_viewer, "_saved_auto_fit", None)
        if prev is not None:
            self.image_viewer.auto_fit = prev
            del self.image_viewer._saved_auto_fit

        # 4) Re-enable shortcuts & floating menu
        self.enable_all_shortcuts()
        if getattr(self, "floating_menu", None):
            self.floating_menu.setEnabled(True)

        # 5) Clean up temp undo vars
        if hasattr(self, "_brightness_initial_state"):
            del self._brightness_initial_state
        if hasattr(self, "_brightness_after_pushed"):
            del self._brightness_after_pushed



    def disable_all_shortcuts(self):
        from PyQt6.QtGui import QShortcut
        for sc in self.findChildren(QShortcut):
            sc.setEnabled(False)
        
    def enable_all_shortcuts(self):
        for sc in self.findChildren(QShortcut):
            sc.setEnabled(True)

    def show_custom_dialog(self,
                           message: str,
                           icon_type="info",
                           buttons="ok",
                           anchor_widget=None,
                           custom_button_texts: dict = None,
                           custom_button_styles: dict = None) -> QDialog.DialogCode:
        t = translations[self.current_language]
        self.disable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(False)
        
        # Create the overlay
        overlay = BaseOverlay(parent=self, overlay_name="MessageOverlay", bg_color="rgba(0, 0, 0, 150)")
        overlay.setObjectName("MessageOverlay")
        overlay.setGeometry(self.rect())
        
        # Key press for Esc to close the dialog.
        def overlay_keypress(event):
            if event.key() == Qt.Key.Key_Escape:
                close_dialog(QDialog.DialogCode.Rejected)
            else:
                event.ignore()
        overlay.keyPressEvent = overlay_keypress
        self.overlay_dialog = overlay

        # Create a container for the dialog content.
        container = QWidget(overlay)
        container.setObjectName("MessageContainer")
        container.setStyleSheet("""
            QWidget#MessageContainer {
                background-color: rgba(0, 0, 0, 0.88);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 60);
            }
            QLabel {
                background-color: transparent;
                color: white;
                font-size: 16px;
            }
            QPushButton {
                background-color: #222222;
                color: #ffffff;
                border: 2px solid #444444;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 15px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #333333;
            }
            QPushButton:pressed {
                background-color: #111111;
            }
            QPushButton:focus {
                outline: none;
                border: 2px solid #AAAAAA;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # Set dialog title based on icon_type.
        if icon_type == "error":
            title_text, emoji = t["error_title"], "❌"
        elif icon_type == "warning":
            title_text, emoji = t["warning"], "⚠️"
        else:
            title_text, emoji = t["info_title"], "ℹ️"
        title_label = QLabel(f"{emoji} {title_text}", container)
        title_label.setStyleSheet("font-weight: bold; font-size: 18px;")
        layout.addWidget(title_label)
        
        msg_label = QLabel(message, container)
        msg_label.setWordWrap(False)
        layout.addWidget(msg_label)
        layout.addSpacing(10)
        
        # Prepare button(s) layout.
        btn_row = QHBoxLayout()
        layout.addLayout(btn_row)
        dialog_result = [None]
        
        def close_dialog(result):
            dialog_result[0] = result
            overlay.hide()
            overlay.deleteLater()
            self.overlay_dialog = None
            if hasattr(self, "floating_menu") and self.floating_menu is not None:
                self.floating_menu.setEnabled(True)
            self.enable_all_shortcuts()
            loop.quit()
        
        if buttons == "yesno":
            # Use custom texts if provided; otherwise fall back to defaults.
            yes_text = custom_button_texts.get("yes") if (custom_button_texts and "yes" in custom_button_texts) else t["yes"]
            no_text  = custom_button_texts.get("no") if (custom_button_texts and "no" in custom_button_texts) else t["no"]
            yes_btn = QPushButton(yes_text, container)
            no_btn  = QPushButton(no_text, container)
            # Apply custom styles if provided.
            if custom_button_styles:
                if "yes" in custom_button_styles:
                    yes_btn.setStyleSheet(custom_button_styles["yes"])
                if "no" in custom_button_styles:
                    no_btn.setStyleSheet(custom_button_styles["no"])
            btn_row.addWidget(yes_btn)
            btn_row.addWidget(no_btn)
            yes_btn.setDefault(True)
            yes_btn.setAutoDefault(True)
            yes_btn.clicked.connect(lambda: close_dialog(QDialog.DialogCode.Accepted))
            no_btn.clicked.connect(lambda: close_dialog(QDialog.DialogCode.Rejected))
            yes_btn.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            def limited_keypress(event):
                if event.key() == Qt.Key.Key_Right:
                    if container.focusWidget() == yes_btn:
                        no_btn.setFocus()
                elif event.key() == Qt.Key.Key_Left:
                    if container.focusWidget() == no_btn:
                        yes_btn.setFocus()
                elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    container.focusWidget().click()
                elif event.key() == Qt.Key.Key_Escape:
                    close_dialog(QDialog.DialogCode.Rejected)
                else:
                    event.ignore()
            yes_btn.keyPressEvent = limited_keypress
            no_btn.keyPressEvent = limited_keypress
        else:
            ok_text = custom_button_texts.get("ok") if (custom_button_texts and "ok" in custom_button_texts) else t["ok"]
            ok_btn = QPushButton(ok_text, container)
            if custom_button_styles and "ok" in custom_button_styles:
                ok_btn.setStyleSheet(custom_button_styles["ok"])
            btn_row.addWidget(ok_btn)
            ok_btn.setDefault(True)
            ok_btn.setAutoDefault(True)
            ok_btn.clicked.connect(lambda: close_dialog(QDialog.DialogCode.Accepted))
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: ok_btn.setFocus(Qt.FocusReason.ActiveWindowFocusReason))
        
        container.adjustSize()
        overlay_w = overlay.width()
        overlay_h = overlay.height()
        container.setMaximumSize(overlay_w - 40, overlay_h - 40)
        container.adjustSize()
        x = (overlay_w - container.width()) // 2
        y = (overlay_h - container.height()) // 2
        container.move(x, y)
        container.show()
        
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        from PyQt6.QtCore import QEventLoop
        loop = QEventLoop()
        loop.exec()
        
        return dialog_result[0] or QDialog.DialogCode.Rejected


    def clamp_widget_to_overlay(self, widget: QWidget, overlay: QWidget):
        # Clamp the widget's position to lie within the overlay's rectangle.
        overlay_rect = overlay.rect()
        widget_geo = widget.geometry()
        new_x = widget_geo.x()
        new_y = widget_geo.y()
        if widget_geo.right() > overlay_rect.right():
            new_x = overlay_rect.right() - widget_geo.width()
        if new_x < overlay_rect.left():
            new_x = overlay_rect.left()
        if widget_geo.bottom() > overlay_rect.bottom():
            new_y = overlay_rect.bottom() - widget_geo.height()
        if new_y < overlay_rect.top():
            new_y = overlay_rect.top()
        widget.move(new_x, new_y)


    def set_loop_navigation(self, value: bool):
        self.loop_navigation = value
        self.save_config()
        self.update_floating_controls()

    def toggle_loop_shortcut(self):
        new_value = not self.loop_navigation
        self.set_loop_navigation(new_value)
        t = translations[self.current_language]
        if new_value:
            self.show_ephemeral_message(t["loop_enabled_message"])
        else:
            self.show_ephemeral_message(t["loop_disabled_message"])

    def show_ephemeral_message(self, message, duration_ms=1600):
        popup = EphemeralPopup(message, parent=self)
        popup.show()
        popup.fadeIn()
        if not hasattr(self, "ephemeral_messages"):
            self.ephemeral_messages = []
        self.ephemeral_messages.insert(0, popup)
        spacing = 10
        total_height = 0
        for ep in self.ephemeral_messages:
            ep.container.adjustSize()
            total_height += ep.container.height() + spacing
        if total_height > 0:
            total_height -= spacing
        top_y = (self.height() - total_height) // 2
        current_y = top_y
        for ep in self.ephemeral_messages:
            ep.container.adjustSize()
            w = ep.container.width()
            new_pos = QPoint((self.width() - w) // 2, current_y)
            anim = QPropertyAnimation(ep.container, b"pos")
            anim.setDuration(300)
            anim.setEndValue(new_pos)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            ep.pos_anim = anim
            current_y += ep.container.height() + spacing
        QTimer.singleShot(duration_ms, lambda: self._fade_out_popup(popup))

    def _fade_out_popup(self, popup):
        popup.fadeOut()
        def cleanup():
            if popup in self.ephemeral_messages:
                self.ephemeral_messages.remove(popup)
            popup.hide()
            popup.deleteLater()
            self._reposition_ephemeral_popups()
        popup.fade_anim.finished.connect(cleanup)

    def _reposition_ephemeral_popups(self):
        spacing = 10
        total_height = 0
        for ep in self.ephemeral_messages:
            ep.container.adjustSize()
            total_height += ep.container.height() + spacing
        if total_height > 0:
            total_height -= spacing
        top_y = (self.height() - total_height) // 2
        current_y = top_y
        for ep in self.ephemeral_messages:
            ep.container.adjustSize()
            w = ep.container.width()
            new_pos = QPoint((self.width() - w) // 2, current_y)
            anim = QPropertyAnimation(ep.container, b"pos")
            anim.setDuration(300)
            anim.setEndValue(new_pos)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            ep.pos_anim = anim
            current_y += ep.container.height() + spacing

    def backspace_toggle_fit(self):
        self.image_viewer.auto_fit = True
        self.image_viewer.adjustToFit()

    def set_hide_navigation_controls(self, value: bool):
        self.hide_navigation_controls = value
        self.save_config()
        self.update_floating_controls()

    def toggle_navigation_controls_shortcut(self):
        self.hide_navigation_controls = not self.hide_navigation_controls
        self.update_floating_controls()
        self.save_config()
        t = translations[self.current_language]
        message = (t["hide_navigation_disabled_message"]
                   if self.hide_navigation_controls
                   else t["hide_navigation_enabled_message"])
        self.show_ephemeral_message(message)

    def toggle_compare(self):
        if not self.image_files or self.current_index < 0 or self.current_index >= len(self.image_files):
            return
        current_image = self.image_files[self.current_index]
        t = translations.get(self.current_language, translations["en"])
        if current_image in self.compare_set:
            self.compare_set.remove(current_image)
            self.show_ephemeral_message(t["compare_removed"].format(count=len(self.compare_set)))
            if getattr(self, "current_filter", "all") == "compare":
                new_filtered = sorted(list(self.compare_set))
                if not new_filtered:
                    self.set_image_view("all")
                    self.save_marked_images()  # Save changes before returning
                    return
                else:
                    if self.current_index < len(new_filtered):
                        new_index = self.current_index
                    else:
                        new_index = 0 if self.loop_navigation else self.current_index - 1
                    self.image_files = new_filtered
                    self.current_index = new_index
                    self.update_favorite_count()
                    self.show_image(reset_zoom=self.reset_zoom_on_new_image)
                    self.save_marked_images()  # Save changes before returning
                    return
        else:
            self.compare_set.add(current_image)
            self.show_ephemeral_message(t["compare_added"].format(count=len(self.compare_set)))
        self.save_marked_images()
        self.update_favorite_count()


    def clear_compare(self):
        t = translations.get(self.current_language, translations["en"])
        # If no images are selected for compare, show a custom dialog.
        if not self.compare_set:
            self.show_custom_dialog(
                t["no_compare_to_clear"],
                icon_type="warning",
                buttons="ok"
            )
            return

        if hasattr(self, "context_menu_overlay") and self.context_menu_overlay is not None:
            self.context_menu_overlay.close()
            self.context_menu_overlay = None
        compare_count = len(self.compare_set)
        confirm = self.show_custom_dialog(
            t["clear_compare_confirm"].format(count=compare_count),
            icon_type="warning",
            buttons="yesno"
        )
        if confirm != QDialog.DialogCode.Accepted:
            return
        self.compare_set.clear()
        if getattr(self, "current_filter", "all") == "compare":
            self.set_image_view("all")
        self.show_ephemeral_message(t["compare_cleared"])
        self.update_favorite_count()
        self.save_marked_images()  # Save changes to Favorites.json

    def toggle_favorites_filter_shortcut(self):
        t = translations[self.current_language]
        # If we are NOT already in favorites mode, then enable favorites filter.
        if self.current_filter != "favorites":
            if len(self.favorites) == 0:
                self.show_custom_dialog(
                    t["no_favorites_marked"],
                    icon_type="info",
                    buttons="ok"
                )
                return
            self.set_image_view("favorites")
            self.show_ephemeral_message(t["favorites_filter_enabled"])
        else:
            # Otherwise, if we are already in favorites filter, toggle it off (back to all).
            self.set_image_view("all")
            self.show_ephemeral_message(t["favorites_filter_disabled"])

    def toggle_compare_filter_shortcut(self):
        t = translations[self.current_language]
        if self.current_filter != "compare":
            if len(self.compare_set) == 0:
                self.show_custom_dialog(
                    t["no_compare_marked"],
                    icon_type="info",
                    buttons="ok"
                )
                return
            self.set_image_view("compare")
            self.show_ephemeral_message(t["compare_filter_enabled"])
        else:
            self.set_image_view("all")
            self.show_ephemeral_message(t["compare_filter_disabled"])

    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)

    def get_unique_copy_filename(self, folder, base_name, ext):
        """Generate a unique 'base_name_copy.ext' in folder, 
           appending _1, _2, etc., if needed."""
        candidate = os.path.join(folder, f"{base_name}_copy{ext}")
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{base_name}_copy_{counter}{ext}")
            counter += 1
        return candidate

    def saveModifiedImage(self, overwrite: bool):
        """
        Saves the currently displayed, modified image. If overwrite=True, asks for confirmation
        and replaces the existing file in place; otherwise, writes a new copy with a unique name.
        After saving, clears any cached pixmap so that the in‐memory cache cannot override the
        fresh file on disk, and then reloads from disk so the viewer always shows the newly‐saved
        (cropped/brightened/rotated) version.
        """
        # 0) Basic checks: do nothing if there is no image
        if not self.image_files or self.current_index < 0:
            return

        # 1) Determine the normalized path & original file path
        norm_path = self.image_files[self.current_index]
        orig_path = self.norm_to_original.get(norm_path, norm_path)
        orig_filename = os.path.basename(orig_path)
        folder = os.path.dirname(orig_path)

        # Grab the current QPixmap from the viewer (what the user sees right now)
        modified = self.image_viewer.pixmap_item.pixmap()
        if modified.isNull():
            # Nothing to save
            return

        # Load localized strings
        t = translations.get(self.current_language, translations["en"])

        # 2) Overwrite vs. “Save a Copy”
        if overwrite:
            # Ask the user to confirm overwriting the existing file
            confirm = self.show_custom_dialog(
                t["overwrite_image_confirm"].format(current_image=orig_filename),
                icon_type="warning",
                buttons="yesno"
            )
            if confirm != QDialog.DialogCode.Accepted:
                return
            save_path = orig_path
        else:
            # Generate a new, unique filename in the same folder
            name, ext = os.path.splitext(orig_filename)
            save_path = self.get_unique_copy_filename(folder, name, ext)

        # 3) Attempt to write the pixmap to disk
        if not modified.save(save_path):
            # If saving fails, alert the user and bail out
            self.show_custom_dialog("Failed to save image", icon_type="error", buttons="ok")
            return

        # 4) Post‐save logic: two separate branches
        if not overwrite:
            # — “Save a Copy” branch — register the new file and display it —
            # 4a) Register the new file so get_all_images() will include it
            new_abs = os.path.abspath(save_path)
            norm_new = os.path.normcase(new_abs)
            self.norm_to_original[norm_new] = new_abs

            # 4a') Retain favorite on the copy: if the original was a favorite, the copy is too
            if norm_path in self.favorites:
                self.favorites.add(norm_new)

            # 4b) Rebuild the list of images respecting the current filter (don't break favorites/compare view)
            full_list = self.get_all_images()
            active_filter = getattr(self, "current_filter", "all")
            if active_filter == "favorites":
                new_files = [f for f in full_list if f in self.favorites]
            elif active_filter == "non_favorites":
                new_files = [f for f in full_list if f not in self.favorites]
            elif active_filter == "compare":
                new_files = [f for f in full_list if f in self.compare_set]
            else:
                new_files = full_list
            self.image_files = new_files

            # 4c) Jump to the new copy in the (filtered) list; if not in list, show first
            if norm_new in self.image_files:
                self.current_index = self.image_files.index(norm_new)
            else:
                self.current_index = 0

            # 4d) Display the new image (fresh load from disk)
            #     We assume self.show_image(...) updates thumbnails/UI and also sets the main pixmap.
            #     Passing reset_zoom=False so we keep whatever zoom the user had.
            self.show_image(reset_zoom=False, preserve_zoom=True)
            self.update_favorite_count()

            # 4e) Reset rotation/brightness state for the *original* file
            #     (so if the user returns to the original, it is not stuck with the old crop state)
            self.image_rotations[norm_path] = 0
            self.image_brightness[norm_path] = 1.0

            # 4f) Clear undo/redo history for the *new* copy (it doesn’t exist yet)
            if norm_new in self._history:
                self._history[norm_new] = {"undo": [], "redo": []}

            # 4g) Clear any “unsaved crop” state—this new copy has no pending crop edits
            self.unsaved_crop = None

        else:
            # — Overwrite existing file in‐place — force a fresh disk read —
            was_auto = self.image_viewer.auto_fit

            # 4a) Reset any rotation/brightness state at this path (we assume we want a “fresh” file)
            self.image_rotations[norm_path]  = 0
            self.image_brightness[norm_path] = 1.0
            self.image_viewer.rotation_angle   = 0
            self.image_viewer.brightness_factor = 1.0
            self.image_viewer.cached_texture    = None

            # <<-- CLEAR CACHE HERE: Remove any cached pixmap so that setImage(...) does NOT reuse
            #     the old in‐memory image. Instead, it will read the newly‐saved file from disk. --
            ImageLoaderRunnable._pixmap_cache.pop(norm_path, None)

            # 4b) Reload from disk. If we were in “auto fit” mode, keep that; otherwise preserve zoom.
            if was_auto:
                self.image_viewer.setImage(norm_path, reset_zoom=True, preserve_zoom=False)
            else:
                self.image_viewer.setImage(norm_path, reset_zoom=False, preserve_zoom=True)

            # 4c) Clear undo/redo history for this same path (since the file on disk just changed)
            if norm_path in self._history:
                self._history[norm_path]["undo"].clear()
                self._history[norm_path]["redo"].clear()

            # 4d) Clear any pending “unsaved crop” (we’ve now saved it)
            self.unsaved_crop = None

        # 5) Mark this image as “no longer modified”
        if self._current_path:
            self._modified[self._current_path] = False
        self.image_modified = False

        # 6) Refresh any floating controls (e.g. Save buttons, star toggles, etc.)
        self.update_floating_controls()

        # 7) Notify the user
        just_saved = os.path.basename(save_path)
        self.show_ephemeral_message(f"File saved as: {just_saved}", duration_ms=3000)



    def delete_non_favorites_action(self):
        # Ensure any open context menu overlay is closed:
        if hasattr(self, "context_menu_overlay") and self.context_menu_overlay is not None:
            self.context_menu_overlay.close()
        
        t = translations[self.current_language]
        all_images = self.get_all_images()
        non_favorites = [img for img in all_images if img not in self.favorites]
        if not non_favorites:
            self.show_custom_dialog(t["no_non_favorites_marked"], icon_type="warning", buttons="ok")
            return
        nonfavorite_count = len(non_favorites)
        confirm_msg = t["delete_non_favorites_confirm"].format(count=nonfavorite_count)
        confirm = self.show_custom_dialog(
            confirm_msg,
            icon_type="warning",
            buttons="yesno"
        )
        if confirm != QDialog.DialogCode.Accepted:
            return

        # Show an overlay progress dialog.
        progress_overlay = OverlayProgressDialog(
            t["delete_non_favorites_progress_title"],
            t["delete_non_favorites_progress_message"],
            parent=self
        )
        progress_overlay.setValue(0)
        progress_overlay.show()
        progress_overlay.raise_()

        # Create and launch the worker in a separate thread.
        self.delete_worker = DeleteNonFavoritesWorker(non_favorites)
        self.delete_thread = QThread()
        self.delete_worker.moveToThread(self.delete_thread)
        self.delete_worker.progressChanged.connect(progress_overlay.setValue)
        progress_overlay.cancelButton.clicked.connect(self.delete_worker.cancel)

        def on_finished(count):
            progress_overlay.hide()
            progress_overlay.deleteLater()
            self.show_custom_dialog(
                t["delete_non_favorites_success"].format(count=count),
                icon_type="info",
                buttons="ok"
            )
            self.delete_thread.quit()
            self.delete_thread.wait()
            self.delete_thread = None
            self.delete_worker = None

            # Remove deleted files from the current list
            self.image_files = [img for img in self.image_files if os.path.exists(img)]

            if not self.image_files:
                self.image_viewer.clear()
                self.current_index = -1
                self.current_filter = "all"
                # Hide the filename label and update floating controls
                self.filename_label.hide()
                self.update_floating_controls()
                # That’s it: we’re in a blank state now
            else:
                # If there are still images left, do normal logic
                if self.current_index >= len(self.image_files):
                    self.current_index = len(self.image_files) - 1
                self.show_image(reset_zoom=self.reset_zoom_on_new_image)
                self.update_favorite_count()

        self.delete_worker.finished.connect(on_finished)

        def on_error(err):
            progress_overlay.hide()
            progress_overlay.deleteLater()
            self.show_custom_dialog("Error: " + err, icon_type="error", buttons="ok")
            self.delete_thread.quit()
            self.delete_thread.wait()
            self.delete_thread = None
            self.delete_worker = None

        self.delete_worker.errorOccurred.connect(on_error)
        self.delete_thread.started.connect(self.delete_worker.run)
        self.delete_thread.start()

    def open_crop_overlay(self):
        # Retrieve the pristine (original) pixmap.
        current_pixmap = self.image_viewer.original_pixmap
        if current_pixmap is None or current_pixmap.isNull():
            return

        # Check for unsaved brightness/rotation modifications.
        if self.image_viewer.brightness_factor != 1.0 or self.image_viewer.rotation_angle != 0:
            t = translations[self.current_language]
            custom_texts = {
                "yes": t["discard_brightrot_and_crop"],      # e.g. "Discard & Crop"
                "no":  t["keep_brightrot_cancel"]            # e.g. "Keep Changes (Cancel Crop)"
            }
            custom_styles = {
                "yes": ("QPushButton { background-color: #007BFF; color: white; "
                        "border: 2px solid #444444; border-radius: 6px; padding: 8px 14px; font-size: 15px; }"
                        "QPushButton:hover { background-color: #0056b3; }"),
                "no":  ("QPushButton { background-color: #DC3545; color: white; "
                        "border: 2px solid #444444; border-radius: 6px; padding: 8px 14px; font-size: 15px; }"
                        "QPushButton:hover { background-color: #B22222; }")
            }
            result = self.show_custom_dialog(
                message=t["unsaved_crop_brightrot_warning_message"],
                icon_type="warning",
                buttons="yesno",
                custom_button_texts=custom_texts,
                custom_button_styles=custom_styles
            )
            # If the user chose “Keep Changes,” abort.
            if result != QDialog.DialogCode.Accepted:
                return

            # --- Discard unsaved modifications ---

            # a) Reset per-image stored state
            if hasattr(self, "image_files") and self.current_index >= 0:
                current_image = self.image_files[self.current_index]
                self.image_rotations[current_image] = 0
                self.image_brightness[current_image] = 1.0

            # b) Reset viewer’s temporary state
            self.image_viewer.brightness_factor = 1.0
            self.image_viewer.rotation_angle   = 0
            self.image_viewer.cached_texture   = None

            # c) Sync the brightness slider visually (if present)
            if hasattr(self, "brightness_slider"):
                slider = self.brightness_slider
                slider.blockSignals(True)
                # slider expects value = (1 - brightness) * 200
                slider.setValue(int((1.0 - 1.0) * 200))
                slider.blockSignals(False)

            # d) **Properly clean up undo/redo stacks for this image**
            path = getattr(self, "_current_path", None)
            if path and path in self._history:
                hist = self._history[path]
                # Remove the single "before‐brightness" entry, if it’s still there
                if hist["undo"]:
                    hist["undo"].pop(0)
                # Clear any redo entries
                hist["redo"].clear()
            # Also clear the brightness_undo_pushed flag so next open starts fresh
            if hasattr(self, "brightness_undo_pushed"):
                del self.brightness_undo_pushed

            # e) Repaint in-place without re-centering
            self.skip_centering = True
            self.image_viewer.updatePixmap()
            self.skip_centering = False

        # Disable shortcuts (and floating menu) before launching the crop overlay.
        self.disable_all_shortcuts()
        if hasattr(self, "floating_menu"):
            self.floating_menu.setEnabled(False)

        # Launch the crop overlay using the pristine image.
        self.crop_overlay = CropOverlay(
            self,
            current_pixmap,
            current_language=self.current_language
        )



    def applyCropResult(self, cropped_pix: QPixmap):
        if not cropped_pix.isNull():
            self.push_undo_state(from_crop=True)
            self.image_viewer.original_pixmap = cropped_pix
            self.image_viewer.rotation_angle = 0
            self.image_viewer.brightness_factor = 1.0
            self.image_viewer.cached_texture = None
            self.image_viewer.adjustToFit()
            self.image_viewer.updatePixmap()
            self.image_modified = True
            self.unsaved_crop = cropped_pix
    
    def on_slider_value_changed(self, val: int):
        self.angle_label.setText(f"Angle: {val}°")
        self.rotation = val
        self.update_scaled_pixmap()
        self.update()

    def push_undo_state(self, from_crop=False):
        """
        Save the current image state onto the undo stack.
        """
        path = getattr(self, "_current_path", None)
        if not path or path not in self._history:
            return

        hist = self._history[path]

        before = len(hist["undo"])

        # ==== BEGIN ORIGINAL push_undo_state BODY ====
        state = {
            "pixmap":          self.image_viewer.original_pixmap.copy(),
            "rotation":        self.image_viewer.rotation_angle,
            "brightness":      self.image_viewer.brightness_factor,
            "image_modified":  self.image_modified,
            "from_crop":       from_crop,
        }
        hist["undo"].append(state)
        # Clear the redo stack when pushing a new undo
        hist["redo"].clear()
        # ==== END ORIGINAL BODY ====

        after = len(hist["undo"])

    def undo_action(self):
        """
        Per-image Undo: revert to last state, sync slider if present,
        and only fit-to-viewport if it was a crop.
        """
        path = getattr(self, "_current_path", None)
        if not path or path not in self._history:
            return
        hist = self._history[path]
        if not hist["undo"]:
            return

        # 1) Pop last undo state
        state = hist["undo"].pop()

        # 2) Push current into redo
        curr = {
            "pixmap":          self.image_viewer.original_pixmap.copy(),
            "rotation":        self.image_viewer.rotation_angle,
            "brightness":      self.image_viewer.brightness_factor,
            "image_modified":  self.image_modified,
            "from_crop":       state.get("from_crop", False),
        }
        hist["redo"].append(curr)

        # 3) Apply popped state
        self.image_viewer.original_pixmap   = state["pixmap"]
        self.image_viewer.rotation_angle    = state["rotation"]
        self.image_viewer.brightness_factor = state["brightness"]
        # clear out any old GPU cache so we rebuild on next paint
        self.image_viewer.cached_texture    = None

        # 4) Restore modified flag
        self._modified[path] = state["image_modified"]
        self.image_modified  = state["image_modified"]
        self.unsaved_crop    = None

        # 5) Repaint
        self.image_viewer.updatePixmap()

        # 6) Sync the slider (if overlay still up)
        if hasattr(self, "brightness_slider"):
            slider = self.brightness_slider
            slider.blockSignals(True)
            slider.setValue(int((1.0 - state["brightness"]) * 200))
            slider.blockSignals(False)

        # 7) Turn off any compare‐mode overlay
        self.image_viewer.compare_enabled = False

        # 8) Fit only if this undo came from a crop action
        if state.get("from_crop", False):
            self.image_viewer.auto_fit = True
            self.image_viewer.adjustToFit()

        # 9) Update UI
        self._update_undo_redo_actions()
        self.update_floating_controls()
        self.show_ephemeral_message(
            translations[self.current_language]["undo_performed"]
        )

        # 10) Persist the restored brightness for this file
        self.image_brightness[path] = self.image_viewer.brightness_factor


    def redo_action(self):
        """
        Per-image Redo: reapply last undone state, sync slider if present,
        and only fit-to-viewport if it was a crop.
        """
        path = getattr(self, "_current_path", None)
        if not path or path not in self._history:
            return
        hist = self._history[path]
        if not hist["redo"]:
            return

        # 1) Pop last redo state
        state = hist["redo"].pop()

        # 2) Push current into undo
        curr = {
            "pixmap":          self.image_viewer.original_pixmap.copy(),
            "rotation":        self.image_viewer.rotation_angle,
            "brightness":      self.image_viewer.brightness_factor,
            "image_modified":  self.image_modified,
            "from_crop":       state.get("from_crop", False),
        }
        hist["undo"].append(curr)

        # 3) Apply popped state
        self.image_viewer.original_pixmap   = state["pixmap"]
        self.image_viewer.rotation_angle    = state["rotation"]
        self.image_viewer.brightness_factor = state["brightness"]
        # clear any old GPU texture cache
        self.image_viewer.cached_texture    = None

        # 4) Restore modified flag
        self._modified[path] = state["image_modified"]
        self.image_modified  = state["image_modified"]

        # 5) Repaint
        self.image_viewer.updatePixmap()

        # 6) Sync the slider (if overlay still up)
        if hasattr(self, "brightness_slider"):
            slider = self.brightness_slider
            slider.blockSignals(True)
            slider.setValue(int((1.0 - state["brightness"]) * 200))
            slider.blockSignals(False)

        # 7) Turn off any compare‐mode overlay
        self.image_viewer.compare_enabled = False

        # 8) Fit only if this redo came from a crop action
        if state.get("from_crop", False):
            self.image_viewer.auto_fit = True
            self.image_viewer.adjustToFit()

        # 9) Update UI
        self._update_undo_redo_actions()
        self.update_floating_controls()
        self.show_ephemeral_message(
            translations[self.current_language]["redo_performed"]
        )

        # 10) Persist the restored brightness for this file
        self.image_brightness[path] = self.image_viewer.brightness_factor


    def prompt_unsaved_crop_warning(self) -> bool:
        lang = self.current_language
        t = translations.get(lang, translations["en"])
        message = t["unsaved_crop_warning_message"]
        # Pass the new custom button texts (and optionally styling)
        custom_texts = {
            "yes": t["discard_and_crop"],
            "no":  t["keep_changes_cancel"]
        }
        custom_styles = {
            "yes": ("QPushButton { background-color: #007BFF; color: white; "
                    "border: 2px solid #444444; border-radius: 6px; padding: 8px 14px; font-size: 15px; }"
                    "QPushButton:hover { background-color: #0056b3; }"),
            "no": ("QPushButton { background-color: #DC3545; color: white; "
                   "border: 2px solid #444444; border-radius: 6px; padding: 8px 14px; font-size: 15px; }"
                   "QPushButton:hover { background-color: #B22222; }")
        }
        
        result = self.show_custom_dialog(
            message,
            icon_type="warning",
            buttons="yesno",
            custom_button_texts=custom_texts,
            custom_button_styles=custom_styles
        )
        # Return True if the user accepted (i.e. chose "Discard Crop (Continue)")
        return (result == QDialog.DialogCode.Accepted)

    def change_image(self, new_image_path):
        # Check if an unsaved crop is active.
        if self.unsaved_crop is not None:
            if not self.prompt_unsaved_crop_warning():
                # The user cancelled the action.
                return
            else:
                # Clear the unsaved crop if the user confirms.
                self.unsaved_crop = None

        # Now proceed to load the new image.
        # For example, if your load_directory method is used when changing images:
        self.load_directory(os.path.dirname(new_image_path), selected_file=new_image_path)

    def set_theme(self, theme_value: str):
        """
        Update application theme, persist setting, apply background to the viewer,
        central widget, and tint the floating controls (filename label, arrows, star),
        AND sync QToolTip background/text with the same colors.
        """
        # 1) store & persist
        self.theme = theme_value
        self.save_config()

        # 2) map to our three colors
        if theme_value == "black":
            bg = "#000000"
        elif theme_value == "inkstone":
            bg = "#1A202C"
        elif theme_value == "dark_grey":
            bg = "#212121"
        else:
            bg = "#000000"
        fg = "#ffffff"  # tooltip & text color

        # 3) Sync the application palette (including tooltips)
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui     import QPalette, QColor

        app = QApplication.instance()
        palette = app.palette()
        palette.setColor(QPalette.ColorRole.Window,       QColor(bg))
        palette.setColor(QPalette.ColorRole.WindowText,   QColor(fg))
        palette.setColor(QPalette.ColorRole.ToolTipBase,  QColor(bg))
        palette.setColor(QPalette.ColorRole.ToolTipText,  QColor(fg))
        app.setPalette(palette)

        # 4) apply to the image viewer’s paintEvent
        if hasattr(self, "image_viewer") and self.image_viewer is not None:
            self.image_viewer.theme    = theme_value
            self.image_viewer.bg_color = bg
            self.image_viewer.setStyleSheet(
                f"border: none; background-color: {bg};"
            )
            self.image_viewer.viewport().update()

        # 5) paint the central widget’s own background (under the dock margin)
        cw = self.centralWidget()
        if cw:
            cw.setStyleSheet(f"background-color: {bg};")

        # 6) compute semi-transparent tints from the bg color
        from PyQt6.QtGui import QColor as _QColor
        ink   = _QColor(bg)
        base  = f"rgba({ink.red()},{ink.green()},{ink.blue()},0.5)"
        hover = f"rgba({ink.red()},{ink.green()},{ink.blue()},0.7)"

        # 7) recolor the filename label
        if hasattr(self, "filename_label") and self.filename_label is not None:
            self.filename_label.setStyleSheet(f"""
                background-color: {base};
                color: white;
                font-size: 23px;
                border-radius: 25px;
                padding-left: 15px;
                padding-right: 15px;
            """)

        # 8) recolor the floating buttons (star & nav arrows)
        btn_style = f"""
            QPushButton {{
                background-color: {base};
                border-radius: 20px;
                color: white;
                font-size: 24px;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """
        for btn in (self.float_favorite, self.float_previous, self.float_next):
            if btn is not None:
                btn.setStyleSheet(btn_style)

    def open_sharpness_overlay(self):
        """
        Launch the Sharpness overlay *without* pushing an undo state.
        We only snapshot when the user actually applies the change.
        """
        # If you had a leftover flag, clear it:
        if hasattr(self, "_sharpness_undo_pushed"):
            del self._sharpness_undo_pushed

        # Grab the current pixmap
        orig = self.image_viewer.original_pixmap

        # Create & show the overlay
        self.sharpness_overlay = SharpnessOverlay(self, orig, self.current_language)
        self.sharpness_overlay.show()


    def applySharpenResult(self, sharpened_pix: QPixmap):
        """
        Receive the sharpened QPixmap and display it,
        *and* mark this image as having unsaved edits.
        """
        # ——— your existing viewer-update code ———
        self.image_viewer.original_pixmap = sharpened_pix
        self.image_viewer.cached_texture = None

        # preserve auto-fit vs manual zoom:
        if self.image_viewer.auto_fit:
            self.image_viewer.adjustToFit()
        else:
            self.image_viewer.resetTransform()
            self.image_viewer.scale(
                self.image_viewer.zoom_factor,
                self.image_viewer.zoom_factor
            )
            self.image_viewer.updatePixmap()
        # ———————————————————————————————

        # mark *this* image dirty
        if self._current_path:
            self._modified[self._current_path] = True
        self.image_modified = True
        self.update_floating_controls()


    def _update_undo_redo_actions(self):
        """
        Enable or disable the Undo/Redo UI controls based on the history
        of the currently displayed image, but safely skip if those
        controls don’t exist or are methods rather than QAction/button.
        """
        # Determine availability
        can_undo = False
        can_redo = False
        if getattr(self, "_current_path", None) in self._history:
            hist = self._history[self._current_path]
            can_undo = bool(hist["undo"])
            can_redo = bool(hist["redo"])

        # Try enabling self.undo_action if it’s a real QAction-like object
        ua = getattr(self, "undo_action", None)
        if hasattr(ua, "setEnabled"):
            ua.setEnabled(can_undo)

        # Try enabling self.redo_action
        ra = getattr(self, "redo_action", None)
        if hasattr(ra, "setEnabled"):
            ra.setEnabled(can_redo)

        # Also guard any toolbar buttons named btn_undo / btn_redo
        bu = getattr(self, "btn_undo", None)
        if hasattr(bu, "setEnabled"):
            bu.setEnabled(can_undo)
        br = getattr(self, "btn_redo", None)
        if hasattr(br, "setEnabled"):
            br.setEnabled(can_redo)

# ------------------------------------------------------------------------
# main
# ------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)

    # Create your 32×32 transparent pixmap and draw the “⭐”
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    font = QFont()
    font.setPointSize(22)
    painter.setFont(font)
    painter.drawText(pixmap.rect(),
                     Qt.AlignmentFlag.AlignCenter,
                     "⭐")
    painter.end()

    # Set the window icon
    app.setWindowIcon(QIcon(pixmap))

    # Launch your viewer
    viewer = PhotoViewer()
    viewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
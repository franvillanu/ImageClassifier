"""Zoomable, pannable image view with compare, brightness and sharpen.
"""
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLayout, QFrame, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtGui import QPixmap, QWheelEvent, QMouseEvent, QPainter, QTransform, QImage, QOpenGLContext
from PyQt6.QtCore import Qt, QPoint, QTimer, QSize, QPointF
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLShaderProgram, QOpenGLShader, QOpenGLTexture
from image_classifier.i18n.translations import translations
from image_classifier.imaging import ImageFrame, ImageLoaderRunnable
from image_classifier.imaging.loader import PRIORITY_CURRENT, PRIORITY_FULL_RESOLUTION, preview_dimension_for
from image_classifier.ui.widgets import BaseOverlay, MyDragOverlay
from image_classifier.ui.viewport import NearestViewport, _opengl


# ------------------------------------------------------------------------
# AdvancedGraphicsImageViewer
# ------------------------------------------------------------------------
class AdvancedGraphicsImageViewer(QGraphicsView):
    FULL_RESOLUTION_DWELL_MS = 250

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
        self.full_loader = None
        self.loading_dialog = None
        self.full_resolution_ready = False
        self.current_load_id = 0
        self._shown_load_id = None
        # (source cacheKey, viewport-sized frame) reused by fit-mode re-renders.
        self._display_cache = None
        # Full-resolution decode starts once the user settles on a photo, so fast
        # browsing never queues 24 MP decodes it will skip past.
        self._full_request_timer = QTimer(self)
        self._full_request_timer.setSingleShot(True)
        self._full_request_timer.setInterval(self.FULL_RESOLUTION_DWELL_MS)
        self._full_request_timer.timeout.connect(self.request_full_resolution)
        self._brightness_timer = QTimer(self)
        self._brightness_timer.setSingleShot(True)
        self._brightness_timer.timeout.connect(self._apply_pending_brightness)
        self._pending_brightness = 1.0
        self._brightness_program = None

    def preview_dimension(self) -> int:
        """Preview size that covers the viewport 1:1 in physical pixels."""
        viewport = self.viewport()
        return preview_dimension_for(
            viewport.width(),
            viewport.height(),
            viewport.devicePixelRatioF(),
        )

    def _cancel_pending_loads(self):
        self._full_request_timer.stop()
        for attr in ("loader", "full_loader"):
            worker = getattr(self, attr, None)
            if worker is not None:
                worker.cancel()
                setattr(self, attr, None)

    def setImage(self, image_path, reset_zoom=True, preserve_zoom=False):
        """Show ``image_path``: screen-sized frame first, full resolution on demand.

        Order of preference: in-memory preview (instant), in-memory full image
        (instant, scaled once), otherwise a high-priority preview decode. The
        full-resolution frame is attached later without re-rendering the screen.
        """
        norm = ImageLoaderRunnable.normalize_path(image_path)

        self.load_counter = getattr(self, "load_counter", 0) + 1
        self.current_load_id = self.load_counter
        load_id = self.current_load_id
        self.current_loading_image = norm
        self._cancel_pending_loads()
        self.full_resolution_ready = False

        # Reset per-image adjustments *before* anything is shown. show_image() stages
        # the target's saved rotation/brightness in desired_*; onImageLoaded applies them.
        self.cached_texture = None
        self.brightness_factor = 1.0
        if hasattr(self, "brightness_slider"):
            self.brightness_slider.setValue(0)
        self.compare_enabled = False

        dimension = self.preview_dimension()
        full = ImageLoaderRunnable.get_cached_image(norm)
        preview = ImageLoaderRunnable.get_cached_preview(norm, dimension)

        if preview is not None:
            self.onImageLoaded(
                QPixmap.fromImage(preview),
                reset_zoom,
                preserve_zoom,
                load_id,
                full_resolution=False,
            )
            if full is not None:
                self._attach_full_resolution(QPixmap.fromImage(full), load_id)
            else:
                self._full_request_timer.start()
            return

        if full is not None:
            self.onImageLoaded(
                QPixmap.fromImage(full),
                reset_zoom,
                preserve_zoom,
                load_id,
                full_resolution=True,
            )
            return

        self.window().image_loading = True
        worker = ImageLoaderRunnable(
            norm,
            max_dimension=dimension,
            progressive=True,
            load_full=False,
        )
        worker.signals.previewReady.connect(
            lambda frame, id=load_id:
                self._on_frame(frame, reset_zoom, preserve_zoom, id)
        )
        # Small sources are decoded whole in one pass and arrive as full frames.
        worker.signals.fullReady.connect(
            lambda frame, id=load_id:
                self._on_frame(frame, reset_zoom, preserve_zoom, id)
        )
        worker.signals.error.connect(
            lambda err, id=load_id: self._on_load_error(err, id)
        )
        self.loader = worker
        worker.start(PRIORITY_CURRENT)

    def _on_frame(self, frame: ImageFrame, reset_zoom: bool, preserve_zoom: bool, load_id: int):
        if load_id != self.current_load_id:
            return
        pixmap = QPixmap.fromImage(frame.image)
        if self._shown_load_id != load_id:
            self.loader = None
            self.onImageLoaded(
                pixmap,
                reset_zoom,
                preserve_zoom,
                load_id,
                full_resolution=frame.full_resolution,
            )
            if not frame.full_resolution:
                self._full_request_timer.start()
            return
        if frame.full_resolution and not self.full_resolution_ready:
            self._attach_full_resolution(pixmap, load_id)

    def request_full_resolution(self):
        """Start (or finish from cache) the full-resolution load for the current image."""
        self._full_request_timer.stop()
        if self.full_resolution_ready or self.full_loader is not None:
            return
        if self._shown_load_id != self.current_load_id:
            # Nothing on screen yet; the preview handler re-arms the timer.
            return
        norm = getattr(self, "current_loading_image", None)
        if not norm:
            return
        load_id = self.current_load_id
        cached = ImageLoaderRunnable.get_cached_image(norm)
        if cached is not None:
            self._attach_full_resolution(QPixmap.fromImage(cached), load_id)
            return
        worker = ImageLoaderRunnable(
            norm,
            max_dimension=self.preview_dimension(),
            progressive=True,
            load_full=True,
            load_preview=False,
        )
        worker.signals.fullReady.connect(
            lambda frame, id=load_id: self._on_full_frame(frame, id)
        )
        worker.signals.error.connect(
            lambda err, id=load_id: self._on_load_error(err, id)
        )
        self.full_loader = worker
        worker.start(PRIORITY_FULL_RESOLUTION)

    def _on_full_frame(self, frame: ImageFrame, load_id: int):
        if load_id != self.current_load_id:
            return
        self.full_loader = None
        self._attach_full_resolution(QPixmap.fromImage(frame.image), load_id)

    def _attach_full_resolution(self, pixmap: QPixmap, load_id: int):
        """Swap in the full-resolution source without a visible re-render.

        Fit mode: the preview on screen already covers the viewport 1:1, so it is
        kept as the display frame and only the source changes (no frame drop, no
        quality "pop"). Zoomed in: the view is rescaled by preview/full so the same
        part of the photo stays under the same screen pixels.
        """
        if load_id != self.current_load_id or pixmap.isNull():
            return
        previous = self.original_pixmap
        self.full_resolution_ready = True
        self.cached_texture = None
        if previous is None or previous.isNull():
            self.original_pixmap = pixmap
            self._display_cache = None
            self.updatePixmap()
            return
        # Keyboard zoom keeps auto_fit set, so decide from the actual scale (as the
        # original full-frame handler did) rather than the flag alone.
        at_fit = self.auto_fit and abs(self.transform().m11() - self.fit_zoom_factor) < 0.01
        if at_fit:
            self.original_pixmap = pixmap
            self._display_cache = (pixmap.cacheKey(), previous)
            return

        self.auto_fit = False
        ratio = previous.width() / pixmap.width() if pixmap.width() else 1.0
        center = self.mapToScene(self.viewport().rect().center())
        self.original_pixmap = pixmap
        self._display_cache = None
        self.updatePixmap()
        if abs(ratio - 1.0) > 1e-3:
            self.scale(ratio, ratio)
            self.zoom_factor = self.transform().m11()
            self.fit_zoom_factor *= ratio
            self.centerOn(QPointF(center.x() / ratio, center.y() / ratio))
            self._apply_sampling_mode()

    def _on_load_error(self, err, load_id):
        if load_id != self.current_load_id:
            return
        window = self.window()
        window.image_loading = False
        self.loader = None
        self.full_loader = None
        if hasattr(window, 'show_custom_dialog'):
            lang = getattr(window, 'current_language', 'en')
            if lang == 'es':
                msg = f"No se pudo cargar la imagen:\n{err}"
            else:
                msg = f"Failed to load image:\n{err}"
            window.show_custom_dialog(msg, icon_type="error", buttons="ok")
        else:
            print(f"Error loading image: {err}")

    def _apply_sampling_mode(self):
        """Bilinear when the photo is drawn smaller than its pixels, nearest when zoomed in.

        Nearest-neighbour keeps pixel-peeping crisp, but when downscaling it drops
        whole rows/columns, which shows up as jagged edges and shimmering detail.
        """
        scale = abs(self.transform().m11()) * self.viewport().devicePixelRatioF()
        mode = (
            Qt.TransformationMode.SmoothTransformation
            if scale < 0.999
            else Qt.TransformationMode.FastTransformation
        )
        if self.pixmap_item.transformationMode() != mode:
            self.pixmap_item.setTransformationMode(mode)

    def _cancel_loader(self):
        """Safely cancel the image loader and close the overlay, if any."""
        if getattr(self, "loader", None) is not None:
            self.loader.cancel()
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
                      load_id: int,
                      full_resolution: bool = True):
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

        # QPixmap is implicitly shared. Avoid a full-frame copy on every load.
        self._shown_load_id = load_id
        self.original_pixmap = pixmap
        self._display_cache = None
        self.full_resolution_ready = full_resolution
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
            self.pixmap_item.setPixmap(display_pix)
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
            self._apply_sampling_mode()

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

    def _display_source(self) -> QPixmap:
        """Return a viewport-sized working frame for fit-mode rendering."""
        source = self.original_pixmap
        if source is None or source.isNull() or not self.auto_fit:
            return source
        max_dimension = self.preview_dimension()
        if max(source.width(), source.height()) <= max_dimension:
            return source
        cached = self._display_cache
        if cached is not None and cached[0] == source.cacheKey():
            frame = cached[1]
            # Valid while it still covers the viewport (window may have grown).
            if max(frame.width(), frame.height()) >= max_dimension - 2:
                return frame
        frame = source.scaled(
            max_dimension,
            max_dimension,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._display_cache = (source.cacheKey(), frame)
        return frame

    def renderFullResolution(self) -> QPixmap:
        """Render current non-destructive adjustments at source resolution."""
        if self.original_pixmap is None or self.original_pixmap.isNull():
            return QPixmap()
        if self.rotation_angle:
            rendered = self.original_pixmap.transformed(
                QTransform().rotate(self.rotation_angle),
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            rendered = self.original_pixmap
        if self.brightness_factor != 1.0:
            viewport = self.viewport()
            if isinstance(viewport, QOpenGLWidget):
                viewport.makeCurrent()
                rendered = self.applyBrightnessGPU(
                    rendered,
                    self.brightness_factor,
                )
                viewport.doneCurrent()
            else:
                rendered = self.applyBrightness(
                    rendered,
                    self.brightness_factor,
                )
        return rendered

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

        # Avoid allocating a same-size frame when no rotation is active.
        source = self._display_source()
        if self.rotation_angle:
            rotated = source.transformed(
                QTransform().rotate(self.rotation_angle),
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            rotated = source

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
        self.pixmap_item.setPixmap(baked)

        # 7) Fit that pixmap to the view & update scene bounds
        rect = self.pixmap_item.sceneBoundingRect()
        self.scene.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

        # 8) Record the new zoom factors
        scale = self.transform().m11()
        self.zoom_factor     = scale
        self.fit_zoom_factor = scale
        self._apply_sampling_mode()

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
        if self.auto_fit:
            self.adjustToFit()
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

        # 5) Into item + update bounds
        self.pixmap_item.setPixmap(baked)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        # 6) Restore transform & anchor so zoom/pan stay exactly where they were
        self.setTransform(saved_transform)
        self.setTransformationAnchor(saved_anchor)
        self._apply_sampling_mode()


    def setBrightness(self, factor):
        self.compare_enabled = False
        self._pending_brightness = factor
        if not self._brightness_timer.isActive():
            self._brightness_timer.start(16)

    def _apply_pending_brightness(self):
        self.cached_texture = None
        self.brightness_factor = self._pending_brightness
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
        self._apply_sampling_mode()
        # Zooming needs real pixels: skip the dwell delay.
        self.request_full_resolution()

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
        self._apply_sampling_mode()
        self.request_full_resolution()

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
        import ctypes

        GL = _opengl()

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
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_CULL_FACE)

        GL.glViewport(0, 0, w, h)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        # 3) Compile once per GL context and reuse for every slider frame.
        if self._brightness_program is None:
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
            VERTEX_SHADER = 0x00000001
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
            self._brightness_program = prog
        prog = self._brightness_program
        prog.bind()
        prog.setUniformValue("brightness", factor)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        tex.bind()
        prog.setUniformValue("image", 0)

        # 4) Draw one big triangle—no shared edge, no seam
        verts = [
            -1.0, -1.0,   0.0, 0.0,
             3.0, -1.0,   2.0, 0.0,
            -1.0,  3.0,   0.0, 2.0
        ]
        verts = (GL.GLfloat * len(verts))(*verts)
        vao = GL.glGenVertexArrays(1)
        vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, ctypes.sizeof(verts), verts, GL.GL_STATIC_DRAW)

        stride = 4 * ctypes.sizeof(GL.GLfloat)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE,
                              stride,
                              ctypes.c_void_p(2 * ctypes.sizeof(GL.GLfloat)))
        GL.glEnableVertexAttribArray(1)

        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)

        # 5) Cleanup and read back
        GL.glBindVertexArray(0)
        GL.glDeleteBuffers(1, [vbo])
        GL.glDeleteVertexArrays(1, [vao])
        tex.release()
        prog.release()
        fbo.release()

        result = fbo.toImage().mirrored(False, True)
        return QPixmap.fromImage(result)

    def applyBrightness(self, pixmap: QPixmap, factor: float) -> QPixmap:
        """CPU fallback matching the gamma shader."""
        import numpy as np

        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        pointer = image.bits()
        pointer.setsize(image.sizeInBytes())
        pixels = np.frombuffer(pointer, np.uint8).reshape(
            image.height(),
            image.bytesPerLine(),
        )
        rgba = pixels[:, : image.width() * 4].reshape(
            image.height(),
            image.width(),
            4,
        )
        rgb = rgba[:, :, :3].astype(np.float32) / 255.0
        rgba[:, :, :3] = np.clip(
            np.power(rgb, factor) * 255.0,
            0,
            255,
        ).astype(np.uint8)
        return QPixmap.fromImage(image)


    def applySharpenGPU(self, pixmap: QPixmap, radius: int, amount: float) -> QPixmap:
        GL = _opengl()

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

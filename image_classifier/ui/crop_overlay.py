"""Crop overlay shown over the photo viewer.
"""
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QSlider
from PyQt6.QtGui import QPixmap, QCursor, QPainter, QTransform, QColor, QPen, QKeyEvent
from PyQt6.QtCore import Qt, QPoint, QTimer, QEvent, QRect, QPointF, pyqtSignal, QRectF
from image_classifier.i18n.translations import translations
from image_classifier.ui.widgets import OverlayComboBox, SmoothRotationSlider


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
        preview_dimension = 2048
        if max(original_pixmap.width(), original_pixmap.height()) > preview_dimension:
            self.preview_pixmap = original_pixmap.scaled(
                preview_dimension,
                preview_dimension,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self.preview_pixmap = original_pixmap
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
        w = self.preview_pixmap.width()
        h = self.preview_pixmap.height()
        tf = QTransform()
        tf.translate(w/2, h/2)
        tf.rotate(self.rotation)
        tf.translate(-w/2, -h/2)
        self._rotated_full = self.preview_pixmap.transformed(
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

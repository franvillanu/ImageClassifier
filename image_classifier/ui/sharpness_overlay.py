"""Sharpness preview overlay.
"""
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QSlider
from PyQt6.QtGui import QPixmap, QWheelEvent, QMouseEvent, QPainter, QColor, QPen, QKeyEvent
from PyQt6.QtCore import Qt, QTimer
from image_classifier.i18n.translations import translations
from image_classifier.imaging import sharpen_cv2
from image_classifier.workers import SharpenThread


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
        preview_dimension = 2048
        if max(original_pixmap.width(), original_pixmap.height()) > preview_dimension:
            self.preview_orig = original_pixmap.scaled(
                preview_dimension,
                preview_dimension,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self.preview_orig = original_pixmap
        self.current = self.preview_orig
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
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._render_preview)

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
            self.preview_orig.scaled(nw, nh,
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
        self._preview_timer.start(60)

    def _render_preview(self):
        r = self.sld_r.value()
        a = self.sld_a.value() / 100.0
        self.current = sharpen_cv2(self.preview_orig, r, a)
        self.update()

# ------------------------------------------------------------------------
# Full-Screen Sharpness Overlay tying it all together
# ------------------------------------------------------------------------
class SharpnessOverlay(QWidget):
    def __init__(self, owner, original_pixmap: QPixmap, current_language="en"):
        super().__init__(owner)
        self._viewer = owner
        self.orig_pix = original_pixmap
        self._processing = False
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

        # 3) Run the full-resolution commit away from the GUI thread.
        worker = SharpenThread(self.orig_pix, r, a, self._viewer)
        self._viewer.sharpen_thread = worker
        self._processing = True
        self.content.setEnabled(False)

        def apply_result(image):
            self._viewer.applySharpenResult(QPixmap.fromImage(image))
            worker.deleteLater()
            self._viewer.sharpen_thread = None
            self._processing = False
            self.releaseKeyboard()
            self.close()

        def show_error(message):
            self._viewer.show_custom_dialog(
                message,
                icon_type="error",
                buttons="ok",
            )
            worker.deleteLater()
            self._viewer.sharpen_thread = None
            self._processing = False
            self.releaseKeyboard()
            self.close()

        worker.finished.connect(apply_result)
        worker.errorOccurred.connect(show_error)
        worker.start()

    def onCancelled(self):
        if self._processing:
            return
        # release the grab and close, just like crop
        self.releaseKeyboard()
        self.close()

    def closeEvent(self, ev):
        if self._processing:
            ev.ignore()
            return
        # restore shortcuts & menu on the viewer
        owner = self.parent()
        if hasattr(owner, "enable_all_shortcuts"):
            owner.enable_all_shortcuts()
        if getattr(owner, "floating_menu", None):
            owner.floating_menu.setEnabled(True)
        super().closeEvent(ev)

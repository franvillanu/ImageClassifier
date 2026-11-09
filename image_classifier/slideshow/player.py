"""Modal viewing window and localized slideshow preferences."""
import ctypes
from dataclasses import replace
import os
from PyQt6.QtCore import QEvent, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPalette, QShortcut
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog, QDialogButtonBox,
                            QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                            QPushButton, QSpinBox, QVBoxLayout, QWidget)
from image_classifier.i18n.translations import translations
from image_classifier.imaging.loader import preview_dimension_for
from image_classifier.ui.icons import IconFactory
from .controller import SlideshowController
from .loading import SlideLoader
from .settings import SlideshowSettings
from .settings_dialog import SettingsDialog
from .surface import SlideSurface


class PlayerWindow(QDialog):
    settingsChanged = pyqtSignal(object)

    def __init__(self, playlist, starting_image, settings, parent=None, *, language="en", raster=False):
        super().__init__(parent)
        self.language = language
        self.t = translations.get(language, translations["en"])
        self.setWindowTitle(self.t["slideshow_title"])
        self.setObjectName("slideshowPlayer")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(480,320)
        self.resize(1000,700)
        # Start directly in the wanted state so the window never flashes at normal size first.
        if settings.fullscreen:
            self.setWindowState(Qt.WindowState.WindowFullScreen)
        elif settings.maximized:
            self.setWindowState(Qt.WindowState.WindowMaximized)
        self.setStyleSheet("""
            QDialog#slideshowPlayer { background: black; }
            QWidget#slideshowOverlay { background: transparent; }
            QFrame#slideshowBar { background: rgba(24, 27, 33, 230);
                border: 1px solid rgba(213, 224, 242, 38); border-radius: 18px; }
            QLabel#slideshowCaption { color: #d4dae4; font-size: 12px;
                background: rgba(14, 16, 20, 190); border-radius: 8px; padding: 5px 10px; }
            QPushButton { background: transparent; border: 1px solid transparent; border-radius: 10px; }
            QPushButton:hover { background: rgba(255, 255, 255, 22); }
            QPushButton:pressed { background: rgba(255, 255, 255, 36); }
            QPushButton:focus { border-color: #b9c9df; }
            QPushButton#slideshowPlay { background: #edf1f7; border-radius: 22px; }
            QPushButton#slideshowPlay:hover { background: white; }
            QPushButton#slideshowClose { background: rgba(24, 27, 33, 210); border-radius: 18px; }
        """)
        self._closing = False
        self._editing_settings = False
        self._fullscreen_change = False
        self._sleep_active = False
        self._last_presented = None
        self._frozen_progress = 0
        self._frozen_strength = settings.strength
        self._applied_mode = (settings.fullscreen, settings.maximized)
        self._notice = ""
        self._status = self.t["slideshow_loading"]
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("black"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.surface = SlideSurface(self, raster=raster)
        # Never show the native window's white before the first frame: stay invisible until
        # the surface has painted (black or a photo), with a safety net if nothing paints.
        self.setWindowOpacity(0.0)
        self.surface.framePainted.connect(self._first_frame)
        QTimer.singleShot(700, self._first_frame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.surface)
        self.controls = QWidget(self)
        self.controls.setObjectName("slideshowOverlay")
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)
        self.message = QLabel(self.t["slideshow_loading"])
        self.message.setObjectName("slideshowCaption")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        controls_layout.addWidget(self.message, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.toast = QLabel(self)
        self.toast.setObjectName("slideshowCaption")
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast.setStyleSheet("font-size: 15px; padding: 8px 16px;")
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.setInterval(1500)
        self.toast_timer.timeout.connect(self.toast.hide)
        self.control_bar = QFrame(self.controls)
        self.control_bar.setObjectName("slideshowBar")
        row = QHBoxLayout(self.control_bar)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(4)
        controls_layout.addWidget(self.control_bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.buttons = {}
        for key, action in (("previous", self.previous), ("play", self.toggle_pause),
                            ("next", self.next), ("settings", self.open_settings),
                            ("fullscreen", self.toggle_fullscreen), ("close", self.close)):
            button = QPushButton(self if key == "close" else self.control_bar)
            button.setAccessibleName(self.t["slideshow_"+key])
            hint = {"previous": "←", "play": "␣", "next": "→", "fullscreen": "F11", "close": "Esc"}.get(key, "")
            button.setToolTip(self.t["slideshow_"+key] + ("  " + hint if hint else ""))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(44, 44) if key == "play" else button.setFixedSize(36, 36)
            button.setIconSize(QSize(22, 22))
            icon = "play_dark" if key == "play" else key
            button.setIcon(IconFactory.get_icon("slideshow_" + icon, 48))
            button.clicked.connect(action)
            self.buttons[key] = button
            if key == "play":
                button.setObjectName("slideshowPlay")
            elif key == "settings":
                divider = QFrame(self.control_bar)
                divider.setFixedSize(1, 22)
                divider.setStyleSheet("background: rgba(213, 224, 242, 38); border: none;")
                row.addSpacing(8)
                row.addWidget(divider)
                row.addSpacing(8)
            if key == "close":
                button.setObjectName("slideshowClose")
            else:
                row.addWidget(button)
        self.control_bar.setFixedSize(self.control_bar.sizeHint())
        self.loader = SlideLoader(self)
        self.controller = SlideshowController(tuple(playlist), starting_image, settings, self.loader, parent=self)
        self.controller.presented.connect(self._present)
        self.controller.frameUpdated.connect(lambda frame:self.surface.present(self.controller.entry,frame))
        self.controller.stateChanged.connect(self._state_changed)
        self.controller.updated.connect(self._refresh)
        self.controller.skipped.connect(lambda p: self._show_notice(self.t["slideshow_skipped"].format(path=os.path.basename(p))))
        self.controller.error.connect(lambda code: self._show_notice(self.t["slideshow_"+code], persistent=True))
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.controller.tick)
        self.decode_refresh_timer = QTimer(self)
        self.decode_refresh_timer.setSingleShot(True)
        self.decode_refresh_timer.setInterval(200)
        self.decode_refresh_timer.timeout.connect(self._refresh_decode)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(3000)
        self.hide_timer.timeout.connect(self._hide_controls)
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.setInterval(5000)
        self.notice_timer.timeout.connect(self._clear_notice)
        for key, callback in (("Space", self.toggle_pause), ("Left", lambda: self.previous(reveal=False)),
                              ("Right", lambda: self.next(reveal=False)),
                              ("Up", lambda: self.change_speed(longer=True)),
                              ("Down", lambda: self.change_speed(longer=False)),
                              ("F11", self.toggle_fullscreen), ("Escape", self.close)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
        self.surface.fallbackActivated.connect(self._install_tracking)
        self._install_tracking()
        QApplication.instance().aboutToQuit.connect(self._shutdown)
        QTimer.singleShot(0, self._start)

    def _first_frame(self):
        if self._closing or self.windowOpacity() >= 1.0:
            return
        QTimer.singleShot(0, lambda: None if self._closing else self.setWindowOpacity(1.0))

    def _install_tracking(self):
        for widget in (self, *self.findChildren(QWidget)):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def _start(self):
        if self._closing:
            return
        self._apply_mode(self.controller.settings)
        self._update_decode_size()
        self.controller.start()
        self.setFocus()
        self.timer.start()
        self.reveal_controls()

    def _update_decode_size(self):
        dimension = preview_dimension_for(self.width()*2, self.height()*2, self.devicePixelRatioF())
        if self.loader.dimension != dimension:
            self.loader.dimension = dimension
            if hasattr(self, "decode_refresh_timer"):
                self.decode_refresh_timer.start()

    def _refresh_decode(self):
        if self._closing or self.controller.entry is None:
            return
        if self.controller._waiting:
            self.decode_refresh_timer.start()
        else:
            self.controller.refresh_image()

    def _present(self, entry, frame):
        self._last_presented = entry
        self.surface.present(entry, frame)
        self._message(os.path.basename(entry.path))

    def _message(self, text):
        self._status = text
        width = min(480, max(200, self.width()-40))
        caption = self._notice+"\n"+text if self._notice else self.message.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, width-24)
        self.message.setText(caption)
        self.message.setToolTip(text)
        self._position_controls()

    def _show_notice(self, text, *, persistent=False):
        self._notice = text
        self._message(self._status)
        self.reveal_controls()
        self.notice_timer.stop()
        if not persistent:
            self.notice_timer.start()

    def _clear_notice(self):
        self._notice = ""
        self._message(self._status)

    def _refresh(self):
        if self.controller._waiting:
            self.surface.refresh(self._frozen_progress, self._frozen_strength)
        else:
            self._frozen_progress = self.controller.progress
            self._frozen_strength = self.controller.active_settings.strength
            self.surface.refresh(self._frozen_progress, self._frozen_strength)

    def _state_changed(self, state):
        label = self.t["slideshow_pause" if self.controller.playing else "slideshow_play"]
        self.buttons["play"].setAccessibleName(label)
        self.buttons["play"].setToolTip(label + "  ␣")
        self.buttons["play"].setIcon(IconFactory.get_icon("slideshow_pause_dark" if self.controller.playing else "slideshow_play_dark", 48))
        self._prevent_sleep(self.controller.playing)
        if state == "loading":
            self._message(self.t["slideshow_loading"])
        if state in ("paused", "stopped"):
            self.reveal_controls()

    def _prevent_sleep(self, active):
        if os.name == "nt" and active != self._sleep_active:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000003 if active else 0x80000000)
        self._sleep_active = active

    def toggle_pause(self):
        self.reveal_controls()
        self.controller.pause() if self.controller.playing else self.controller.resume()

    def next(self, reveal=True):
        if reveal:
            self.reveal_controls()
        self.controller.next()

    def previous(self, reveal=True):
        if reveal:
            self.reveal_controls()
        self.controller.previous()

    def change_speed(self, longer):
        """Up = more seconds per photo (slower), Down = fewer (faster); ~20% per press, at least 1 s."""
        current = self.controller.active_settings.duration
        step = max(1, round(current * 0.2))
        duration = self.controller.set_duration(current + step if longer else current - step)
        self.settingsChanged.emit(self.controller.settings)
        seconds = f"{duration:g}"
        self.toast.setText(self.t["slideshow_speed_notice"].format(seconds=seconds))
        self.toast.adjustSize()
        self.toast.move((self.width() - self.toast.width()) // 2, 24)
        self.toast.show()
        self.toast.raise_()
        self.toast_timer.start()

    def open_settings(self):
        was_playing = self.controller.playing
        self._editing_settings = True
        self.controller.pause()
        # Show where the window really is now (F11, double-click or the button may have changed it).
        fullscreen = self.isFullScreen()
        current = replace(self.controller.settings, fullscreen=fullscreen,
                          maximized=self.isMaximized() and not fullscreen)
        dialog = SettingsDialog(current, self.language, self, playback=True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.set_settings(dialog.settings())
            self._apply_mode(self.controller.settings)
            self.settingsChanged.emit(self.controller.settings)
        self._editing_settings = False
        if was_playing:
            self.controller.resume()

    def _apply_mode(self, settings):
        self._applied_mode = (settings.fullscreen, settings.maximized)
        wanted = (Qt.WindowState.WindowFullScreen if settings.fullscreen
                  else Qt.WindowState.WindowMaximized if settings.maximized
                  else Qt.WindowState.WindowNoState)
        current = self.windowState() & (Qt.WindowState.WindowFullScreen | Qt.WindowState.WindowMaximized)
        if current == wanted:
            self._update_fullscreen_control()
            return
        self._fullscreen_change = True
        self.setUpdatesEnabled(False)  # no half-resized frames while the window changes state
        try:
            if current & Qt.WindowState.WindowFullScreen and wanted == Qt.WindowState.WindowMaximized:
                self.showNormal()  # Qt drops a direct fullscreen -> maximized change
            self.setWindowState((self.windowState() & ~(Qt.WindowState.WindowFullScreen | Qt.WindowState.WindowMaximized)) | wanted)
            self.show()
        finally:
            self.setUpdatesEnabled(True)
            self._fullscreen_change = False
        self._update_decode_size()
        self._update_fullscreen_control()

    def toggle_fullscreen(self):
        self._fullscreen_change = True
        self.showNormal() if self.isFullScreen() else self.showFullScreen()
        self._fullscreen_change = False
        self._update_decode_size()
        self._update_fullscreen_control()

    def _set_idle_cursor(self, hidden):
        shape = Qt.CursorShape.BlankCursor if hidden else Qt.CursorShape.ArrowCursor
        for widget in (self, self.surface, self.surface.canvas):
            widget.setCursor(shape)

    def _update_fullscreen_control(self):
        icon = "slideshow_restore" if self.isFullScreen() else "slideshow_fullscreen"
        self.buttons["fullscreen"].setIcon(IconFactory.get_icon(icon, 48))
        self.buttons["close"].setVisible(self.isFullScreen() and not self.controls.isHidden())
        self.buttons["close"].raise_()

    def _position_controls(self):
        width = min(480, max(200, self.width()-40))
        self.controls.setFixedWidth(width)
        self.message.setMaximumWidth(width)
        height = self.controls.layout().totalHeightForWidth(width)
        if height < 0:
            height = self.controls.sizeHint().height()
        self.controls.setGeometry((self.width()-width)//2, max(12, self.height()-height-24), width, height)
        self.buttons["close"].move(self.width()-56, 20)

    def reveal_controls(self):
        if self._closing:
            return
        self._set_idle_cursor(False)
        self.controls.show()
        self.controls.raise_()
        self._position_controls()
        self._update_fullscreen_control()
        self.buttons["close"].raise_()
        self.hide_timer.start()

    def _hide_controls(self):
        focus = QApplication.focusWidget()
        focused = focus and (focus is self.controls or self.controls.isAncestorOf(focus) or focus is self.buttons["close"])
        if self.controller.playing and not focused:
            self.controls.hide()
            self.buttons["close"].hide()
            if self.isFullScreen() or self.isMaximized():
                self._set_idle_cursor(True)
        else:
            self.hide_timer.start()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.MouseMove, QEvent.Type.FocusIn):
            self.reveal_controls()
        elif event.type() == QEvent.Type.MouseButtonDblClick and obj in (self.surface, self.surface.canvas):
            self.toggle_fullscreen()
            return True
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if hasattr(self, "controller") and not self._closing and not self._editing_settings and not self._fullscreen_change:
            if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
                self.controller.pause()
            elif event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
                self.controller.pause()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "buttons") and "close" in self.buttons:
            self._position_controls()
        if hasattr(self, "loader"):
            self._update_decode_size()

    def event(self, event):
        result = super().event(event)
        if event.type() == getattr(QEvent.Type, "DevicePixelRatioChange", None) and hasattr(self, "loader"):
            self._update_decode_size()
        return result

    def done(self, result):
        self._shutdown()
        super().done(result)

    def closeEvent(self, event):
        self._shutdown()
        super().closeEvent(event)

    def _shutdown(self):
        if self._closing:
            return
        self._closing = True
        self.timer.stop()
        self.hide_timer.stop()
        self.decode_refresh_timer.stop()
        self.notice_timer.stop()
        self.toast_timer.stop()
        self.controller.close()
        self.surface.release()
        self._prevent_sleep(False)

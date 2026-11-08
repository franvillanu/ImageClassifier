"""Modal viewing window and localized slideshow preferences."""
import ctypes
import os
from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox,
                            QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                            QPushButton, QSpinBox, QVBoxLayout, QWidget)
from image_classifier.i18n.translations import translations
from image_classifier.imaging.loader import preview_dimension_for
from .controller import SlideshowController
from .loading import SlideLoader
from .settings import SlideshowSettings
from .surface import SlideSurface


class SettingsDialog(QDialog):
    def __init__(self, settings, language="en", parent=None, *, playback=False):
        super().__init__(parent)
        t = translations.get(language, translations["en"])
        self.setWindowTitle(t["slideshow"])
        self.setMinimumWidth(360)
        self.setStyleSheet("QWidget { color: white; background: #252525; } QAbstractSpinBox, QPushButton { padding: 7px; }")
        layout = QFormLayout(self)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(3,600)
        self.duration.setValue(settings.duration)
        layout.addRow(t["slideshow_duration"], self.duration)
        self.strength = QSpinBox()
        self.strength.setRange(0,100)
        self.strength.setSuffix("%")
        self.strength.setValue(int(settings.strength))
        layout.addRow(t["slideshow_strength"], self.strength)
        self.checks = {}
        for key in ("shuffle", "repeat", "fullscreen"):
            check = QCheckBox(t["slideshow_start_fullscreen" if key == "fullscreen" else "slideshow_"+key])
            check.setChecked(getattr(settings, key))
            self.checks[key] = check
            layout.addRow(check)
        if playback:
            layout.addRow(QLabel(t["slideshow_next_settings"]))
        buttons = QDialogButtonBox()
        buttons.addButton(t["slideshow_apply" if playback else "slideshow_start"], QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(t["slideshow_cancel"], QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def settings(self):
        return SlideshowSettings(self.duration.value(), self.strength.value(),
                                 **{key: check.isChecked() for key, check in self.checks.items()})


class PlayerWindow(QDialog):
    settingsChanged = pyqtSignal(object)

    def __init__(self, playlist, starting_image, settings, parent=None, *, language="en", raster=False):
        super().__init__(parent)
        self.language = language
        self.t = translations.get(language, translations["en"])
        self.setWindowTitle(self.t["slideshow"])
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(480,320)
        self.resize(1000,700)
        self.setStyleSheet("QWidget { background: black; color: white; } QPushButton { padding: 9px; background: #292929; border: 1px solid #666; } QPushButton:focus { border: 1px solid white; }")
        self._closing = False
        self._editing_settings = False
        self._fullscreen_change = False
        self._sleep_active = False
        self._last_presented = None
        self._frozen_progress = 0
        self._frozen_strength = settings.strength
        self._applied_fullscreen_preference = settings.fullscreen
        self._notice = ""
        self._status = self.t["slideshow_loading"]
        self.surface = SlideSurface(self, raster=raster)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.surface)
        self.controls = QWidget(self)
        controls_layout = QVBoxLayout(self.controls)
        self.message = QLabel(self.t["slideshow_loading"])
        self.message.setWordWrap(True)
        controls_layout.addWidget(self.message)
        row = QHBoxLayout()
        controls_layout.addLayout(row)
        self.buttons = {}
        for key, action in (("previous", self.previous), ("play", self.toggle_pause),
                            ("next", self.next), ("settings", self.open_settings),
                            ("fullscreen", self.toggle_fullscreen), ("close", self.close)):
            button = QPushButton(self.t["slideshow_"+key])
            button.clicked.connect(action)
            self.buttons[key] = button
            row.addWidget(button)
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
        for key, callback in (("Space", self.toggle_pause), ("Left", self.previous), ("Right", self.next),
                              ("F11", self.toggle_fullscreen), ("Escape", self.close)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
        self.surface.fallbackActivated.connect(self._install_tracking)
        self._install_tracking()
        QApplication.instance().aboutToQuit.connect(self._shutdown)
        QTimer.singleShot(0, self._start)

    def _install_tracking(self):
        for widget in (self, *self.findChildren(QWidget)):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def _start(self):
        if self._closing:
            return
        if self.controller.settings.fullscreen:
            self.showFullScreen()
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
        preference = self.controller.active_settings.fullscreen
        if preference != self._applied_fullscreen_preference:
            self._applied_fullscreen_preference = preference
            if self.isFullScreen() != preference:
                self.toggle_fullscreen()
        self._last_presented = entry
        self.surface.present(entry, frame)
        self._message(os.path.basename(entry.path))

    def _message(self, text):
        self._status = text
        self.message.setText(self._notice+"\n"+text if self._notice else text)

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
        self.buttons["play"].setText(self.t["slideshow_pause" if self.controller.playing else "slideshow_play"])
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

    def next(self):
        self.reveal_controls()
        self.controller.next()

    def previous(self):
        self.reveal_controls()
        self.controller.previous()

    def open_settings(self):
        was_playing = self.controller.playing
        self._editing_settings = True
        self.controller.pause()
        dialog = SettingsDialog(self.controller.settings, self.language, self, playback=True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.set_settings(dialog.settings())
            self.settingsChanged.emit(self.controller.settings)
        self._editing_settings = False
        if was_playing:
            self.controller.resume()

    def toggle_fullscreen(self):
        self._fullscreen_change = True
        self.showNormal() if self.isFullScreen() else self.showFullScreen()
        self._fullscreen_change = False
        self._update_decode_size()

    def reveal_controls(self):
        if self._closing:
            return
        self.controls.show()
        self.controls.raise_()
        self.hide_timer.start()

    def _hide_controls(self):
        focus = QApplication.focusWidget()
        if self.controller.playing and not (focus and (focus is self.controls or self.controls.isAncestorOf(focus))):
            self.controls.hide()
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
        if hasattr(self, "controls"):
            self.controls.setGeometry(12, max(0, self.height()-138), max(1,self.width()-24), 126)
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
        self.controller.close()
        self.surface.release()
        self._prevent_sleep(False)

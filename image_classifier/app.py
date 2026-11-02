import sys
import time
import traceback
import datetime
import os
import json
from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QMainWindow, QWidget, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QHBoxLayout, QScrollArea, QLayout, QDialog, QCheckBox,
    QRadioButton, QLineEdit, QSizePolicy, QSlider, QMenu, QGridLayout, QFrame, QProgressBar, QTabWidget, QGraphicsDropShadowEffect, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsOpacityEffect, QButtonGroup, QComboBox, QRubberBand, QListView, QProgressDialog,
    QStyledItemDelegate, QStyleOptionViewItem , QStyle, QStyleOptionSlider 
)
from PyQt6.QtGui import (
    QPixmap, QKeySequence, QShortcut, QWheelEvent, QMouseEvent, QCursor, QIcon,
    QPainter, QFont, QTransform, QColor, QGuiApplication, QImage, QVector3D, QPen, QKeyEvent, QBrush, QPalette, QOpenGLContext, QAction,
    QSurfaceFormat, QColorSpace
)
from PyQt6.QtCore import (
    Qt, QPoint, QTimer, QByteArray, QSize, QMimeData, QUrl, QObject, QEvent, QPropertyAnimation, QRect, QPointF, QEventLoop, QEasingCurve, pyqtSignal,
    QThread, QCoreApplication, QRect, QRectF, QRunnable, pyqtSlot, QThreadPool, QStandardPaths, QBuffer, QIODevice
)    
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLShaderProgram, QOpenGLShader, QOpenGLTexture
# Windows Shell (COM + open in Explorer); imaging (sharpen, loader); config; workers; UI
from image_classifier.shell_win import open_folder_and_select_item
from image_classifier.imaging import (
    ImageFrame,
    ImageLoaderRunnable,
    WorkerSignals,
    sharpen_cv2,
)
from image_classifier.imaging.loader import (
    PRIORITY_CURRENT,
    PRIORITY_FULL_RESOLUTION,
    PRIORITY_PRELOAD_AHEAD,
    PRIORITY_PRELOAD_NEXT,
    PRIORITY_PRELOAD_PREVIOUS,
    preview_dimension_for,
)
from image_classifier.config import get_config_file
from image_classifier.editor.editor_window import PhotoEditor
from image_classifier.editor.qtimage import qimage_to_rgba
from image_classifier.imaging.saver import save_rgba
from image_classifier.workers import ExportWorker, DeleteNonFavoritesWorker, SharpenThread
from image_classifier import __version__
from image_classifier.updates.controller import UpdateController
from image_classifier.ui.update_banner import UpdateBanner
from image_classifier.ui.whats_new import WhatsNewOverlay
from image_classifier.ui.icons import IconFactory
from image_classifier.ui.image_viewer import AdvancedGraphicsImageViewer
from image_classifier.ui.crop_overlay import CropOverlay
from image_classifier.ui.settings_panel import Segmented, SettingsPanel
from image_classifier.ui.scaling import scale_css, ui_scale
from image_classifier.ui.help_panel import HELP_STYLE, HelpContent
from image_classifier.ui.search_field import add_clear_button, matches as shortcut_matches
from image_classifier.ui.sharpness_overlay import SharpnessOverlay, SharpnessOverlayContent
from image_classifier.updates.notes import (
    format_release_date, load_release_notes, notes_for_version, pick, release_dates,
)
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
        self.norm_to_original = {}
        self._directory_cache = {}
        # path -> (token, loader) for neighbour preloads currently queued or decoding
        self._preload_inflight = {}
        self._preload_token = 0
        self._nav_direction = 1
        self._last_nav_attempt = 0.0
        self._last_nav_advance = 0.0
        self._marked_save_timer = QTimer(self)
        self._marked_save_timer.setSingleShot(True)
        self._marked_save_timer.setInterval(250)
        self._marked_save_timer.timeout.connect(self._write_marked_images)
        self.menu_dock_left = True
        self.loop_navigation = False
        self._first_image_loaded = True
        self.white_balance_enabled = False
        self.white_balance_gains = (1.0, 1.0, 1.0)
        self.load_config()
        ImageLoaderRunnable.configure_disk_cache(
            enabled=self.preview_cache_enabled,
            limit_mb=self.preview_cache_limit_mb,
        )
        self.init_ui()
        self.init_floating_controls()
        self.set_theme(self.theme)
        self.update_floating_controls()
        self.update_favorite_count()
        self.setup_shortcuts()
        self.floating_menu.settings_button.clicked.connect(self.open_settings_overlay)
        self.floating_menu.brightness_button.clicked.connect(lambda: self.open_editor("adjust"))
        self.show()
        QTimer.singleShot(0, self.initialize_viewer)
        self.updateLanguage()
        self.all_tooltips = []
        self.loading_in_progress = False
        self.init_updates()

    def init_updates(self):
        """Create the update controller/banner and schedule the silent startup check."""
        self.update_controller = UpdateController(self)
        self.update_banner = UpdateBanner(
            self, self.update_controller, lambda: self.current_language, self.install_update,
            self.open_update_notes,
        )
        QTimer.singleShot(1500, self.announce_new_version)
        if self.check_updates and (
            getattr(sys, "frozen", False) or os.environ.get("IMAGE_CLASSIFIER_FORCE_UPDATE_CHECK") == "1"
        ):
            QTimer.singleShot(3000, lambda: self.update_controller.check(manual=False))

    def open_whats_new(self, title, entries):
        """Release-notes overlay; shortcuts and the floating menu are off while it is open."""
        if getattr(self, "whats_new_overlay", None) is not None:
            return
        t = translations[self.current_language]
        self.disable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(False)
        self.whats_new_overlay = WhatsNewOverlay(
            self, title, entries, t["close_label"], t["whats_new_empty"], self._on_whats_new_closed,
            section_titles={"new": t["whats_new_section_new"], "changed": t["whats_new_section_changed"],
                            "fixed": t["whats_new_section_fixed"]},
            latest_text=t["whats_new_latest"],
        )
        self.whats_new_overlay.open_overlay()

    def _on_whats_new_closed(self):
        self.whats_new_overlay = None
        self.enable_all_shortcuts()
        if hasattr(self, "floating_menu") and self.floating_menu is not None:
            self.floating_menu.setEnabled(True)

    def announce_new_version(self):
        """Once after an update: show what changed in the version that just started."""
        if self.last_seen_version == __version__:
            return
        self.last_seen_version = __version__  # saved with the rest of the config
        entry = notes_for_version(__version__)
        if not entry:
            return
        t = translations[self.current_language]
        self.open_whats_new(
            t["whats_new_in"].format(version=__version__), [("", pick(entry, self.current_language))]
        )

    def open_update_notes(self, version, text):
        t = translations[self.current_language]
        self.open_whats_new(t["whats_new_in"].format(version=version), [("", text)])

    def open_release_history(self):
        t = translations[self.current_language]
        dates = release_dates()
        entries = [
            (f"v{e[0]}", pick(e, self.current_language), format_release_date(dates.get(e[0]), self.current_language))
            for e in load_release_notes()
        ]
        self.open_whats_new(t["whats_new_history"], entries)

    def check_for_updates_manually(self):
        self.update_controller.check(manual=True)

    def install_update(self):
        t = translations[self.current_language]
        busy = getattr(self, "export_thread", None) or getattr(self, "delete_thread", None)
        if busy:
            confirm = self.show_custom_dialog(t["update_busy_confirm"], icon_type="warning", buttons="yesno")
            if confirm != QDialog.DialogCode.Accepted:
                return
        self.save_config()
        # Only close if Windows actually started the installer (UAC may be declined).
        if self.update_controller.install(self.current_language):
            self.close()

    def set_check_updates(self, value: bool):
        self.check_updates = value
        self.save_config()

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
            
            # Try to disable Windows color management for consistent colors in fullscreen
            # This may help reduce color differences between fullscreen and windowed mode
            try:
                import ctypes
                from ctypes import wintypes
                # ICM_OFF = 1, ICM_ON = 2, ICM_QUERY = 3
                ICM_OFF = 1
                gdi32 = ctypes.windll.gdi32
                # Get window handle
                hwnd = int(self.winId()) if hasattr(self, 'winId') else None
                if hwnd:
                    hdc = ctypes.windll.user32.GetDC(hwnd)
                    if hdc:
                        # Try to disable ICM for this device context
                        gdi32.SetICMMode(hdc, ICM_OFF)
                        ctypes.windll.user32.ReleaseDC(hwnd, hdc)
            except Exception:
                # If Windows API call fails, continue anyway
                pass
            
            super().showFullScreen()
            self.is_fullscreen = True
            self.float_exit.show()
            
            # Force OpenGL context to refresh with sRGB color space
            vp = self.image_viewer.viewport()
            if isinstance(vp, QOpenGLWidget):
                vp.makeCurrent()
                vp.doneCurrent()
                QTimer.singleShot(50, lambda: vp.update())

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

        t = translations[self.current_language]
        en = self.current_language == "en"
        cache_label = "Cache previews on disk" if en else "Guardar vistas previas en disco"

        toggle_groups = [
            (t["settings_group_general"], [
                (t["update_check_startup"], self.check_updates, self.set_check_updates),
                (t["load_last_folder"], getattr(self, "load_last_folder", False), self.set_load_last_folder),
                (t["menu_dock_left"], self.menu_dock_left, self.toggle_menu_dock),
            ]),
            (t["settings_group_viewing"], [
                (t["loop_navigation"], self.loop_navigation, self.set_loop_navigation),
                (t["reset_zoom"], self.reset_zoom_on_new_image, self.set_reset_zoom),
                (t["rotate_all_option"], self.rotate_all, self.set_rotate_all),
                (t["show_filename"], self.show_filename, self.set_show_filename),
            ]),
            (t["settings_group_storage"], [
                (cache_label, self.preview_cache_enabled, self.set_preview_cache_enabled),
            ]),
        ]
        container = SettingsPanel(
            self.settings_overlay, t["options_title"], toggle_groups,
            t["about_button"], t["help_button"],
            self.open_about_overlay, self.open_help_overlay, self.close_settings_overlay,
            scale=ui_scale(self),
        )

        def cache_size_text(megabytes):
            return f"Preview cache: {megabytes:.0f} MB" if en else f"Caché de vistas previas: {megabytes:.0f} MB"

        cache_widgets = {}

        def clear_preview_cache():
            ImageLoaderRunnable.clear_disk_cache()
            cache_widgets["label"].setText(cache_size_text(0))

        cache_widgets["label"], _ = container.add_action_row(
            cache_size_text(ImageLoaderRunnable.disk_cache_size() / (1024 * 1024)),
            "Clear" if en else "Borrar",
            clear_preview_cache,
        )

        container.add_group_title(t["sort_by"])
        criterion_combo = OverlayComboBox(container.body)
        criterion_combo.addItem(t["sort_file_name"], "file_name")
        criterion_combo.addItem(t["sort_date_modified"], "date_modified")
        criterion_combo.addItem(t["sort_size"], "size")
        criterion_combo.setCurrentIndex(max(0, criterion_combo.findData(self.sort_option)))
        criterion_combo.currentIndexChanged.connect(
            lambda index: self.set_sort_option(criterion_combo.itemData(index))
        )
        container.add_control(criterion_combo)
        container.add_control(Segmented(
            [(t["sort_ascending"], True), (t["sort_descending"], False)],
            bool(self.sort_ascending), self.set_sort_ascending, scale=container.scale,
        ))

        container.add_group_title(t["theme"])
        theme_keys = ["black", "dark_grey", "inkstone"]
        container.add_control(Segmented(
            [(t[key], key) for key in theme_keys],
            self.theme if self.theme in theme_keys else "black", self.set_theme, scale=container.scale,
        ))

        container.add_group_title(t["language"])
        container.add_control(Segmented(
            [("English", "en"), ("Español", "es")], self.current_language, self.set_language,
            scale=container.scale,
        ))
        container.finish()

        # Never taller than the window: the body scrolls, the header and footer stay put
        container.setFixedHeight(min(container.preferred_height(), self.settings_overlay.height() - 40))

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
        y = max(y, 20) if container.height() <= self.settings_overlay.height() - 40 else 20

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
        S = ui_scale(self)
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
        container.setStyleSheet(scale_css(HELP_STYLE, S))

        # Instead of forcing a fixed size, set an initial size and use size policies.
        container.resize(round(920 * S), round(1000 * S))
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

        # Header, search field and the category list
        content = HelpContent(
            container, t["help_title"], t["help_search_placeholder"], t["help_no_results"],
            SHORTCUT_CATEGORIES, S, self.close_help_overlay,
        )
        self.shortcuts_search_line = content.search_line
        self.shortcut_rows = content.rows

        # Finally, show and raise the overlay.
        container.show()
        self.help_overlay.show()
        self.help_overlay.raise_()

        # Ensure the search bar gets focus immediately.
        QTimer.singleShot(0, lambda: self.shortcuts_search_line.setFocus(Qt.FocusReason.ActiveWindowFocusReason))

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
        container.setMinimumWidth(380)
        container.setStyleSheet("""
            QWidget#AboutContainer {
                background-color: #17181a;
                border-radius: 14px;
                border: 1px solid #3d4047;
            }
            QLabel { background-color: transparent; color: white; font-size: 15px; }
            QLabel#aboutAppName { font-size: 26px; font-weight: bold; }
            QLabel#aboutVersion {
                color: #8cc4ff; font-size: 14px;
                background-color: rgba(0, 120, 215, 55);
                border-radius: 11px; padding: 3px 14px;
            }
            QLabel#aboutCopyright { color: #8a8f98; font-size: 13px; }
            QFrame#aboutDivider { background-color: rgba(255, 255, 255, 30); border: none; }
            QPushButton {
                border: none; border-radius: 9px; padding: 10px 18px; font-size: 15px; color: white;
            }
            QPushButton#updateButton { background-color: #0078D7; }
            QPushButton#updateButton:hover { background-color: #1a8cea; }
            QPushButton#notesButton { background-color: #2b303a; }
            QPushButton#notesButton:hover { background-color: #3a414e; }
            QPushButton#closeButton { background-color: #DC3545; padding: 8px 30px; }
            QPushButton#closeButton:hover { background-color: #B22222; }
        """)
        # Size to content; padding from layout margins

        from PyQt6.QtCore import QSize
        from PyQt6.QtWidgets import QFrame
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 32, 40, 26)
        layout.setSpacing(0)
        center = Qt.AlignmentFlag.AlignCenter

        name_label = QLabel("\u2b50 " + t["photo_viewer_title"], container)
        name_label.setObjectName("aboutAppName")
        layout.addWidget(name_label, alignment=center)
        layout.addSpacing(10)

        version_label = QLabel(t["about_version"].format(version=__version__), container)
        version_label.setObjectName("aboutVersion")
        layout.addWidget(version_label, alignment=center)
        layout.addSpacing(24)

        update_btn = QPushButton(t["update_check_button"], container)
        update_btn.setObjectName("updateButton")
        update_btn.setIcon(IconFactory.get_icon("refresh", 18))
        update_btn.setIconSize(QSize(18, 18))
        update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        update_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        def on_check_updates():
            self.close_about_overlay()
            self.check_for_updates_manually()
        update_btn.clicked.connect(on_check_updates)
        layout.addWidget(update_btn)
        layout.addSpacing(8)

        notes_btn = QPushButton(t["whats_new_button"], container)
        notes_btn.setObjectName("notesButton")
        notes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        notes_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        def on_whats_new():
            self.close_about_overlay()
            self.open_release_history()
        notes_btn.clicked.connect(on_whats_new)
        layout.addWidget(notes_btn)
        layout.addSpacing(22)

        divider = QFrame(container)
        divider.setObjectName("aboutDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(16)

        copyright_label = QLabel(t["copyright_label"], container)
        copyright_label.setObjectName("aboutCopyright")
        copyright_label.setAlignment(center)
        layout.addWidget(copyright_label)
        layout.addSpacing(18)

        close_btn = QPushButton(t["close_label"], container)
        close_btn.setObjectName("closeButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(close_btn, alignment=center)

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

    def _invalidate_directory_cache(self, directory=None):
        if directory is None:
            self._directory_cache.clear()
            return

        norm_dir = os.path.normcase(os.path.abspath(directory))
        stale_keys = [key for key in self._directory_cache if key[0] == norm_dir]
        for key in stale_keys:
            self._directory_cache.pop(key, None)

    def _prune_marked_sets(self, valid_images=None):
        valid_set = set(valid_images or [])
        previous_favorites = len(self.favorites)
        previous_compare = len(self.compare_set)
        self.favorites.intersection_update(valid_set)
        self.compare_set.intersection_update(valid_set)
        return (
            len(self.favorites) != previous_favorites
            or len(self.compare_set) != previous_compare
        )

    def get_all_images(self):
        if not (self.current_directory and os.path.exists(self.current_directory)):
            self.norm_to_original = {}
            return []

        norm_dir = os.path.normcase(os.path.abspath(self.current_directory))
        cache_key = (norm_dir, self.sort_option, bool(self.sort_ascending))
        cached = self._directory_cache.get(cache_key)
        if cached is not None:
            self.norm_to_original = dict(cached["norm_to_original"])
            return list(cached["images"])

        entries = []
        norm_to_original = {}

        with os.scandir(self.current_directory) as scanner:
            for entry in scanner:
                if not entry.is_file():
                    continue
                if not entry.name.lower().endswith(ALLOWED_EXTENSIONS):
                    continue

                original_path = os.path.abspath(entry.path)
                norm_path = os.path.normcase(original_path)
                norm_to_original[norm_path] = original_path

                if self.sort_option == "file_name":
                    sort_key = (entry.name.lower(), norm_path)
                else:
                    try:
                        stat_result = entry.stat()
                    except OSError:
                        continue
                    if self.sort_option == "date_modified":
                        sort_key = (stat_result.st_mtime, norm_path)
                    elif self.sort_option == "size":
                        sort_key = (stat_result.st_size, norm_path)
                    else:
                        sort_key = (entry.name.lower(), norm_path)

                entries.append((sort_key, norm_path))

        entries.sort(key=lambda item: item[0])
        images = [norm_path for _, norm_path in entries]

        if not self.sort_ascending:
            images.reverse()

        self.norm_to_original = norm_to_original
        self._directory_cache[cache_key] = {
            "images": tuple(images),
            "norm_to_original": dict(norm_to_original),
        }
        return list(images)


    def update_scroll_area_margins(self):
        dock_width = 80
        container = self.centralWidget()
        if self.menu_dock_left:
            container.layout().setContentsMargins(dock_width, 0, 0, 0)
        else:
            container.layout().setContentsMargins(0, 0, 0, 0)

    def update_favorite_count(self):
        t = translations[self.current_language]
        all_images = self.get_all_images()
        self._prune_marked_sets(all_images)
        total_images = len(all_images)
        favorite_count = len(self.favorites)
        compare_count = len(self.compare_set)
        non_favorite_count = total_images - favorite_count
        layout = self.floating_menu.filter_button.layout()
        if layout is None:
            layout = QVBoxLayout(self.floating_menu.filter_button)
            self.floating_menu.filter_button.setLayout(layout)
            self.filter_button_icon_label = QLabel()
            self.filter_button_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.filter_button_count_label = QLabel()
            self.filter_button_count_label.setStyleSheet("color: white; font-size: 21px;")
            self.filter_button_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(4)
            shadow.setColor(QColor(0, 0, 0))
            shadow.setOffset(1, 1)
            self.filter_button_count_label.setGraphicsEffect(shadow)
            layout.addWidget(self.filter_button_icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
            layout.addSpacing(2)
            layout.addWidget(self.filter_button_count_label, alignment=Qt.AlignmentFlag.AlignCenter)
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
        self.filter_button_icon_label.setPixmap(icon.pixmap(36, 36))
        self.filter_button_count_label.setText(count_text)
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
        if hasattr(self, "update_banner") and self.update_banner.isVisible():
            self.update_banner.reposition()
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
                self.check_updates            = config.get('check_updates', True)
                self.last_seen_version        = config.get('last_seen_version')
                self.preview_cache_enabled    = config.get('preview_cache_enabled', True)
                self.preview_cache_limit_mb   = config.get('preview_cache_limit_mb', 1024)
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
                self.check_updates            = True
                self.last_seen_version        = __version__  # fresh install: nothing to announce
                self.preview_cache_enabled    = True
                self.preview_cache_limit_mb   = 1024
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
            self.check_updates            = True
            self.last_seen_version        = __version__
            self.preview_cache_enabled    = True
            self.preview_cache_limit_mb   = 1024

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
                'check_updates':           self.check_updates,
                'last_seen_version':       self.last_seen_version,
                'preview_cache_enabled':   self.preview_cache_enabled,
                'preview_cache_limit_mb':  self.preview_cache_limit_mb,
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def save_marked_images(self):
        self._marked_save_timer.start()

    def _write_marked_images(self):
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
        temp_path = json_path + ".tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, json_path)
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
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
        QShortcut(QKeySequence("B"), self, lambda: self.open_editor("adjust"))
        QShortcut(QKeySequence("Ctrl+E"), self, lambda: self.open_editor("crop"))
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
            self._nav_direction = 1
            self.show_image()

    def go_to_last_image(self):
        if self.image_files and self.current_index != len(self.image_files) - 1:
            # Save the currently displayed image as the "previous"
            self.previous_image = self.image_files[self.current_index]
            self.current_index = len(self.image_files) - 1
            self._nav_direction = -1
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
        image_patterns = " ".join(f"*{extension}" for extension in ALLOWED_EXTENSIONS)
        self.dialog.setNameFilter(f"Images ({image_patterns})")
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
                if f.lower().endswith(ALLOWED_EXTENSIONS)
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

    def set_preview_cache_enabled(self, value: bool):
        self.preview_cache_enabled = value
        ImageLoaderRunnable.configure_disk_cache(
            enabled=value,
            limit_mb=self.preview_cache_limit_mb,
        )
        self.save_config()

    def _starting_image_index(self, selected_file=None, start_at_first=False):
        norm_selected = (
            os.path.normcase(os.path.normpath(selected_file))
            if selected_file else None
        )
        norm_images = [
            os.path.normcase(os.path.normpath(path))
            for path in self.image_files
        ]
        if norm_selected and norm_selected in norm_images:
            return norm_images.index(norm_selected)
        if start_at_first:
            return 0
        return getattr(self, "last_index", 0)

    def load_directory(
        self,
        directory,
        selected_file=None,
        do_show=True,
        start_at_first=False,
    ):
        if self._marked_save_timer.isActive():
            self._marked_save_timer.stop()
            self._write_marked_images()

        # ——— Clear all per-image history when loading a new folder ———
        self._history.clear()
        self._modified.clear()
        self._current_path = None
        self._cancel_preloads()
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
            self.compare_set = set()
            self.norm_to_original = {}
            self._invalidate_directory_cache()
            self.current_index = -1
            self.save_config()
            self.update_favorite_count()
            return

        # Set up new directory & reset filters
        prev_filter = getattr(self, "current_filter", "all")
        self.current_directory = directory
        self._invalidate_directory_cache(directory)
        if prev_filter != "all":
            self.show_ephemeral_message(translations[self.current_language]["filter_reset_to_all"])
        self.current_filter = "all"
        self.show_all_images = True

        # Reload image list
        self.image_files = self.get_all_images()
        self.favorites = set()
        self.load_marked_images()
        self._prune_marked_sets(self.image_files)

        # Choose starting index
        if self.image_files:
            self.current_index = self._starting_image_index(
                selected_file=selected_file,
                start_at_first=start_at_first,
            )
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

        # ——— Phase 2: display current image before scheduling speculative work ———
        self.image_viewer.setImage(path, reset_zoom, preserve_zoom)

        # ——— Phase 3: preload screen-sized neighbours in the direction of travel ———
        self._schedule_preloads()

        # ——— Phase 4: refresh controls ———
        self.update_floating_controls()



    def _cancel_preloads(self):
        for _token, loader in self._preload_inflight.values():
            loader.cancel()
        self._preload_inflight.clear()

    def _preload_finished(self, path, token):
        entry = self._preload_inflight.get(path)
        if entry is not None and entry[0] == token:
            self._preload_inflight.pop(path, None)

    def _schedule_preloads(self):
        """Keep the next two photos (travel direction) and the previous one decoded.

        Preloads that fell out of that window are cancelled, so holding an arrow
        key never leaves a backlog of decodes for photos already skipped past.
        """
        total = len(self.image_files)
        if total <= 1 or not (0 <= self.current_index < total):
            self._cancel_preloads()
            return
        step = -1 if self._nav_direction < 0 else 1
        plan = (
            (step, PRIORITY_PRELOAD_NEXT),
            (-step, PRIORITY_PRELOAD_PREVIOUS),
            (2 * step, PRIORITY_PRELOAD_AHEAD),
        )
        current_path = self.image_files[self.current_index]
        targets = []
        for offset, priority in plan:
            index = self.current_index + offset
            if self.loop_navigation:
                index %= total
            elif not (0 <= index < total):
                continue
            path = self.image_files[index]
            if path != current_path and path not in (p for p, _ in targets):
                targets.append((path, priority))

        wanted = {path for path, _ in targets}
        for path in list(self._preload_inflight):
            if path not in wanted:
                self._preload_inflight.pop(path)[1].cancel()

        dimension = self.image_viewer.preview_dimension()
        for path, priority in targets:
            if path in self._preload_inflight:
                continue
            if (
                ImageLoaderRunnable.get_cached_preview(path, dimension) is not None
                or ImageLoaderRunnable.get_cached_image(path) is not None
            ):
                continue
            self._preload_token += 1
            token = self._preload_token
            loader = ImageLoaderRunnable(
                path,
                max_dimension=dimension,
                progressive=True,
                load_full=False,
            )
            done = lambda *_args, p=path, t=token: self._preload_finished(p, t)
            loader.signals.previewReady.connect(done)
            loader.signals.fullReady.connect(done)
            loader.signals.error.connect(done)
            self._preload_inflight[path] = (token, loader)
            loader.start(priority)

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

    # Held arrow key: a repeat only advances once the current photo is on screen,
    # at most ~14 photos/s, so every photo passed is actually drawn.
    NAV_REPEAT_GAP = 0.12       # key events closer than this count as a held key
    NAV_MIN_INTERVAL = 0.07
    NAV_STUCK_TIMEOUT = 1.5     # never block longer than this if a load never finishes

    def _nav_step_allowed(self):
        now = time.monotonic()
        repeating = now - self._last_nav_attempt < self.NAV_REPEAT_GAP
        self._last_nav_attempt = now
        if repeating:
            since_advance = now - self._last_nav_advance
            viewer = self.image_viewer
            shown = viewer._shown_load_id == viewer.current_load_id
            if since_advance < self.NAV_MIN_INTERVAL:
                return False
            if not shown and since_advance < self.NAV_STUCK_TIMEOUT:
                return False
        self._last_nav_advance = now
        return True

    def show_next_image(self):
        if not self._nav_step_allowed():
            return
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
        self._nav_direction = 1
        self.show_image()
        
    def show_previous_image(self):
        if not self._nav_step_allowed():
            return
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
        self._nav_direction = -1
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
        valid_images = set(self.image_files)
        json_path = os.path.join(self.current_directory, 'Favorites.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('directory') == self.current_directory:
                    self.favorites = {
                        os.path.normcase(os.path.abspath(item['full_path']))
                        for item in data.get('favorites', [])
                        if os.path.normcase(os.path.abspath(item['full_path'])) in valid_images
                    }
                    self.compare_set = {
                        os.path.normcase(os.path.abspath(item['full_path']))
                        for item in data.get('compare', [])
                        if os.path.normcase(os.path.abspath(item['full_path'])) in valid_images
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

        import send2trash

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
            ImageLoaderRunnable.drop_cached_pixmap(current_image)
            self._preload_inflight.pop(current_image, None)
            self._invalidate_directory_cache(self.current_directory)

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
                background-color: #17181a;
                border-radius: 12px;
                border: 1px solid #3d4047;
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
        if not self.image_viewer.full_resolution_ready:
            self.image_viewer.request_full_resolution()
            self.show_ephemeral_message(
                translations.get(
                    self.current_language,
                    translations["en"],
                ).get(
                    "full_resolution_loading",
                    "Full-resolution image is still loading.",
                )
            )
            return
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
                background-color: #17181a;
                border-radius: 12px;
                border: 1px solid #3d4047;
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
            "pixmap":          self.image_viewer.original_pixmap,
            "full_res":        self.image_viewer.full_resolution_ready,
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
        if self._marked_save_timer.isActive():
            self._marked_save_timer.stop()
            self._write_marked_images()
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
        if not self.image_viewer.full_resolution_ready:
            self.image_viewer.request_full_resolution()
            t = translations.get(self.current_language, translations["en"])
            self.show_ephemeral_message(
                t.get(
                    "full_resolution_loading",
                    "Full-resolution image is still loading.",
                )
            )
            return

        # 1) Determine the normalized path & original file path
        norm_path = self.image_files[self.current_index]
        orig_path = self.norm_to_original.get(norm_path, norm_path)
        orig_filename = os.path.basename(orig_path)
        folder = os.path.dirname(orig_path)

        # Grab the current QPixmap from the viewer (what the user sees right now)
        modified = self.image_viewer.renderFullResolution()
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

        # 3) Write it with the editor's saver: keeps EXIF/ICC (orientation reset, since the
        #    rotation is baked in), JPEG quality 95, and an atomic replace of the original.
        try:
            save_rgba(save_path, qimage_to_rgba(modified.toImage()), source_path=orig_path)
        except OSError as exc:
            self.show_custom_dialog(t["editor_save_failed"].format(error=exc), icon_type="error", buttons="ok")
            return

        self._finish_save(norm_path, save_path, overwrite)

    def _finish_save(self, norm_path, save_path, overwrite):
        """Refresh lists, caches and the view after ``save_path`` was written."""
        self._invalidate_directory_cache(os.path.dirname(save_path))

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
            ImageLoaderRunnable.drop_cached_pixmap(norm_path)

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
            for deleted_image in non_favorites:
                if not os.path.exists(deleted_image):
                    ImageLoaderRunnable.drop_cached_pixmap(deleted_image)
                    self._preload_inflight.pop(deleted_image, None)
            self._invalidate_directory_cache(self.current_directory)

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

    # ------------------------------------------------------------------ photo editor
    def open_editor(self, tab="crop"):
        """Open the non-destructive photo editor (Recortar / Ajuste) on the current image."""
        if getattr(self, "photo_editor", None) is not None:
            return
        if not self.image_files or self.current_index < 0:
            return
        t = translations.get(self.current_language, translations["en"])
        if not self.image_viewer.full_resolution_ready:
            self.image_viewer.request_full_resolution()
            self.show_ephemeral_message(t.get("full_resolution_loading", "Full-resolution image is still loading."))
            return
        pixmap = self.image_viewer.original_pixmap
        if pixmap is None or pixmap.isNull():
            return
        norm_path = self.image_files[self.current_index]
        orig_path = self.norm_to_original.get(norm_path, norm_path)
        folder, filename = os.path.split(orig_path)
        name, ext = os.path.splitext(filename)
        angle = int(self.image_viewer.rotation_angle or 0)
        rot90 = (angle // 90) % 4 if angle % 90 == 0 else 0

        self.disable_all_shortcuts()
        if getattr(self, "floating_menu", None) is not None:
            self.floating_menu.setEnabled(False)
        self.photo_editor = PhotoEditor(
            self, pixmap.toImage(), orig_path,
            language=self.current_language, rot90=rot90, tab=tab,
            # the viewer's brightness (B tool, gamma) maps 1:1 onto the editor's Brillo slider
            brightness=round((1.0 - (self.image_viewer.brightness_factor or 1.0)) * 200),
            copy_path_for=lambda: self.get_unique_copy_filename(folder, name, ext),
            background=getattr(self.image_viewer, "bg_color", "#000000"),
        )
        self.photo_editor.saved.connect(lambda path, overwrite: self._on_editor_saved(norm_path, path, overwrite))
        self.photo_editor.closed.connect(self._on_editor_closed)

    def _on_editor_saved(self, norm_path, save_path, overwrite):
        # The editor baked any pending quick-rotation and brightness into the saved pixels;
        # clear them so the viewer never applies them a second time.
        self.image_rotations[norm_path] = 0
        self.image_viewer.rotation_angle = 0
        self.image_viewer.brightness_factor = 1.0
        for key in (norm_path, getattr(self, "_current_path", None)):
            if key is not None:
                self.image_brightness.pop(key, None)
        self.image_viewer.cached_texture = None
        self._finish_save(norm_path, save_path, overwrite)
        if not overwrite:
            self.show_ephemeral_message(os.path.basename(save_path))

    def _on_editor_closed(self):
        self.photo_editor = None
        self.enable_all_shortcuts()
        if getattr(self, "floating_menu", None) is not None:
            self.floating_menu.setEnabled(True)
        self.setFocus()

    def open_crop_overlay(self):
        if not self.image_viewer.full_resolution_ready:
            self.image_viewer.request_full_resolution()
            self.show_ephemeral_message(
                translations.get(
                    self.current_language,
                    translations["en"],
                ).get(
                    "full_resolution_loading",
                    "Full-resolution image is still loading.",
                )
            )
            return
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
            "pixmap":          self.image_viewer.original_pixmap,
            "full_res":        self.image_viewer.full_resolution_ready,
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

    def _restore_snapshot_resolution(self, state):
        """Keep ``full_resolution_ready`` truthful after restoring an undo/redo snapshot.

        A snapshot taken before the full-resolution frame arrived holds the screen
        preview. Pixel edits (crop, sharpen, editor) require full resolution, so such a
        snapshot is always the unedited file: restore the full frame instead when it is
        cached, otherwise mark the view as preview-only (save/edit stay blocked) and
        fetch it. Without this, saving after an undo could write the downscaled preview.
        """
        viewer = self.image_viewer
        viewer._display_cache = None
        if state.get("full_res", True):
            viewer.full_resolution_ready = True
            return
        path = getattr(self, "_current_path", None)
        full = ImageLoaderRunnable.get_cached_image(path) if path else None
        if full is not None:
            viewer.original_pixmap = QPixmap.fromImage(full)
            viewer.full_resolution_ready = True
        else:
            viewer.full_resolution_ready = False
            viewer.request_full_resolution()

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
            "pixmap":          self.image_viewer.original_pixmap,
            "full_res":        self.image_viewer.full_resolution_ready,
            "rotation":        self.image_viewer.rotation_angle,
            "brightness":      self.image_viewer.brightness_factor,
            "image_modified":  self.image_modified,
            "from_crop":       state.get("from_crop", False),
        }
        hist["redo"].append(curr)

        # 3) Apply popped state
        self.image_viewer.original_pixmap   = state["pixmap"]
        self._restore_snapshot_resolution(state)
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
            "pixmap":          self.image_viewer.original_pixmap,
            "full_res":        self.image_viewer.full_resolution_ready,
            "rotation":        self.image_viewer.rotation_angle,
            "brightness":      self.image_viewer.brightness_factor,
            "image_modified":  self.image_modified,
            "from_crop":       state.get("from_crop", False),
        }
        hist["undo"].append(curr)

        # 3) Apply popped state
        self.image_viewer.original_pixmap   = state["pixmap"]
        self._restore_snapshot_resolution(state)
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
        if not self.image_viewer.full_resolution_ready:
            self.image_viewer.request_full_resolution()
            self.show_ephemeral_message(
                translations.get(
                    self.current_language,
                    translations["en"],
                ).get(
                    "full_resolution_loading",
                    "Full-resolution image is still loading.",
                )
            )
            return

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

"""Floating toolbar menu with icon buttons."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLayout
from PyQt6.QtCore import Qt, QSize

from image_classifier.ui.icons import IconFactory
from image_classifier.ui.dialogs import TooltipEventFilter
from image_classifier.i18n.translations import translations


class FloatingMenu(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tooltip_filters = {}
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background: transparent; border: none;")
        self.init_ui()
        self.hide()

    def _set_tooltip(self, button, texts, key):
        tooltip_filter = self._tooltip_filters.get(button)
        if tooltip_filter is None:
            tooltip_filter = TooltipEventFilter(lambda: texts[key], self)
            self._tooltip_filters[button] = tooltip_filter
            button.installEventFilter(tooltip_filter)
        else:
            tooltip_filter.tooltip_text_getter = lambda texts=texts, key=key: texts[key]

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        button_style = """
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 22px;
                min-width: 50px;
                max-width: 50px;
                min-height: 50px;
                max-height: 50px;
                text-align: center;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: transparent;
            }
        """

        t = translations["en"]

        self.open_button = QPushButton()
        self._set_tooltip(self.open_button, t, "select_folder")
        self.open_button.setIcon(IconFactory.get_icon("folder", 36))
        self.open_button.setIconSize(QSize(36, 36))
        self.open_button.setFixedSize(50, 50)

        self.export_button = QPushButton()
        self._set_tooltip(self.export_button, t, "export_favorites")
        self.export_button.setIcon(IconFactory.get_icon("export", 36))
        self.export_button.setIconSize(QSize(36, 36))
        self.export_button.setFixedSize(50, 50)

        self.rotate_button = QPushButton()
        self._set_tooltip(self.rotate_button, t, "rotate")
        self.rotate_button.setIcon(IconFactory.get_icon("rotate", 36))
        self.rotate_button.setIconSize(QSize(36, 36))
        self.rotate_button.setFixedSize(50, 50)

        self.brightness_button = QPushButton()
        self._set_tooltip(self.brightness_button, t, "brightness")
        self.brightness_button.setIcon(IconFactory.get_icon("brightness", 36))
        self.brightness_button.setIconSize(QSize(36, 36))
        self.brightness_button.setFixedSize(50, 50)

        self.sharpness_button = QPushButton()
        self._set_tooltip(self.sharpness_button, t, "sharpness")
        self.sharpness_button.setIcon(IconFactory.get_icon("sharpness", 36))
        self.sharpness_button.setIconSize(QSize(36, 36))
        self.sharpness_button.setFixedSize(50, 50)
        self.sharpness_button.clicked.connect(lambda: self.parent().open_sharpness_overlay())

        self.fullscreen_button = QPushButton()
        self._set_tooltip(self.fullscreen_button, t, "fullscreen")
        self.fullscreen_button.setIcon(IconFactory.get_icon("fullscreen", 36))
        self.fullscreen_button.setIconSize(QSize(36, 36))
        self.fullscreen_button.setFixedSize(50, 50)

        self.filter_button = QPushButton()
        self._set_tooltip(self.filter_button, t, "filter")
        self.filter_button.setIconSize(QSize(36, 36))
        self.filter_button.setFixedSize(60, 80)

        self.settings_button = QPushButton()
        self._set_tooltip(self.settings_button, t, "settings")
        self.settings_button.setIcon(IconFactory.get_icon("settings", 36))
        self.settings_button.setIconSize(QSize(36, 36))
        self.settings_button.setFixedSize(50, 50)

        self.crop_button = QPushButton(self)
        self._set_tooltip(self.crop_button, t, "crop")
        self.crop_button.setFixedSize(50, 50)
        self.crop_button.setIcon(IconFactory.get_icon("crop", 36))
        self.crop_button.setIconSize(QSize(36, 36))
        self.crop_button.clicked.connect(lambda: self.parent().open_crop_overlay())

        for btn in [
            self.open_button,
            self.export_button,
            self.crop_button,
            self.brightness_button,
            self.sharpness_button,
            self.rotate_button,
            self.fullscreen_button,
            self.filter_button,
            self.settings_button
        ]:
            btn.setStyleSheet(button_style)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def update_tooltips(self, t):
        self._set_tooltip(self.open_button, t, "select_folder")
        self._set_tooltip(self.export_button, t, "export_favorites")
        self._set_tooltip(self.rotate_button, t, "rotate")
        self._set_tooltip(self.crop_button, t, "crop")
        self._set_tooltip(self.brightness_button, t, "brightness")
        self._set_tooltip(self.sharpness_button, t, "sharpness")
        self._set_tooltip(self.fullscreen_button, t, "fullscreen")
        self._set_tooltip(self.filter_button, t, "filter")
        self._set_tooltip(self.settings_button, t, "settings")

"""Dialogs and overlay popups: help, tooltips, progress, ephemeral."""
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QTabWidget,
    QLayout,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt, QObject, QEvent, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPalette

from image_classifier.ui.widgets import BaseOverlay
from image_classifier.i18n.translations import translations


# ------------------------------------------------------------------------
# HelpDialog
# ------------------------------------------------------------------------
class HelpDialog(QDialog):
    def __init__(self, parent=None, icon_details=None):
        super().__init__(parent)
        lang = getattr(parent, "current_language", "en")
        t = translations.get(lang, translations["en"])
        self.setWindowTitle(t["help_dialog_title"])
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: rgba(0, 0, 0, 230);
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 8px;
            }}
            QLabel {{
                color: white;
                font-size: 17px;
                padding: 0;
                margin: 0;
            }}
            QPushButton {{
                background-color: #444444;
                color: white;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: #555555;
            }}
            QTabWidget::pane {{
                border: none;
            }}
            QTabBar::tab {{
                background-color: #333333;
                border-radius: 8px;
                padding: 10px 15px;
                margin: 2px;
                font-size: 16px; 
                color: white;
            }}
            QTabBar::tab:selected {{
                background-color: #0056b3;
            }}
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        icons_tab = QWidget()
        icons_tab_layout = QVBoxLayout(icons_tab)
        icons_tab_layout.setContentsMargins(10, 10, 10, 10)
        icons_tab_layout.setSpacing(8)
        table_layout = QGridLayout()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setHorizontalSpacing(30)
        table_layout.setVerticalSpacing(15)
        icon_header = QLabel(t["icon_header"])
        button_header = QLabel(t["button_header"])
        desc_header = QLabel(t["description_header"])
        icon_header.setStyleSheet("font-weight: bold;")
        button_header.setStyleSheet("font-weight: bold;")
        desc_header.setStyleSheet("font-weight: bold;")
        table_layout.addWidget(icon_header, 0, 0, alignment=Qt.AlignmentFlag.AlignHCenter)
        table_layout.addWidget(button_header, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        table_layout.addWidget(desc_header, 0, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        if not icon_details:
            icon_details = [
                (None, t["select_folder"],    t["help_select_folder"]),
                (None, t["export_favorites"], t["help_export_favorites"]),
                (None, t["rotate"],           t["help_rotate_image"]),
                (None, t["brightness"],       t["help_adjust_brightness"]),
                (None, t["fullscreen"],       t["help_toggle_fullscreen"]),
                (None, t["filter"],           t["help_adjust_brightness"]),
                (None, t["settings"],        t["help_settings"]),
            ]
        for row_index, (icon_obj, btn_text, desc_text) in enumerate(icon_details, start=1):
            icon_label = QLabel()
            if icon_obj:
                icon_label.setPixmap(icon_obj.pixmap(36, 36))
            table_layout.addWidget(icon_label, row_index, 0, alignment=Qt.AlignmentFlag.AlignHCenter)
            name_label = QLabel(btn_text)
            table_layout.addWidget(name_label, row_index, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            desc_label = QLabel(desc_text)
            table_layout.addWidget(desc_label, row_index, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        icons_tab_layout.addLayout(table_layout)
        icons_tab_layout.addStretch()
        self.tab_widget.addTab(icons_tab, t["help_tab_icons"])
        shortcuts_tab = QWidget()
        shortcuts_tab_layout = QVBoxLayout(shortcuts_tab)
        shortcuts_tab_layout.setContentsMargins(10, 10, 10, 10)
        shortcuts_tab_layout.setSpacing(15)
        shortcuts_table = QGridLayout()
        shortcuts_table.setHorizontalSpacing(10)
        shortcuts_table.setColumnStretch(0, 0)
        shortcuts_table.setColumnStretch(1, 0)
        shortcuts_table.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        header_key = QLabel(t["shortcut_key"])
        header_action = QLabel(t["shortcut_action"])
        header_key.setStyleSheet("font-weight: bold;")
        header_action.setStyleSheet("font-weight: bold;")
        shortcuts_table.addWidget(header_key, 0, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        shortcuts_table.addWidget(header_action, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        all_shortcuts = [
            (t["shortcut_left_key"],        t["shortcut_left_desc"]),
            (t["shortcut_right_key"],       t["shortcut_right_desc"]),
            (t["shortcut_up_key"],          t["shortcut_up_desc"]),
            (t["shortcut_down_key"],        t["shortcut_down_desc"]),
            (t["shortcut_pageup_key"],      t["shortcut_pageup_desc"]),
            (t["shortcut_pagedown_key"],    t["shortcut_pagedown_desc"]),
            (t["shortcut_mark_favorite_key"], t["shortcut_mark_favorite_key_desc"]),
            (t["shortcut_delete_key"],      t["shortcut_delete_desc"]),
            (t["shortcut_rotate_key"],      t["shortcut_rotate_desc"]),
            (t["shortcut_brightness_key"],  t["shortcut_brightness_desc"]),
            (t["shortcut_doubleclick_key"], t["shortcut_doubleclick_desc"]),
            (t["shortcut_f11_key"],         t["shortcut_f11_desc"]),
            (t["shortcut_escape_key"],      t["shortcut_escape_desc"]),
            (t["shortcut_mouse_key"],       t["shortcut_mouse_desc"]),
            (t["shortcut_open_key"],        t["shortcut_open_desc"]),
            (t["shortcut_export_key"],      t["shortcut_export_desc"]),
            (t["shortcut_toggle_menu_key"], t["shortcut_toggle_menu_desc"]),
            (t["shortcut_loop_key"],        t["shortcut_loop_desc"]),
            (t["shortcut_show_filename_key"], t["shortcut_show_filename_desc"]),
            (t["shortcut_reset_zoom_key"],    t["shortcut_reset_zoom_desc"]),
            (t["shortcut_dock_key"],        t["shortcut_dock_desc"]),
            (t["shortcut_toggle_compare_key"],        t["shortcut_toggle_compare_desc"]),
            (t["shortcut_toggle_compare_filter_key"], t["shortcut_toggle_compare_filter_desc"]),
            (t["shortcut_clear_compare_key"],         t["shortcut_clear_compare_desc"]),
            (t["shortcut_hide_nav_key"],    t["shortcut_hide_nav_desc"]),
            (t["shortcut_toggle_favorite_filter_key"],    t["shortcut_toggle_favorite_filter_desc"]),
        ]
        all_shortcuts = sorted(all_shortcuts, key=lambda s: s[0].lower())
        for row_idx, (key_text, action_text) in enumerate(all_shortcuts, start=1):
            key_label = QLabel(key_text)
            shortcuts_table.addWidget(key_label, row_idx, 0, alignment=Qt.AlignmentFlag.AlignLeft)
            action_label = QLabel(action_text)
            shortcuts_table.addWidget(action_label, row_idx, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        shortcuts_tab_layout.addLayout(shortcuts_table)
        shortcuts_tab_layout.addStretch()
        self.tab_widget.addTab(shortcuts_tab, f"{t['shortcuts_title']}")
        main_layout.addWidget(self.tab_widget)
        close_button = QPushButton(t["close_label"])
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
        close_button.clicked.connect(self.accept)
        main_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setLayout(main_layout)
        self.adjustSize()
        if parent:
            parent_rect = parent.geometry()
            x = parent_rect.center().x() - (self.width() // 2)
            y = parent_rect.center().y() - (self.height() // 2)
            self.move(x, y)


# ------------------------------------------------------------------------
# TooltipEventFilter
# ------------------------------------------------------------------------
class TooltipEventFilter(QObject):
    def __init__(self, tooltip_text_getter, parent=None):
        super().__init__(parent)
        self.tooltip_text_getter = tooltip_text_getter
        self.tooltip = None

    def eventFilter(self, obj, event):
        main_window = obj.window()
        if hasattr(main_window, "active_overlay") and main_window.active_overlay is not None and main_window.active_overlay.isVisible():
            return True
        if event.type() == QEvent.Type.ToolTip:
            return True
        elif event.type() == QEvent.Type.Enter:
            text = self.tooltip_text_getter()
            main_window = obj.window()
            self.tooltip = CustomTooltip(text, parent=main_window)
            if hasattr(main_window, "all_tooltips"):
                main_window.all_tooltips.append(self.tooltip)
            self.tooltip.show()
            self.tooltip.fadeIn()
            self.tooltip.adjustSize()
            TOOLTIP_X_OFFSET = 14
            icon_global = obj.mapToGlobal(QPoint(obj.width(), obj.height() // 2))
            pos = main_window.mapFromGlobal(icon_global)
            pos.setX(pos.x() + TOOLTIP_X_OFFSET)
            pos.setY(pos.y() - self.tooltip.height() // 2)
            self.tooltip.move(pos)
            return True
        elif event.type() == QEvent.Type.Leave:
            if self.tooltip:
                self.tooltip.fadeOut()
                self.tooltip.hide()
                main_window = obj.window()
                if hasattr(main_window, "all_tooltips") and self.tooltip in main_window.all_tooltips:
                    main_window.all_tooltips.remove(self.tooltip)
                self.tooltip = None
            return True
        return False


class LoadingKeyFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return True
        return False


# ------------------------------------------------------------------------
# CustomTooltip
# ------------------------------------------------------------------------
class CustomTooltip(BaseOverlay):
    def __init__(self, text, parent=None):
        super().__init__(parent, overlay_name="CustomTooltip", bg_color="transparent")
        self.label = QLabel(text, self)
        app = QApplication.instance()
        palette = app.palette()
        base_color = palette.color(QPalette.ColorRole.ToolTipBase)
        text_color = palette.color(QPalette.ColorRole.ToolTipText)
        r, g, b = base_color.red(), base_color.green(), base_color.blue()
        bg_rgba = f"rgba({r}, {g}, {b}, 200)"
        fg_hex = text_color.name()
        self.label.setStyleSheet(f"""
            background-color: {bg_rgba};
            color: {fg_hex};
            border-radius: 4px;
            padding: 5px;
            font-size: 15px;
        """)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.setContentsMargins(0, 0, 0, 0)
        self.adjustSize()
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(300)
        self.setWindowOpacity(0.0)

    def fadeIn(self):
        self.animation.stop()
        self.animation.setStartValue(self.windowOpacity())
        self.animation.setEndValue(1.0)
        self.animation.start()

    def fadeOut(self):
        self.animation.stop()
        self.animation.setStartValue(self.windowOpacity())
        self.animation.setEndValue(0.0)
        self.animation.start()


# ------------------------------------------------------------------------
# OverlayProgressDialog (determinate or indeterminate)
# ------------------------------------------------------------------------
class OverlayProgressDialog(QWidget):
    def __init__(self, title: str, message: str, parent: QWidget = None, indeterminate: bool = False):
        super().__init__(parent)
        self.worker_active = True
        if parent:
            self.setGeometry(parent.rect())
        from PyQt6.QtWidgets import QProgressBar
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.container = QWidget(self)
        self.container.setStyleSheet("""
            background-color: rgba(0, 0, 0, 220);
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 40);
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(30, 30, 30, 30)
        container_layout.setSpacing(15)
        self.titleLabel = QLabel(title, self.container)
        self.titleLabel.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: white;
            background-color: transparent;
            border: none;
        """)
        container_layout.addWidget(self.titleLabel)
        self.messageLabel = QLabel(message, self.container)
        self.messageLabel.setStyleSheet("""
            font-size: 18px;
            color: white;
            background-color: transparent;
            border: none;
        """)
        self.messageLabel.setWordWrap(False)
        container_layout.addWidget(self.messageLabel)
        self.progressBar = QProgressBar(self.container)
        if indeterminate:
            self.progressBar.setRange(0, 0)
            self.progressBar.setTextVisible(False)
        else:
            self.progressBar.setRange(0, 100)
        self.progressBar.setStyleSheet("""
            QProgressBar {
                background-color: #444;
                border-radius: 6px;
                text-align: center;
                font-size: 16px;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #0078D7;
                border-radius: 6px;
            }
        """)
        container_layout.addWidget(self.progressBar)
        self.cancelButton = QPushButton("Cancel", self.container)
        self.cancelButton.setStyleSheet("""
            QPushButton {
                background-color: #DC3545;
                color: white;
                border-radius: 6px;
                font-size: 16px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #B22222;
            }
        """)
        container_layout.addWidget(self.cancelButton)
        main_layout.addWidget(self.container, alignment=Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def setValue(self, value: int):
        self.progressBar.setValue(value)

    def showEvent(self, event):
        super().showEvent(event)
        self.container.adjustSize()
        new_x = (self.width() - self.container.width()) // 2
        new_y = (self.height() - self.container.height()) // 2
        self.container.move(new_x, new_y)


# ------------------------------------------------------------------------
# EphemeralPopup
# ------------------------------------------------------------------------
class EphemeralPopup(BaseOverlay):
    def __init__(self, message, parent=None):
        super().__init__(parent, overlay_name="EphemeralPopup", bg_color="transparent")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        self.container = QWidget(self)
        self.container.setStyleSheet("""
            background-color: rgba(0, 0, 0, 150);
            border-radius: 8px;
        """)
        label = QLabel(message, self.container)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: white; font-size: 22px; padding: 10px 20px;")
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        self.container.adjustSize()
        self.moveContainerToCenter()
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_anim.setDuration(500)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def moveContainerToCenter(self):
        overlay_rect = self.rect()
        container_rect = self.container.rect()
        new_pos = overlay_rect.center() - container_rect.center()
        self.container.move(new_pos)

    def fadeIn(self):
        self.fade_anim.stop()
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

    def fadeOut(self):
        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.start()

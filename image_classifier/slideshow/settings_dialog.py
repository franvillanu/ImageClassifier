"""Slideshow preferences dialog: sliders, switches and visual window-mode tiles."""
from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractButton, QButtonGroup, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                            QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)
from image_classifier.i18n.translations import translations
from image_classifier.ui.icons import IconFactory
from image_classifier.ui.settings_panel import ToggleSwitch
from .settings import SlideshowSettings

ACCENT = "#9db8e6"
RED = "#DC3545"

STYLE = f"""
    QDialog {{ background: #191c21; }}
    QDialog QWidget {{ background: transparent; }}
    QSlider {{ background: transparent; }}
    QLabel {{ color: #e8eaed; background: transparent; font-size: 14px; }}
    QLabel#title {{ color: #f4f6fa; font-size: 22px; font-weight: 600; }}
    QLabel#value {{ color: #f4f6fa; font-size: 15px; font-weight: 600; }}
    QLabel#hint {{ color: #aeb6c3; font-size: 12px; }}
    QLabel#key {{ color: #f4f6fa; background: #2a2f38; border: 1px solid #3b414c;
        border-bottom: 2px solid #3b414c; border-radius: 6px; padding: 2px 8px; font-size: 12px; font-weight: 600; }}
    QLabel#keyText {{ color: #c5ccd6; font-size: 13px; }}
    QLabel#section {{ color: #aeb6c3; font-size: 13px; }}
    QFrame#card {{ background: #20242b; border: 1px solid #2f3540; border-radius: 14px; }}
    QFrame#rule {{ background: #2f3540; border: none; }}
    QSlider::groove:horizontal {{ height: 6px; background: #3a4150; border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
    QSlider::handle:horizontal {{ width: 20px; height: 20px; margin: -7px 0; border-radius: 10px;
        background: #f4f6fa; border: 3px solid #20242b; }}
    QSlider::handle:horizontal:hover {{ background: white; }}
    QSlider:focus {{ outline: none; }}
    QPushButton {{ height: 46px; padding: 0 26px; border-radius: 12px; font-size: 14px; font-weight: 600; }}
    QPushButton#cancel {{ background: {RED}; color: white; border: none; }}
    QPushButton#cancel:hover {{ background: #e4505f; }}
    QPushButton#start {{ background: #007BFF; color: white; border: none; }}
    QPushButton#start:hover {{ background: #0056b3; }}
    QPushButton:focus {{ border: 2px solid #b9c9df; }}
"""


class ModeTile(QAbstractButton):
    """A selectable tile showing a miniature of the window mode it stands for."""

    def __init__(self, kind, text, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(104)

    def sizeHint(self):
        return QSize(120, 104)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        card = QRectF(1, 1, self.width() - 2, self.height() - 2)
        painter.setBrush(QColor("#1f2633" if on else "#2a2f38" if self.underMouse() else "#20242b"))
        painter.setPen(QPen(QColor(ACCENT if on else "#2f3540"), 2 if on else 1))
        painter.drawRoundedRect(card, 12, 12)
        screen = QRectF(card.left() + 14, card.top() + 12, card.width() - 28, 48)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2a3140"))
        painter.drawRoundedRect(screen, 5, 5)
        painter.setBrush(QColor(ACCENT if on else "#4a5366"))
        if self.kind == "fullscreen":
            painter.drawRoundedRect(screen, 5, 5)
        elif self.kind == "maximized":
            painter.drawRoundedRect(QRectF(screen.left(), screen.top(), screen.width(), screen.height() - 8), 5, 5)
            painter.setBrush(QColor("#5b6478"))
            painter.drawRoundedRect(QRectF(screen.left(), screen.bottom() - 7, screen.width(), 7), 3, 3)
        else:
            painter.drawRoundedRect(QRectF(screen.center().x() - screen.width() * .28,
                                           screen.center().y() - 15, screen.width() * .56, 30), 4, 4)
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setBold(on)
        painter.setFont(font)
        painter.setPen(QColor("#f4f6fa" if on else "#c5ccd6"))
        painter.drawText(QRectF(card.left(), screen.bottom() + 6, card.width(), 26),
                         Qt.AlignmentFlag.AlignCenter, self.text())
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#b9c9df"), 1))
            painter.drawRoundedRect(card.adjusted(-1, -1, 1, 1), 13, 13)


class DisclosureRow(QAbstractButton):
    """Quiet, checkable row: icon, label and a chevron that turns as the section opens (SPEC-002 SD-1/SD-3)."""

    def __init__(self, icon, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setAccessibleName(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._icon = icon
        self._angle = 0.0
        self._turn = QVariantAnimation(self)
        self._turn.setDuration(180)
        self._turn.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._turn.valueChanged.connect(self._set_angle)
        self.toggled.connect(self._animate_chevron)

    def sizeHint(self):
        return QSize(240, 40)

    def _set_angle(self, value):
        self._angle = float(value)
        self.update()

    def _animate_chevron(self, checked):
        self._turn.stop()
        self._turn.setStartValue(self._angle)
        self._turn.setEndValue(90.0 if checked else 0.0)
        self._turn.start()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.underMouse() or self.hasFocus():
            painter.setPen(QPen(QColor("#b9c9df"), 1) if self.hasFocus() else Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#20242b"))
            painter.drawRoundedRect(rect, 10, 10)
        self._icon.paint(painter, 12, (self.height() - 20) // 2, 20, 20)
        font = QFont(self.font())
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor("#aeb6c3"))
        painter.drawText(QRectF(42, 0, self.width() - 80, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        painter.translate(self.width() - 22, self.height() / 2)
        painter.rotate(self._angle)
        painter.setPen(QPen(QColor("#aeb6c3"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawPolyline([QPointF(-2.5, -5), QPointF(2.5, 0), QPointF(-2.5, 5)])


class SettingsDialog(QDialog):
    def __init__(self, settings, language="en", parent=None, *, playback=False):
        super().__init__(parent)
        t = translations.get(language, translations["en"])
        self.setWindowTitle(t["slideshow_settings_title"])
        self.setMinimumWidth(540)
        self.setStyleSheet(STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 20, 26, 20)
        root.setSpacing(12)
        title = QLabel(t["slideshow_settings_title"])
        title.setObjectName("title")
        root.addWidget(title)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 12, 20, 12)
        card_layout.setSpacing(10)
        duration = max(3, min(600, int(round(settings.duration))))
        self.duration_slider = self._slider(card_layout, t["slideshow_duration"], 3, max(120, duration),
                                            duration, lambda v: f"{v} s")
        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFixedHeight(1)
        card_layout.addWidget(rule)
        self.strength_slider = self._slider(card_layout, t["slideshow_strength"], 0, 100,
                                            int(settings.strength), lambda v: f"{v}%")
        root.addWidget(card)

        self.switches = {}
        toggles = QFrame()
        toggles.setObjectName("card")
        toggles_layout = QVBoxLayout(toggles)
        toggles_layout.setContentsMargins(20, 6, 20, 6)
        toggles_layout.setSpacing(0)
        for index, key in enumerate(("shuffle", "repeat", "new_motion_on_revisit")):
            if index:
                rule = QFrame()
                rule.setObjectName("rule")
                rule.setFixedHeight(1)
                toggles_layout.addWidget(rule)
            row = QHBoxLayout()
            row.setContentsMargins(0, 8, 0, 8)
            row.addWidget(QLabel(t["slideshow_" + key]), 1)
            switch = ToggleSwitch(scale=1.15)
            switch.setChecked(getattr(settings, key))
            self.switches[key] = switch
            row.addWidget(switch)
            toggles_layout.addLayout(row)
        root.addWidget(toggles)

        label = QLabel(t["slideshow_start_mode"])
        label.setObjectName("section")
        root.addWidget(label)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        current = "fullscreen" if settings.fullscreen else "maximized" if settings.maximized else "windowed"
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        for value in ("fullscreen", "maximized", "windowed"):
            tile = ModeTile(value, t["slideshow_mode_" + value])
            tile.setChecked(value == current)
            tile.setProperty("mode", value)
            self.mode_group.addButton(tile)
            tiles.addWidget(tile)
        root.addLayout(tiles)
        # Shortcut sheet collapsed by default behind a quiet row (SPEC-002 SD-1); animated (SD-2)
        self.shortcuts_toggle = DisclosureRow(IconFactory.get_icon("keyboard", 48), t["slideshow_shortcuts_toggle"])
        self.shortcuts_card = self._shortcuts(t)
        self.shortcuts_card.setMaximumHeight(0)
        self.shortcuts_card.hide()
        root.addWidget(self.shortcuts_toggle)
        root.addWidget(self.shortcuts_card)
        self._shortcuts_anim = QPropertyAnimation(self.shortcuts_card, b"maximumHeight", self)
        self._shortcuts_anim.setDuration(180)
        self._shortcuts_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._shortcuts_anim.valueChanged.connect(lambda _value: self.adjustSize())
        self._shortcuts_anim.finished.connect(self._shortcuts_settled)
        self.shortcuts_toggle.toggled.connect(self._set_shortcuts_expanded)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch(1)
        cancel = QPushButton(t["slideshow_cancel"])
        cancel.setObjectName("cancel")
        cancel.clicked.connect(self.reject)
        start = QPushButton(t["slideshow_apply" if playback else "slideshow_start"])
        start.setObjectName("start")
        start.setDefault(True)
        start.clicked.connect(self.accept)
        for button in (cancel, start):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        root.addSpacing(4)
        root.addLayout(buttons)

    def _set_shortcuts_expanded(self, expanded):
        card = self.shortcuts_card
        start = card.maximumHeight() if card.isVisible() else 0
        if start > card.sizeHint().height():
            start = card.height()
        if expanded:
            card.setMaximumHeight(start)
            card.show()
        self._shortcuts_anim.stop()
        self._shortcuts_anim.setStartValue(start)
        self._shortcuts_anim.setEndValue(card.sizeHint().height() if expanded else 0)
        self._shortcuts_anim.start()

    def _shortcuts_settled(self):
        card = self.shortcuts_card
        if self.shortcuts_toggle.isChecked():
            card.setMaximumHeight(16777215)  # natural height again (QWIDGETSIZE_MAX)
        else:
            card.hide()
        self.adjustSize()

    def _shortcuts(self, t):
        """Compact cheat sheet: three columns, each keycap row above its small label."""
        card = QFrame()
        card.setObjectName("card")
        outer = QHBoxLayout(card)
        outer.setContentsMargins(18, 12, 18, 12)
        outer.setSpacing(14)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        outer.addLayout(grid, 1)
        entries = (((t["slideshow_key_space"],), t["slideshow_key_pause"]),
                   (("←", "→"), t["slideshow_key_steps"]),
                   (("↑", "↓"), t["slideshow_key_speed"]),
                   (("R",), t["slideshow_key_rotate"]),
                   (("Ctrl / Shift", "←↑↓→"), t["slideshow_key_pan"]),
                   ((t["slideshow_key_wheel"], "+", "−"), t["slideshow_key_zoom"]),
                   ((t["slideshow_key_drag"],), t["slideshow_key_pan"]),
                   (("⌫", "0"), t["slideshow_key_reset_view"]),
                   (("F11",), t["slideshow_fullscreen"]),
                   (("Esc",), t["slideshow_close"]),
                   ((t["slideshow_key_mouse"],), t["slideshow_key_controls"]))
        for index, (keys, text) in enumerate(entries):
            cell = QVBoxLayout()
            cell.setSpacing(6)
            row = QHBoxLayout()
            row.setSpacing(4)
            for key in keys:
                chip = QLabel(key)
                chip.setObjectName("key")
                chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
                chip.setMinimumWidth(28)
                row.addWidget(chip)
            row.addStretch(1)
            cell.addLayout(row)
            label = QLabel(text)
            label.setObjectName("hint")
            label.setWordWrap(True)
            label.setMinimumWidth(60)
            cell.addWidget(label)
            grid.addLayout(cell, index // 3, index % 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        return card

    def _slider(self, layout, text, low, high, value, fmt):
        head = QHBoxLayout()
        head.addWidget(QLabel(text), 1)
        readout = QLabel(fmt(value))
        readout.setObjectName("value")
        head.addWidget(readout)
        layout.addLayout(head)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)
        slider.setFixedHeight(26)
        slider.setCursor(Qt.CursorShape.PointingHandCursor)
        slider.valueChanged.connect(lambda v: readout.setText(fmt(v)))
        layout.addWidget(slider)
        return slider

    def settings(self):
        mode = self.mode_group.checkedButton().property("mode")
        return SlideshowSettings(float(self.duration_slider.value()), self.strength_slider.value(),
                                 fullscreen=mode == "fullscreen", maximized=mode == "maximized",
                                 **{key: switch.isChecked() for key, switch in self.switches.items()})

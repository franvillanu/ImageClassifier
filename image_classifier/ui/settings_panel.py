"""Options panel: a header, a scrolling body of grouped settings, and a pinned footer.

The body scrolls, so the panel stays usable on small windows; the header (title and close)
and the footer (About, Help) never scroll out of sight.
"""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from image_classifier.ui.widgets import OverlayComboBox
from image_classifier.ui.scaling import px, scale_css

ACCENT = "#2a77c6"
PANEL_WIDTH = 360

SWITCH_ON = "#3498DB"  # the app's own blue (as the old checkboxes)
SEGMENT_ON = "#4a4f58"

# Every rule is scoped with #SettingsContainer so it beats the app-wide `QWidget { background: black }`
STYLE = f"""
    QWidget#SettingsContainer {{
        background-color: #17181a; border: 1px solid #3d4047; border-radius: 12px;
    }}
    #SettingsContainer QWidget {{ background: transparent; }}
    #SettingsContainer QLabel {{ color: #e8eaed; font-size: 15px; border: none; padding: 0; }}
    #SettingsContainer QLabel#panelTitle {{ color: white; font-size: 16px; font-weight: bold; }}
    #SettingsContainer QLabel#groupTitle {{ color: #9aa1ab; font-size: 12px; font-weight: bold; padding: 0; }}
    #SettingsContainer QFrame#rule {{ background-color: #2c3036; border: none; }}
    #SettingsContainer QWidget#Card {{ background-color: #1e2024; border: 1px solid #2c3036; border-radius: 10px; }}
    #SettingsContainer QWidget#ToggleRow:hover {{ background-color: #25282d; }}
    #SettingsContainer QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    #SettingsContainer QScrollBar::handle:vertical {{ background: #3a3e45; border-radius: 4px; min-height: 28px; }}
    #SettingsContainer QScrollBar::handle:vertical:hover {{ background: #4d525a; }}
    #SettingsContainer QScrollBar::add-line:vertical, #SettingsContainer QScrollBar::sub-line:vertical {{ height: 0; }}
    #SettingsContainer QScrollBar::add-page:vertical, #SettingsContainer QScrollBar::sub-page:vertical {{ background: transparent; }}
    #SettingsContainer QPushButton {{
        background-color: #3a3e45; color: white; border: 1px solid #4a4f58; border-radius: 8px;
        font-size: 13px; font-weight: bold; min-height: 34px; padding: 0 14px;
    }}
    #SettingsContainer QPushButton:hover {{ background-color: #4d525a; }}
    #SettingsContainer QPushButton#closeX {{ background: transparent; border: none; min-height: 36px; min-width: 36px; padding: 0; }}
    #SettingsContainer QPushButton#closeX:hover {{ background-color: #3a3e45; }}
    #SettingsContainer QPushButton#aboutBtn {{ background-color: {ACCENT}; border: none; min-height: 40px; }}
    #SettingsContainer QPushButton#aboutBtn:hover {{ background-color: #3586dc; }}
    #SettingsContainer QPushButton#helpBtn {{ background-color: #6b4fc4; border: none; min-height: 40px; }}
    #SettingsContainer QPushButton#helpBtn:hover {{ background-color: #7b5fd6; }}
    #SettingsContainer QWidget#Segmented {{ background-color: #0f1012; border: 1px solid #3a3e45; border-radius: 10px; }}
    #SettingsContainer QWidget#Segmented QPushButton {{
        background: transparent; border: none; color: #aab0b8; font-weight: normal; border-radius: 8px;
        min-height: 32px; padding: 0 8px;
    }}
    #SettingsContainer QWidget#Segmented QPushButton:hover {{ background-color: #202226; }}
    #SettingsContainer QWidget#Segmented QPushButton:checked {{ background-color: {SEGMENT_ON}; color: white; font-weight: bold; }}
    #SettingsContainer QComboBox {{
        min-height: 34px; background-color: #0f1012; color: white; font-size: 14px;
        border-radius: 8px; padding: 0 12px; border: 1px solid #3a3e45;
    }}
    #SettingsContainer QComboBox:hover {{ border-color: #6b717b; }}
    #SettingsContainer QComboBox::drop-down {{ border: none; width: 24px; }}
"""


def settings_panel_position(window_size, panel_size, x, margin=20):
    """Top-left of the Options panel (OV-4): vertically centred, horizontal `x` kept.

    Always inside the window (pinned to `margin` when the window is too small).
    """
    y = (window_size.height() - panel_size.height()) // 2
    x = min(x, window_size.width() - panel_size.width() - margin)
    y = min(y, window_size.height() - panel_size.height() - margin)
    return max(x, margin), max(y, margin)


class ToggleSwitch(QAbstractButton):
    """A checkable on/off switch (40x22 at scale 1)."""

    def __init__(self, parent=None, scale=1.0):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(px(40, scale), px(22, scale))

    def sizeHint(self):
        return self.size()

    def paintEvent(self, _event):
        w, h = self.width(), self.height()
        gap = h * 3 / 22
        knob = h - 2 * gap
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(SWITCH_ON if self.isChecked() else "#5b6068"))
        painter.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(w - gap - knob if self.isChecked() else gap, gap, knob, knob))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#8cc1ff"))
            painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), h / 2, h / 2)


class ToggleRow(QWidget):
    """Label on the left, switch on the right; clicking anywhere on the row flips it."""

    def __init__(self, label, checked, callback, parent=None, scale=1.0):
        super().__init__(parent)
        self.setObjectName("ToggleRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(px(44, scale))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(px(14, scale), 0, px(12, scale), 0)
        row.setSpacing(px(12, scale))
        text = QLabel(label, self)
        text.setWordWrap(True)
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.switch = ToggleSwitch(self, scale)
        self.switch.setChecked(bool(checked))
        self.switch.toggled.connect(lambda state: callback(bool(state)))
        row.addWidget(text, 1)
        row.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.switch.toggle()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class Segmented(QWidget):
    """Exclusive row of buttons; `options` is [(label, value)]."""

    def __init__(self, options, current, on_change, parent=None, scale=1.0):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(px(3, scale), px(3, scale), px(3, scale), px(3, scale))
        row.setSpacing(px(2, scale))
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for label, value in options:
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setChecked(value == current)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=value: on_change(v))
            self._group.addButton(button)
            row.addWidget(button, 1)


def _rule(parent):
    line = QFrame(parent)
    line.setObjectName("rule")
    line.setFixedHeight(1)
    return line


class SettingsPanel(QWidget):
    """Built from plain data so the app keeps owning what each setting does.

    toggle_groups: [(title, [(label, checked, callback(bool))])]
    """

    def __init__(self, parent, title, toggle_groups, about_text, help_text, on_about, on_help, on_close, scale=1.0):
        super().__init__(parent)
        self.scale = scale
        self.setObjectName("SettingsContainer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(scale_css(STYLE, scale))
        self.setFixedWidth(px(PANEL_WIDTH, scale))
        self._drag_offset = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(self)
        head_row = QHBoxLayout(header)
        head_row.setContentsMargins(px(18, scale), px(8, scale), px(8, scale), px(8, scale))
        heading = QLabel(title, header)
        heading.setObjectName("panelTitle")
        close_x = QPushButton("✕", header)
        close_x.setObjectName("closeX")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(on_close)
        head_row.addWidget(heading, 1)
        head_row.addWidget(close_x)
        outer.addWidget(header)
        outer.addWidget(_rule(self))
        self._header_height = header.sizeHint().height() + 1

        self.body = QWidget()
        # Never grow wider than the viewport (that would clip the switches under the scrollbar)
        self.body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(px(12, scale), 0, px(12, scale), px(14, scale))
        self.body_layout.setSpacing(0)
        for group_title, rows in toggle_groups:
            self.add_group_title(group_title)
            for label, checked, callback in rows:
                self._add(ToggleRow(label, checked, callback, self._card_widget, scale))

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(px(120, scale))
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

        outer.addWidget(_rule(self))
        footer = QWidget(self)
        foot_row = QHBoxLayout(footer)
        foot_row.setContentsMargins(px(12, scale), px(10, scale), px(12, scale), px(10, scale))
        foot_row.setSpacing(px(8, scale))
        about = QPushButton(about_text, footer)
        about.setObjectName("aboutBtn")
        help_btn = QPushButton(help_text, footer)
        help_btn.setObjectName("helpBtn")
        for button, callback in ((about, on_about), (help_btn, on_help)):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(callback)
            foot_row.addWidget(button, 1)
        outer.addWidget(footer)
        self._footer_height = footer.sizeHint().height() + 1

    # -- body builders ---------------------------------------------------
    def add_group_title(self, text):
        """Start a new group: a small caption, then a rounded card that the next rows go into."""
        header = QWidget(self.body)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(px(6, self.scale), px(18, self.scale), px(6, self.scale), px(8, self.scale))
        header_row.setSpacing(px(10, self.scale))
        label = QLabel(text.upper(), header)
        label.setObjectName("groupTitle")
        header_row.addWidget(label)
        header_row.addWidget(_rule(header), 1, Qt.AlignmentFlag.AlignVCenter)  # OV-5: GENERAL ──────
        self.body_layout.addWidget(header)
        self._card_widget = QWidget(self.body)
        self._card_widget.setObjectName("Card")
        self._card_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._card = QVBoxLayout(self._card_widget)
        self._card.setContentsMargins(0, 0, 0, 0)
        self._card.setSpacing(0)
        self.body_layout.addWidget(self._card_widget)

    def _add(self, widget):
        if self._card.count():  # thin divider between the rows of a card
            self._card.addWidget(_rule(self._card_widget))
        self._card.addWidget(widget)

    def add_control(self, widget):
        """A full-width control (segmented row, combo box) inside the current card."""
        holder = QWidget(self._card_widget)
        row = QHBoxLayout(holder)
        row.setContentsMargins(px(10, self.scale), px(8, self.scale), px(10, self.scale), px(8, self.scale))
        row.addWidget(widget)
        self._add(holder)

    def add_action_row(self, text, button_text, on_click):
        holder = QWidget(self._card_widget)
        holder.setMinimumHeight(px(52, self.scale))
        row = QHBoxLayout(holder)
        row.setContentsMargins(px(14, self.scale), 0, px(10, self.scale), 0)
        label = QLabel(text, holder)
        button = QPushButton(button_text, holder)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(on_click)
        row.addWidget(label, 1)
        row.addWidget(button)
        self._add(holder)
        return label, button

    def finish(self):
        self.body_layout.addStretch(1)

    def preferred_height(self):
        return self._header_height + self.body.sizeHint().height() + self._footer_height + 2

    # -- dragging (from any area that does not handle the mouse itself) ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            self.move(self.mapToParent(event.position().toPoint() - self._drag_offset))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
        super().mouseReleaseEvent(event)


__all__ = ["SettingsPanel", "Segmented", "ToggleRow", "ToggleSwitch", "OverlayComboBox", "PANEL_WIDTH"]

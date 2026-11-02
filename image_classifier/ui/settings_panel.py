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

ACCENT = "#2a77c6"
PANEL_WIDTH = 360

SWITCH_ON = "#2fa36b"
SEGMENT_ON = "#4a4f58"

# Every rule is scoped with #SettingsContainer so it beats the app-wide `QWidget { background: black }`
STYLE = f"""
    QWidget#SettingsContainer {{
        background-color: #17181a; border: 1px solid #4a4f58; border-radius: 14px;
    }}
    #SettingsContainer QWidget {{ background: transparent; }}
    #SettingsContainer QLabel {{ color: #e8eaed; font-size: 14px; border: none; padding: 0; }}
    #SettingsContainer QLabel#panelTitle {{ color: white; font-size: 16px; font-weight: bold; }}
    #SettingsContainer QLabel#groupTitle {{ color: #9aa1ab; font-size: 11px; font-weight: bold; }}
    #SettingsContainer QFrame#rule {{ background-color: #3a3e45; border: none; }}
    #SettingsContainer QWidget#ToggleRow:hover {{ background-color: #202226; border-radius: 8px; }}
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


class ToggleSwitch(QAbstractButton):
    """A checkable on/off switch (40x22)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self):
        return QSize(40, 22)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(SWITCH_ON if self.isChecked() else "#5b6068"))
        painter.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(21 if self.isChecked() else 3, 3, 16, 16))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#8cc1ff"))
            painter.drawRoundedRect(QRectF(0.5, 0.5, 39, 21), 10.5, 10.5)


class ToggleRow(QWidget):
    """Label on the left, switch on the right; clicking anywhere on the row flips it."""

    def __init__(self, label, checked, callback, parent=None):
        super().__init__(parent)
        self.setObjectName("ToggleRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(12)
        text = QLabel(label, self)
        text.setWordWrap(True)
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.switch = ToggleSwitch(self)
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

    def __init__(self, options, current, on_change, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
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

    def __init__(self, parent, title, toggle_groups, about_text, help_text, on_about, on_help, on_close):
        super().__init__(parent)
        self.setObjectName("SettingsContainer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE)
        self.setFixedWidth(PANEL_WIDTH)
        self._drag_offset = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(self)
        head_row = QHBoxLayout(header)
        head_row.setContentsMargins(18, 8, 8, 8)
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
        self.body_layout.setContentsMargins(8, 4, 8, 12)
        self.body_layout.setSpacing(0)
        for group_title, rows in toggle_groups:
            self.add_group_title(group_title)
            for label, checked, callback in rows:
                self.body_layout.addWidget(ToggleRow(label, checked, callback, self.body))

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(120)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

        outer.addWidget(_rule(self))
        footer = QWidget(self)
        foot_row = QHBoxLayout(footer)
        foot_row.setContentsMargins(12, 10, 12, 10)
        foot_row.setSpacing(8)
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
        label = QLabel(text.upper(), self.body)
        label.setObjectName("groupTitle")
        label.setContentsMargins(10, 14, 10, 6)
        self.body_layout.addWidget(label)

    def add_row(self, widget):
        self.body_layout.addWidget(widget)

    def add_control(self, widget):
        """A full-width control (segmented row, combo box) with side margins to line up with the rows."""
        holder = QWidget(self.body)
        row = QHBoxLayout(holder)
        row.setContentsMargins(10, 3, 10, 3)
        row.addWidget(widget)
        self.body_layout.addWidget(holder)

    def add_action_row(self, text, button_text, on_click):
        holder = QWidget(self.body)
        holder.setMinimumHeight(48)
        row = QHBoxLayout(holder)
        row.setContentsMargins(10, 0, 10, 0)
        label = QLabel(text, holder)
        button = QPushButton(button_text, holder)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(on_click)
        row.addWidget(label, 1)
        row.addWidget(button)
        self.body_layout.addWidget(holder)
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

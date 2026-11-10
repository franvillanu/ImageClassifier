"""Options drawer: a header, a search field, a scrolling body of titled sections and a pinned footer.

The drawer fills the window's right edge (SPEC-001 OV-4). The body scrolls, so it stays usable on
small windows; the header and the footer (About, Help) never scroll out of sight. The search field
filters the sections (OV-5); sections are a title plus a thin line, no cards (OV-6).
"""

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from image_classifier.ui.widgets import OverlayComboBox
from image_classifier.ui.scaling import px, scale_css

ACCENT = "#2a77c6"
PANEL_WIDTH = 460

SWITCH_ON = "#4aa8ff"
SWITCH_OFF = "#6b707a"
SEGMENT_ON = ACCENT

# Readability (SPEC-001 OV-7)
LABEL_PX = 16
GROUP_TITLE_PX = 14
CONTROL_MIN_HEIGHT = 44

# Every rule is scoped with #SettingsContainer so it beats the app-wide `QWidget { background: black }`
STYLE = f"""
    QWidget#SettingsContainer {{
        background-color: #18191c; border: none; border-left: 1px solid #3a3d44;
    }}
    #SettingsContainer QWidget {{ background: transparent; }}
    #SettingsContainer QLabel {{ color: #f2f3f5; font-size: {LABEL_PX}px; border: none; padding: 0; }}
    #SettingsContainer QLabel#panelTitle {{ color: white; font-size: 22px; font-weight: bold; }}
    #SettingsContainer QLabel#groupTitle {{ color: #8cc4ff; font-size: {GROUP_TITLE_PX}px; font-weight: bold; padding: 0; }}
    #SettingsContainer QLabel#noResults {{ color: #b4b9c2; padding: 24px 8px; }}
    #SettingsContainer QFrame#rule {{ background-color: #3a3d44; border: none; }}
    #SettingsContainer QWidget#ToggleRow:hover {{ background-color: #202226; border-radius: 10px; }}
    #SettingsContainer QLineEdit#search {{
        min-height: {CONTROL_MIN_HEIGHT}px; background-color: #0f1012; color: white; font-size: {LABEL_PX}px;
        border: 1px solid #3a3d44; border-radius: 12px; padding: 0 14px;
    }}
    #SettingsContainer QLineEdit#search:focus {{ border-color: {SWITCH_ON}; }}
    #SettingsContainer QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    #SettingsContainer QScrollBar::handle:vertical {{ background: #3a3e45; border-radius: 4px; min-height: 28px; }}
    #SettingsContainer QScrollBar::handle:vertical:hover {{ background: #4d525a; }}
    #SettingsContainer QScrollBar::add-line:vertical, #SettingsContainer QScrollBar::sub-line:vertical {{ height: 0; }}
    #SettingsContainer QScrollBar::add-page:vertical, #SettingsContainer QScrollBar::sub-page:vertical {{ background: transparent; }}
    #SettingsContainer QPushButton {{
        background-color: #2a2d33; color: white; border: 1px solid #5a5f69; border-radius: 10px;
        font-size: {LABEL_PX}px; font-weight: bold; min-height: {CONTROL_MIN_HEIGHT - 2}px; padding: 0 18px;
    }}
    #SettingsContainer QPushButton:hover {{ background-color: #3a3e45; }}
    #SettingsContainer QPushButton#closeX {{
        background: transparent; border: none; min-height: {CONTROL_MIN_HEIGHT}px; min-width: {CONTROL_MIN_HEIGHT}px;
        padding: 0; color: #c9cdd4; font-size: 20px;
    }}
    #SettingsContainer QPushButton#closeX:hover {{ background-color: #2a2d33; }}
    #SettingsContainer QPushButton#aboutBtn {{ background-color: {ACCENT}; border: none; min-height: {CONTROL_MIN_HEIGHT}px; }}
    #SettingsContainer QPushButton#aboutBtn:hover {{ background-color: #3586dc; }}
    #SettingsContainer QPushButton#helpBtn {{ background-color: #6b4fc4; border: none; min-height: {CONTROL_MIN_HEIGHT}px; }}
    #SettingsContainer QPushButton#helpBtn:hover {{ background-color: #7b5fd6; }}
    #SettingsContainer QWidget#Segmented {{ background-color: #111215; border: 1px solid #3a3d44; border-radius: 12px; }}
    #SettingsContainer QWidget#Segmented QPushButton {{
        background: transparent; border: none; color: #c9cdd4; font-weight: normal; border-radius: 9px;
        min-height: {CONTROL_MIN_HEIGHT - 8}px; padding: 0 8px;
    }}
    #SettingsContainer QWidget#Segmented QPushButton:hover {{ background-color: #202226; }}
    #SettingsContainer QWidget#Segmented QPushButton:checked {{ background-color: {SEGMENT_ON}; color: white; font-weight: bold; }}
    #SettingsContainer QComboBox {{
        min-height: {CONTROL_MIN_HEIGHT}px; background-color: #111215; color: white; font-size: {LABEL_PX}px;
        border-radius: 10px; padding: 0 14px; border: 1px solid #4a4e57;
    }}
    #SettingsContainer QComboBox:hover {{ border-color: #6b717b; }}
    #SettingsContainer QComboBox::drop-down {{ border: none; width: 24px; }}
"""


def settings_drawer_geometry(window_size, width):
    """The drawer's rectangle (OV-4): full window height, flush right, never wider than the window."""
    width = min(width, window_size.width())
    return QRect(window_size.width() - width, 0, width, window_size.height())


class ToggleSwitch(QAbstractButton):
    """A checkable on/off switch (40x22 at scale 1 by default; the drawer uses 48x28)."""

    def __init__(self, parent=None, scale=1.0, size=(40, 22)):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(px(size[0], scale), px(size[1], scale))

    def sizeHint(self):
        return self.size()

    def paintEvent(self, _event):
        w, h = self.width(), self.height()
        gap = h * 3 / 22
        knob = h - 2 * gap
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(SWITCH_ON if self.isChecked() else SWITCH_OFF))  # the slideshow dialog shares it
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
        self.setMinimumHeight(px(52, scale))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_text = label
        row = QHBoxLayout(self)
        row.setContentsMargins(px(10, scale), 0, px(8, scale), 0)
        row.setSpacing(px(16, scale))
        text = QLabel(label, self)
        text.setWordWrap(True)
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.switch = ToggleSwitch(self, scale, size=(48, 28))
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
        self.setMinimumHeight(px(CONTROL_MIN_HEIGHT, scale))
        self.search_text = " ".join(label for label, _ in options)
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

    def __init__(self, parent, title, toggle_groups, about_text, help_text, on_about, on_help, on_close, scale=1.0,
                 search_placeholder="Search settings…", no_results_text="No settings match your search"):
        super().__init__(parent)
        self.scale = scale
        self.setObjectName("SettingsContainer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(scale_css(STYLE, scale))
        self.setFixedWidth(px(PANEL_WIDTH, scale))
        self._groups = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(self)
        head_row = QHBoxLayout(header)
        head_row.setContentsMargins(px(28, scale), px(14, scale), px(14, scale), px(8, scale))
        heading = QLabel(title, header)
        heading.setObjectName("panelTitle")
        close_x = QPushButton("✕", header)
        close_x.setObjectName("closeX")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(on_close)
        head_row.addWidget(heading, 1)
        head_row.addWidget(close_x)
        outer.addWidget(header)

        search_holder = QWidget(self)
        search_row = QHBoxLayout(search_holder)
        search_row.setContentsMargins(px(28, scale), 0, px(28, scale), px(8, scale))
        self.search = QLineEdit(search_holder)
        self.search.setObjectName("search")
        self.search.setPlaceholderText(search_placeholder)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        search_row.addWidget(self.search)
        outer.addWidget(search_holder)

        self.no_results = QLabel(no_results_text, self)
        self.no_results.setObjectName("noResults")
        self.no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_results.setWordWrap(True)
        self.no_results.hide()
        outer.addWidget(self.no_results)

        self.body = QWidget()
        # Never grow wider than the viewport (that would clip the switches under the scrollbar)
        self.body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(px(28, scale), 0, px(28, scale), px(16, scale))
        self.body_layout.setSpacing(0)
        for group_title, rows in toggle_groups:
            self.add_group_title(group_title)
            for label, checked, callback in rows:
                self._add(ToggleRow(label, checked, callback, self._group_widget, scale))

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
        foot_row.setContentsMargins(px(28, scale), px(14, scale), px(28, scale), px(14, scale))
        foot_row.setSpacing(px(12, scale))
        about = QPushButton(about_text, footer)
        about.setObjectName("aboutBtn")
        help_btn = QPushButton(help_text, footer)
        help_btn.setObjectName("helpBtn")
        for button, callback in ((about, on_about), (help_btn, on_help)):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(callback)
            foot_row.addWidget(button, 1)
        outer.addWidget(footer)

    # -- body builders ---------------------------------------------------
    def add_group_title(self, text):
        """Start a new section: its title with a thin line after it, then the rows that follow (OV-6)."""
        header = QWidget(self.body)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, px(24, self.scale), 0, px(8, self.scale))
        header_row.setSpacing(px(14, self.scale))
        label = QLabel(text.upper(), header)
        label.setObjectName("groupTitle")
        header_row.addWidget(label)
        header_row.addWidget(_rule(header), 1, Qt.AlignmentFlag.AlignVCenter)
        self.body_layout.addWidget(header)
        self._group_widget = QWidget(self.body)
        self._group = QVBoxLayout(self._group_widget)
        self._group.setContentsMargins(0, 0, 0, 0)
        self._group.setSpacing(px(2, self.scale))
        self.body_layout.addWidget(self._group_widget)
        self._groups.append({"title": text, "header": header, "container": self._group_widget, "rows": []})

    def _add(self, widget, text=None):
        if text is None:
            text = getattr(widget, "search_text", "")
        self._group.addWidget(widget)
        self._groups[-1]["rows"].append((widget, text))

    @staticmethod
    def _combo_text(widget):
        if isinstance(widget, QComboBox):
            return " ".join(widget.itemText(i) for i in range(widget.count()))
        return getattr(widget, "search_text", "")

    def add_control(self, widget):
        """A full-width control (segmented row, combo box) inside the current section."""
        holder = QWidget(self._group_widget)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, px(6, self.scale), 0, px(6, self.scale))
        row.addWidget(widget)
        self._add(holder, self._combo_text(widget))

    def add_action_row(self, text, button_text, on_click):
        holder = QWidget(self._group_widget)
        holder.setMinimumHeight(px(56, self.scale))
        row = QHBoxLayout(holder)
        row.setContentsMargins(px(10, self.scale), 0, 0, 0)
        row.setSpacing(px(16, self.scale))
        label = QLabel(text, holder)
        button = QPushButton(button_text, holder)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(on_click)
        row.addWidget(label, 1)
        row.addWidget(button)
        self._add(holder, f"{text} {button_text}")
        return label, button

    def finish(self):
        self.body_layout.addStretch(1)

    # -- search (OV-5) ------------------------------------------------------
    def apply_filter(self, query=""):
        """Show only the rows whose label (or whose section title) contains `query`, case-insensitively."""
        needle = (query or "").strip().casefold()
        any_visible = False
        for group in self._groups:
            title_match = bool(needle) and needle in group["title"].casefold()
            visible = 0
            for widget, text in group["rows"]:
                show = not needle or title_match or needle in text.casefold()
                widget.setVisible(show)
                visible += show
            group["header"].setVisible(bool(visible))
            group["container"].setVisible(bool(visible))
            any_visible = any_visible or bool(visible)
        self.no_results.setVisible(bool(needle) and not any_visible)


__all__ = ["SettingsPanel", "Segmented", "ToggleRow", "ToggleSwitch", "OverlayComboBox", "PANEL_WIDTH",
           "settings_drawer_geometry"]

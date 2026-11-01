"""Editor widgets: straighten ruler, adjustment slider rows and shared styling."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from image_classifier.editor import icons
from image_classifier.editor.state import ANGLE_LIMIT

# Windows 11 dark palette
BG = "#1c1c1c"
BAR = "#202020"
PANEL = "#272727"
TEXT = "#ffffff"
TEXT_DIM = "#c5c5c5"
ACCENT = "#4cc2ff"
ACCENT_TEXT = "#000000"
HOVER = "rgba(255,255,255,0.08)"
PRESSED = "rgba(255,255,255,0.05)"

STYLE = f"""
QWidget#PhotoEditor, QWidget#EditorCanvasHost {{ background: {BG}; }}
QWidget#EditorTopBar, QWidget#EditorBottomBar {{ background: {BG}; }}
QWidget#EditorPanel {{ background: {BAR}; border-left: 1px solid #2d2d2d; }}
QLabel {{ color: {TEXT}; font-size: 13px; background: transparent; }}
QLabel#Dim {{ color: {TEXT_DIM}; }}
QLabel#GroupTitle {{ font-size: 14px; font-weight: 600; padding-top: 6px; }}
QToolButton {{
    color: {TEXT}; background: transparent; border: none; border-radius: 4px;
    padding: 6px 10px; font-size: 13px;
}}
QToolButton:hover {{ background: {HOVER}; }}
QToolButton:pressed {{ background: {PRESSED}; }}
QToolButton:disabled {{ color: #6d6d6d; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#Tab {{ padding: 8px 14px; border-radius: 0; border-bottom: 3px solid transparent; }}
QToolButton#Tab:checked {{ border-bottom: 3px solid {ACCENT}; }}
QToolButton#Primary {{ background: {ACCENT}; color: {ACCENT_TEXT}; padding: 7px 14px; }}
QToolButton#Primary:hover {{ background: #47b1e8; }}
QToolButton#Primary:disabled {{ background: #3a3a3a; color: #8a8a8a; }}
QToolButton#Secondary {{ background: #2d2d2d; padding: 7px 14px; border: 1px solid #353535; }}
QToolButton#Secondary:hover {{ background: #323232; }}
QMenu {{ background: #2c2c2c; color: {TEXT}; border: 1px solid #3a3a3a; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 7px 28px 7px 14px; border-radius: 4px; font-size: 13px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::item:checked {{ color: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: #9a9a9a; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: #9a9a9a; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; border: 5px solid #454545; width: 10px; height: 10px;
    margin: -8px 0; border-radius: 10px;
}}
QSlider::handle:horizontal:hover {{ border: 4px solid #454545; width: 12px; height: 12px; margin: -8px 0; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: #555; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def tool_button(icon_name: str | None = None, text: str = "", tooltip: str = "", parent=None,
                object_name: str | None = None, icon_size: int = 20) -> QToolButton:
    btn = QToolButton(parent)
    if icon_name:
        btn.setIcon(icons.icon(icon_name, icon_size))
        btn.setIconSize(QSize(icon_size, icon_size))
    if text:
        btn.setText(text)
        if icon_name:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    if tooltip:
        btn.setToolTip(tooltip)
    if object_name:
        btn.setObjectName(object_name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


class StraightenRuler(QWidget):
    """Horizontal tick ruler for the straighten angle, like Windows Photos.

    Drag to scrub (the ticks follow the pointer), wheel/arrow keys step 0.1 deg
    (Shift: 1 deg), double-click resets to 0. Values snap to 0 when close.
    """

    valueChanged = pyqtSignal(float)
    pressed = pyqtSignal()
    released = pyqtSignal()

    PX_PER_DEGREE = 10.5
    SNAP = 0.3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._drag_x = None
        self._drag_value = 0.0
        self._decimal = ","
        self.setMinimumSize(320, 44)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def set_decimal_separator(self, sep: str):
        self._decimal = sep
        self.update()

    def value(self) -> float:
        return self._value

    def setValue(self, v: float, emit: bool = False):
        v = round(max(-ANGLE_LIMIT, min(ANGLE_LIMIT, v)), 1)
        if v == self._value:
            return
        self._value = v
        self.update()
        if emit:
            self.valueChanged.emit(v)

    def text(self) -> str:
        v = 0.0 if abs(self._value) < 0.05 else self._value
        return f"{v:.1f}".replace(".", self._decimal).replace("-", "−") + " °"

    def sizeHint(self):
        return QSize(600, 44)

    # ---- painting
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        cx = w / 2.0
        mid_y = h * 0.62
        ppd = self.PX_PER_DEGREE
        first = int(max(-ANGLE_LIMIT, self._value - cx / ppd)) - 1
        last = int(min(ANGLE_LIMIT, self._value + cx / ppd)) + 1
        font = QFont(self.font())
        font.setPixelSize(12)
        p.setFont(font)
        for deg in range(first, last + 1):
            if abs(deg) > ANGLE_LIMIT:
                continue
            x = cx + (deg - self._value) * ppd
            fade = max(0.0, 1.0 - abs(x - cx) / (cx + 1))
            alpha = int(60 + 160 * fade)
            if deg == 0:
                p.setPen(QPen(QColor(255, 255, 255, 255), 1))
                p.drawText(QRectF(x - 12, mid_y - 9, 24, 18), Qt.AlignmentFlag.AlignCenter, "0")
                continue
            if deg % 5 == 0:
                p.setPen(QPen(QColor(255, 255, 255, alpha), 2))
                p.drawLine(QPointF(x, mid_y - 7), QPointF(x, mid_y + 7))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, alpha))
                p.drawEllipse(QPointF(x, mid_y), 1.3, 1.3)
        # centre indicator
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(QRectF(cx - 3, mid_y - 11, 6, 22), 3, 3)
        # value label
        p.setPen(QColor(255, 255, 255))
        font.setPixelSize(13)
        p.setFont(font)
        p.drawText(QRectF(0, 0, w, mid_y - 12), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 4, 4)
        p.end()

    # ---- interaction
    def _snap(self, v: float) -> float:
        return 0.0 if abs(v) < self.SNAP else v

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_x = e.position().x()
            self._drag_value = self._value
            self.pressed.emit()

    def mouseMoveEvent(self, e):
        if self._drag_x is None:
            return
        v = self._drag_value - (e.position().x() - self._drag_x) / self.PX_PER_DEGREE
        self.setValue(self._snap(v), emit=True)

    def mouseReleaseEvent(self, e):
        if self._drag_x is not None and e.button() == Qt.MouseButton.LeftButton:
            self._drag_x = None
            self.released.emit()

    def mouseDoubleClickEvent(self, e):
        self.pressed.emit()
        self.setValue(0.0, emit=True)
        self.released.emit()

    def _step(self, delta: float):
        self.pressed.emit()
        self.setValue(self._value + delta, emit=True)
        self.released.emit()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0 or e.angleDelta().x() / 120.0
        if steps:
            big = e.modifiers() & Qt.KeyboardModifier.ShiftModifier
            self._step(-steps * (1.0 if big else 0.1))
        e.accept()

    def keyPressEvent(self, e):
        big = e.modifiers() & Qt.KeyboardModifier.ShiftModifier
        step = 1.0 if big else 0.1
        if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self._step(-step)
        elif e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self._step(step)
        elif e.key() == Qt.Key.Key_0:
            self._step(-self._value)
        else:
            super().keyPressEvent(e)


class _ResetSlider(QSlider):
    doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        e.accept()

    def wheelEvent(self, e):
        # Don't hijack scrolling of the panel unless the slider has focus.
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class AdjustSlider(QWidget):
    """One Ajuste row: icon + label + value, slider -100..100 below. Double-click resets."""

    valueChanged = pyqtSignal(str, int)  # live
    committed = pyqtSignal(str)  # gesture finished

    def __init__(self, name: str, label: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.name = name
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(icons.icon(icon_name, 16).pixmap(16, 16))
        self.label = QLabel(label)
        self.value_label = QLabel("0")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(ic)
        top.addWidget(self.label, 1)
        top.addWidget(self.value_label)
        self.slider = _ResetSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(-100, 100)
        self.slider.setPageStep(10)
        self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 10)
        lay.setSpacing(8)
        lay.addLayout(top)
        lay.addWidget(self.slider)
        self.slider.valueChanged.connect(self._on_value)
        self.slider.sliderReleased.connect(lambda: self.committed.emit(self.name))
        self.slider.doubleClicked.connect(self.reset)

    def _on_value(self, v: int):
        self.value_label.setText(str(v))
        self.valueChanged.emit(self.name, v)
        if not self.slider.isSliderDown():
            self.committed.emit(self.name)  # keyboard / click-on-track: one step = one undo entry

    def set_value(self, v: int):
        self.slider.blockSignals(True)
        self.slider.setValue(int(v))
        self.slider.blockSignals(False)
        self.value_label.setText(str(int(v)))

    def reset(self):
        if self.slider.value() != 0:
            self.slider.setValue(0)

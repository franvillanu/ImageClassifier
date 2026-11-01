"""Editor widgets and styling, modelled on the Windows 11 Photos editor."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from image_classifier.editor import icons
from image_classifier.editor.state import ANGLE_LIMIT

# Windows 11 dark palette
BG = "#1c1c1c"
PANEL = "#202020"
TEXT = "#ffffff"
TEXT_DIM = "#cfcfcf"
TEXT_OFF = "#777777"
ACCENT = "#4cc2ff"
ACCENT_HOVER = "#48b2e9"
ACCENT_TEXT = "#000000"
FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'

STYLE = f"""
QWidget#PhotoEditor {{ background: {BG}; font-family: {FONT}; }}
QWidget#EditorTopBar, QWidget#EditorBottomBar {{ background: {BG}; }}
QWidget#EditorPanel {{ background: {PANEL}; border-left: 1px solid #2b2b2b; }}
QLabel {{ color: {TEXT}; font-size: 14px; background: transparent; font-family: {FONT}; }}
QLabel#Dim {{ color: {TEXT_DIM}; font-size: 13px; }}
QLabel#GroupTitle {{ font-size: 14px; font-weight: 600; }}
QToolButton {{
    color: {TEXT}; background: transparent; border: none; border-radius: 4px;
    padding: 0px 10px; min-height: 32px; font-size: 14px; font-family: {FONT};
}}
QToolButton:hover {{ background: rgba(255,255,255,0.07); }}
QToolButton:pressed {{ background: rgba(255,255,255,0.04); color: {TEXT_DIM}; }}
QToolButton:disabled {{ color: {TEXT_OFF}; }}
QToolButton::menu-indicator {{ image: none; width: 0px; }}
QToolButton#Icon {{ padding: 0px; min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px; }}
QToolButton#Tab {{ padding: 0px 12px; min-height: 40px; }}
QToolButton#Tab:hover {{ background: transparent; }}
QToolButton#Primary {{ background: {ACCENT}; color: {ACCENT_TEXT}; padding: 0px 12px; }}
QToolButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QToolButton#Primary:pressed {{ background: #42a1d2; color: #1a1a1a; }}
QToolButton#Primary:disabled {{ background: #3b3b3b; color: #8b8b8b; }}
QToolButton#Secondary {{ background: #2d2d2d; border: 1px solid #383838; padding: 0px 14px; }}
QToolButton#Secondary:hover {{ background: #323232; }}
QMenu {{
    background: #2c2c2c; color: {TEXT}; border: 1px solid #3a3a3a; border-radius: 8px;
    padding: 4px; font-size: 14px; font-family: {FONT};
}}
QMenu::item {{ padding: 8px 32px 8px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: rgba(255,255,255,0.07); }}
QMenu::item:checked {{ color: {ACCENT}; }}
QMenu::indicator {{ width: 0px; }}
QMenu::separator {{ height: 1px; background: #3a3a3a; margin: 4px 6px; }}
QSlider {{ min-height: 24px; }}
QSlider::groove:horizontal {{ height: 4px; background: #8a8a8a; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: #8a8a8a; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; border: 5px solid #454545; width: 10px; height: 10px;
    margin: -8px 0px; border-radius: 10px;
}}
QSlider::handle:horizontal:hover {{ border: 4px solid #454545; width: 12px; height: 12px; }}
QSlider::handle:horizontal:pressed {{ border: 6px solid #454545; width: 8px; height: 8px; }}
QFrame#DialogBack {{ background: rgba(0,0,0,0.45); }}
QFrame#DialogCard {{ background: #2b2b2b; border: 1px solid #3d3d3d; border-radius: 8px; }}
QWidget#DialogFooter {{
    background: #202020; border-top: 1px solid #353535;
    border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
}}
QLabel#DialogTitle {{ font-size: 20px; font-weight: 600; }}
QLabel#DialogBody {{ font-size: 14px; color: {TEXT_DIM}; }}
QToolButton#Primary, QToolButton#Secondary {{ min-height: 32px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #5a5a5a; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


def ui_font(px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """The Windows 11 UI font for text we paint ourselves (stylesheets don't reach QPainter)."""
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPixelSize(px)
    font.setWeight(weight)
    return font


def tool_button(icon_name: str | None = None, text: str = "", tooltip: str = "", parent=None,
                object_name: str | None = None, icon_size: int = 16) -> QToolButton:
    btn = QToolButton(parent)
    if icon_name:
        btn.setIcon(icons.icon(icon_name, icon_size))
        btn.setIconSize(QSize(icon_size, icon_size))
    if text:
        btn.setText(" " + text if icon_name else text)
        if icon_name:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    elif icon_name and object_name is None:
        object_name = "Icon"
    if tooltip:
        btn.setToolTip(tooltip)
    if object_name:
        btn.setObjectName(object_name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


class TabButton(QToolButton):
    """Icon + label tab with the short Windows accent pill under the active one."""

    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Tab")
        self.setCheckable(True)
        self.setText(" " + text)  # en space: Windows-like icon/label gap
        self.setIcon(icons.icon(icon_name, 16))
        self.setIconSize(QSize(16, 16))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.isChecked():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            w = 16.0
            p.drawRoundedRect(QRectF((self.width() - w) / 2, self.height() - 3, w, 3), 1.5, 1.5)
            p.end()


class IconLabel(QWidget):
    """Paints a QIcon at the widget's real device pixel ratio (crisp at any scaling)."""

    def __init__(self, icon: QIcon, size: int = 16, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, _e):
        p = QPainter(self)
        self._icon.paint(p, self.rect())
        p.end()


class StraightenRuler(QWidget):
    """Horizontal tick ruler for the straighten angle, like Windows Photos.

    Drag to scrub (the ticks follow the pointer), wheel/arrow keys step 0.1 deg
    (Shift: 1 deg), double-click resets to 0. Values snap to 0 when close.
    """

    valueChanged = pyqtSignal(float)
    pressed = pyqtSignal()
    released = pyqtSignal()

    PX_PER_DEGREE = 10.0
    SNAP = 0.3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._drag_x = None
        self._drag_value = 0.0
        self._decimal = ","
        self.setFixedHeight(60)
        self.setMinimumWidth(320)
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
        return f"{v:.1f}".replace(".", self._decimal).replace("-", "−") + "°"

    def sizeHint(self):
        return QSize(600, 60)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        cx = w / 2.0
        base = h - 18.0  # tick baseline; labels sit below it
        ppd = self.PX_PER_DEGREE
        first = int(max(-ANGLE_LIMIT, self._value - cx / ppd)) - 1
        last = int(min(ANGLE_LIMIT, self._value + cx / ppd)) + 1
        p.setFont(ui_font(11))
        for deg in range(first, last + 1):
            if abs(deg) > ANGLE_LIMIT:
                continue
            x = cx + (deg - self._value) * ppd
            fade = max(0.0, 1.0 - (abs(x - cx) / (cx + 1)) ** 3)
            if fade <= 0:
                continue
            major = deg % 5 == 0
            length = 10.0 if major else 5.0
            p.setPen(QPen(QColor(255, 255, 255, int((150 if major else 80) * fade)), 1))
            p.drawLine(QPointF(round(x) + 0.5, base - length), QPointF(round(x) + 0.5, base))
            if deg % 15 == 0 and abs(x - cx) > 14:
                p.setPen(QColor(255, 255, 255, int(130 * fade)))
                label = str(deg).replace("-", "−")
                p.drawText(QRectF(x - 20, base + 3, 40, 14), Qt.AlignmentFlag.AlignCenter, label)
        # indicator: accent needle through the ticks
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT))
        p.drawRoundedRect(QRectF(cx - 1.5, base - 18, 3, 22), 1.5, 1.5)
        p.setFont(ui_font(14, QFont.Weight.DemiBold))
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(0, 0, w, base - 20), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                   self.text())
        p.end()

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


class AspectStrip(QWidget):
    """Row of aspect-ratio choices, each drawn at its true proportions (Windows Photos style).

    Items are ``(label, ratio)`` where ratio is ``None`` (free), ``"original"`` or a float.
    """

    picked = pyqtSignal(int)

    ICON_BOX = 44.0  # hover/selection square
    SHAPE = 22.0  # longest side of a ratio shape

    def __init__(self, items: list[tuple[str, object]], parent=None):
        super().__init__(parent)
        self._items = items
        self._current = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setFixedHeight(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_current(self, index: int):
        if index != self._current:
            self._current = index
            self.update()

    def _item_width(self) -> float:
        return max(56.0, min(96.0, self.width() / max(1, len(self._items))))

    def _origin(self) -> float:
        return (self.width() - self._item_width() * len(self._items)) / 2.0

    def _index_at(self, x: float) -> int:
        i = int((x - self._origin()) // self._item_width())
        return i if 0 <= i < len(self._items) else -1

    def sizeHint(self):
        return QSize(int(76 * len(self._items)), 80)

    def minimumSizeHint(self):
        return QSize(int(56 * len(self._items)), 80)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        iw = self._item_width()
        x0 = self._origin()
        for i, (label, ratio) in enumerate(self._items):
            cx = x0 + iw * (i + 0.5)
            box = QRectF(cx - self.ICON_BOX / 2, 4, self.ICON_BOX, self.ICON_BOX)
            selected = i == self._current
            if selected or i == self._hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 22 if selected else 12))
                p.drawRoundedRect(box, 6, 6)
            color = QColor(TEXT if selected or i == self._hover else TEXT_DIM)
            self._paint_shape(p, box.center(), ratio, color)
            p.setFont(ui_font(13, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
            p.setPen(color)
            p.drawText(QRectF(cx - iw / 2, box.bottom() + 6, iw, 20), Qt.AlignmentFlag.AlignCenter, label)
        p.end()

    def _paint_shape(self, p: QPainter, c: QPointF, ratio, color: QColor):
        pen = QPen(color, 1.5)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        s = self.SHAPE
        if ratio is None or ratio == "original":
            # Photo glyph; "free" adds crop corners around it.
            inner = s * (0.62 if ratio is None else 0.9)
            r = QRectF(c.x() - inner / 2, c.y() - inner / 2, inner, inner)
            p.drawRoundedRect(r, 2.5, 2.5)
            path = QPainterPath(QPointF(r.left() + 1, r.bottom() - 1))
            path.lineTo(QPointF(r.left() + inner * 0.38, r.top() + inner * 0.52))
            path.lineTo(QPointF(r.left() + inner * 0.62, r.bottom() - inner * 0.22))
            path.lineTo(QPointF(r.left() + inner * 0.74, r.top() + inner * 0.62))
            path.lineTo(QPointF(r.right() - 1, r.bottom() - 1))
            p.drawPath(path)
            p.drawEllipse(QPointF(r.right() - inner * 0.27, r.top() + inner * 0.27), inner * 0.08, inner * 0.08)
            if ratio is None:
                o, L = s / 2, s * 0.28
                for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    x, y = c.x() + dx * o, c.y() + dy * o
                    corner = QPainterPath(QPointF(x - dx * L, y))
                    corner.lineTo(QPointF(x, y))
                    corner.lineTo(QPointF(x, y - dy * L))
                    p.drawPath(corner)
            return
        w, h = (s, s / ratio) if ratio >= 1 else (s * ratio, s)
        p.drawRoundedRect(QRectF(c.x() - w / 2, c.y() - h / 2, w, h), 2.5, 2.5)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().x())
        if i != self._hover:
            self._hover = i
            self.setToolTip(self._items[i][0] if i >= 0 else "")
            self.update()

    def leaveEvent(self, _e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        i = self._index_at(e.position().x())
        if e.button() == Qt.MouseButton.LeftButton and i >= 0:
            self.set_current(i)
            self.picked.emit(i)


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
        top.setSpacing(10)
        self.label = QLabel(label)
        self.value_label = QLabel("0")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(IconLabel(icons.icon(icon_name, 16)))
        top.addWidget(self.label, 1)
        top.addWidget(self.value_label)
        self.slider = _ResetSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(-100, 100)
        self.slider.setPageStep(10)
        self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 10)
        lay.setSpacing(6)
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

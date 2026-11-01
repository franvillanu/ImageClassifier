"""Editor widgets, styled after Image Classifier's own viewer.

The viewer is a black canvas with thin white halo icons floating over the
photo and translucent black cards where text is needed; the editor follows
the same rules instead of borrowing another app's chrome.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QFrame, QToolButton, QVBoxLayout, QWidget

from image_classifier.editor import icons
from image_classifier.editor.state import ANGLE_LIMIT

TEXT = "#ffffff"
TEXT_DIM = "#b8b8b8"
TEXT_OFF = "#6a6a6a"
ACCENT = "#0078D7"  # the app's accent (settings, popups, update button)
ACCENT_HOVER = "#1a8cea"
DANGER = "#DC3545"  # the app's close/destructive red
DANGER_HOVER = "#B22222"
CARD = QColor(12, 12, 14, 214)
CARD_LINE = QColor(255, 255, 255, 26)
FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'

STYLE = f"""
QWidget#PhotoEditor {{ font-family: {FONT}; }}
QLabel {{ color: {TEXT}; font-size: 14px; background: transparent; font-family: {FONT}; }}
QLabel#Dim {{ color: {TEXT_DIM}; font-size: 13px; }}
QLabel#Value {{ color: {TEXT_DIM}; font-size: 13px; }}
QLabel#GroupTitle {{ color: {TEXT_DIM}; font-size: 12px; font-weight: 600; letter-spacing: 1px; }}
QLabel#DialogTitle {{ font-size: 19px; font-weight: 600; }}
QLabel#DialogBody {{ font-size: 14px; color: {TEXT_DIM}; }}
QToolButton {{
    color: {TEXT}; background: rgba(255,255,255,0.08); border: none; border-radius: 6px;
    padding: 0px 16px; min-height: 34px; font-size: 14px; font-family: {FONT};
}}
QToolButton:hover {{ background: rgba(255,255,255,0.16); }}
QToolButton:disabled {{ color: {TEXT_OFF}; background: rgba(255,255,255,0.04); }}
QToolButton::menu-indicator {{ image: none; width: 0px; }}
QToolButton#Primary {{ background: {ACCENT}; }}
QToolButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QToolButton#Primary:disabled {{ background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.35); }}
QToolButton#Danger {{ background: {DANGER}; }}
QToolButton#Danger:hover {{ background: {DANGER_HOVER}; }}
QToolButton#Text {{ background: transparent; }}
QToolButton#Text:hover {{ background: rgba(255,255,255,0.10); }}
QMenu {{
    background: rgba(0,0,0,0.92); color: {TEXT}; border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px; padding: 6px; font-size: 15px; font-family: {FONT};
}}
QMenu::item {{ padding: 9px 28px 9px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: rgba(255,255,255,0.18); }}
QMenu::separator {{ height: 1px; background: rgba(255,255,255,0.12); margin: 5px 8px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.25); border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


def _round_pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def ui_font(px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """The UI font for text we paint ourselves (stylesheets don't reach QPainter)."""
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPixelSize(px)
    font.setWeight(weight)
    return font


def halo_text(p: QPainter, rect: QRectF, flags, text: str, color: QColor = QColor(TEXT)):
    """Text with a soft black outline so it reads over any photo, like the viewer's labels."""
    p.setPen(QColor(0, 0, 0, 170))
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        p.drawText(rect.translated(dx, dy), flags, text)
    p.setPen(color)
    p.drawText(rect, flags, text)


def tool_button(icon_name: str | None = None, text: str = "", tooltip: str = "", parent=None,
                object_name: str | None = None, icon_size: int = 16) -> QToolButton:
    """Text button (dialogs, save). Icons in the editor are ``HaloButton``s."""
    btn = QToolButton(parent)
    if icon_name:
        btn.setIcon(icons.icon(icon_name, icon_size, halo=False))
        btn.setIconSize(QSize(icon_size, icon_size))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    if text:
        btn.setText(text)
    if tooltip:
        btn.setToolTip(tooltip)
    if object_name:
        btn.setObjectName(object_name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


class HaloButton(QAbstractButton):
    """A bare halo icon, like the viewer's floating menu: no background, brightens on hover.

    Checkable buttons show a small accent bar beside (``indicator="left"``) or
    under (``"bottom"``) the icon when checked.
    """

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 30, box: int = 46,
                 indicator: str = "left", parent=None):
        super().__init__(parent)
        self._name = icon_name
        self._size = size
        self._indicator = indicator
        self._hover = False
        self.setFixedSize(box, box)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_icon(self, name: str):
        self._name = name
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def sizeHint(self):
        return self.size()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            p.setOpacity(0.28)
        elif self.isDown():
            p.setOpacity(0.7)
        elif not (self._hover or self.isChecked()):
            p.setOpacity(0.8)
        s = self._size
        r = QRectF((self.width() - s) / 2.0, (self.height() - s) / 2.0, s, s).toRect()
        icons.icon(self._name, s).paint(p, r)
        if self.isCheckable() and self.isChecked():
            p.setOpacity(1.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            if self._indicator == "left":
                p.drawRoundedRect(QRectF(0, self.height() / 2 - 9, 3, 18), 1.5, 1.5)
            else:
                p.drawRoundedRect(QRectF(self.width() / 2 - 9, self.height() - 3, 18, 3), 1.5, 1.5)
        p.end()


class HaloTextButton(HaloButton):
    """Halo icon followed by a label, both centred on the same line (e.g. the ratio picker)."""

    PAD, GAP = 10, 8

    def __init__(self, icon_name: str, text: str, tooltip: str = "", size: int = 24, height: int = 40,
                 reserve: list[str] | None = None, parent=None):
        """``reserve``: labels to size for, so the row doesn't shift when the label changes."""
        super().__init__(icon_name, tooltip, size=size, box=height, indicator="bottom", parent=parent)
        self._font = ui_font(14)
        from PyQt6.QtGui import QFontMetricsF
        metrics = QFontMetricsF(self._font)
        tw = max(metrics.horizontalAdvance(t) for t in (reserve or []) + [text])
        self.setFixedWidth(int(self.PAD + self._size + self.GAP + tw + self.PAD + 2))
        self.setText(text)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            p.setOpacity(0.28)
        elif self.isDown():
            p.setOpacity(0.7)
        elif not (self._hover or self.isChecked()):
            p.setOpacity(0.8)
        s = self._size
        y = (self.height() - s) / 2.0
        icons.icon(self._name, s).paint(p, QRectF(self.PAD, y, s, s).toRect())
        p.setFont(self._font)
        text_rect = QRectF(self.PAD + s + self.GAP, 0, self.width() - self.PAD - s - self.GAP, self.height())
        halo_text(p, text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.isCheckable() and self.isChecked():
            p.setOpacity(1.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(QRectF(self.width() / 2 - 9, self.height() - 3, 18, 3), 1.5, 1.5)
        p.end()


class Card(QFrame):
    """Translucent black rounded card, the app's overlay container look."""

    def __init__(self, parent=None, radius: float = 12.0, fill: QColor | None = None):
        super().__init__(parent)
        self._radius = radius
        self._fill = fill or CARD
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(CARD_LINE, 1))
        p.setBrush(self._fill)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self._radius, self._radius)
        p.end()


class _MenuRow(QAbstractButton):
    """One popover option: icon, label and an optional dim hint line."""

    def __init__(self, icon_name: str, title: str, hint: str = "", shortcut: str = "", parent=None):
        super().__init__(parent)
        self._icon = icon_name
        self._title = title
        self._hint = hint
        self._shortcut = shortcut
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(56 if hint else 42)
        from PyQt6.QtGui import QFontMetricsF
        w = max(QFontMetricsF(ui_font(15)).horizontalAdvance(title), QFontMetricsF(ui_font(12)).horizontalAdvance(hint))
        sw = QFontMetricsF(ui_font(12)).horizontalAdvance(shortcut) + 24 if shortcut else 0
        self.setMinimumWidth(int(14 + 22 + 14 + w + 22 + sw))

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover or self.isDown():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 34 if self.isDown() else 24))
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        icons.icon(self._icon, 22, halo=False).paint(p, QRectF(14, (self.height() - 22) / 2, 22, 22).toRect())
        if self._shortcut:
            p.setFont(ui_font(12))
            p.setPen(QColor(TEXT_OFF if not self._hover else TEXT_DIM))
            p.drawText(QRectF(0, 0, self.width() - 14, self.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._shortcut)
        x = 14 + 22 + 14
        if self._hint:
            p.setFont(ui_font(15))
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(x, 8, self.width() - x, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self._title)
            p.setFont(ui_font(12))
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(x, 29, self.width() - x, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self._hint)
        else:
            p.setFont(ui_font(15))
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(x, 0, self.width() - x, self.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title)
        p.end()


class Popover(QWidget):
    """Menu card anchored under a button: fades and slides in, closes on outside click or Esc.

    Covers its parent with an invisible backdrop so any click elsewhere dismisses it.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.card = Card(self, radius=12, fill=QColor(16, 16, 18))
        self._lay = QVBoxLayout(self.card)
        self._lay.setContentsMargins(6, 6, 6, 6)
        self._lay.setSpacing(2)
        from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        self._fx = QGraphicsOpacityEffect(self.card)
        self.card.setGraphicsEffect(self._fx)
        self._fade = QPropertyAnimation(self._fx, b"opacity", self)
        self._slide = QPropertyAnimation(self.card, b"pos", self)
        for a in (self._fade, self._slide):
            a.setDuration(150)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
        # The effect is only needed while fading; left on, it composites the card translucently.
        self._fade.finished.connect(lambda: self._fx.setEnabled(False))
        self.hide()

    def add_item(self, icon_name: str, title: str, hint: str, callback, shortcut: str = ""):
        row = _MenuRow(icon_name, title, hint, shortcut)
        row.clicked.connect(lambda: (self.close_menu(), callback()))
        self._lay.addWidget(row)
        return row

    def add_separator(self):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,0.10); margin: 0px 10px;")
        self._lay.addSpacing(3)
        self._lay.addWidget(line)
        self._lay.addSpacing(3)

    def open_under(self, anchor: QWidget):
        parent = self.parentWidget()
        self.setGeometry(parent.rect())
        self.card.adjustSize()
        a = anchor.mapTo(parent, anchor.rect().bottomRight())
        x = max(8, a.x() - self.card.width() + 1)
        y = a.y() + 8
        from PyQt6.QtCore import QPoint
        self._slide.setStartValue(QPoint(x, y - 8))
        self._slide.setEndValue(QPoint(x, y))
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self.card.move(x, y - 8)
        self._fx.setEnabled(True)
        self._fx.setOpacity(0.0)
        self.show()
        self.raise_()
        self.setFocus()
        self._fade.start()
        self._slide.start()

    def close_menu(self):
        self.hide()

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.position().toPoint()):
            self.close_menu()
        e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close_menu()
        e.accept()


class StraightenRuler(QWidget):
    """Slim tick ruler for the straighten angle; floats over the canvas with no background.

    Drag to scrub (the ticks follow the pointer), wheel/arrow keys step 0.1 deg
    (Shift: 1 deg), double-click resets to 0. Values snap to 0 when close.
    """

    valueChanged = pyqtSignal(float)
    pressed = pyqtSignal()
    released = pyqtSignal()

    PX_PER_DEGREE = 8.0
    SNAP = 0.3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._drag_x = None
        self._drag_value = 0.0
        self._decimal = ","
        self.setFixedHeight(46)
        self.setMinimumWidth(240)
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
        return QSize(420, 46)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        cx = w / 2.0
        base = h - 6.0
        ppd = self.PX_PER_DEGREE
        first = int(max(-ANGLE_LIMIT, self._value - cx / ppd)) - 1
        last = int(min(ANGLE_LIMIT, self._value + cx / ppd)) + 1
        for deg in range(first, last + 1):
            if abs(deg) > ANGLE_LIMIT:
                continue
            x = cx + (deg - self._value) * ppd
            fade = max(0.0, 1.0 - (abs(x - cx) / (cx + 1)) ** 2)
            if fade <= 0:
                continue
            length = 12.0 if deg == 0 else 8.0 if deg % 5 == 0 else 4.0
            alpha = (230 if deg == 0 else 150 if deg % 5 == 0 else 80) * fade
            xr = round(x) + 0.5
            p.setPen(QPen(QColor(0, 0, 0, int(alpha * 0.6)), 3))
            p.drawLine(QPointF(xr, base - length), QPointF(xr, base))
            p.setPen(QPen(QColor(255, 255, 255, int(alpha)), 1))
            p.drawLine(QPointF(xr, base - length), QPointF(xr, base))
        # needle
        p.setPen(_round_pen(QColor(0, 0, 0, 150), 4))
        p.drawLine(QPointF(cx, base - 18), QPointF(cx, base + 2))
        p.setPen(_round_pen(QColor(ACCENT if self._value else TEXT), 2))
        p.drawLine(QPointF(cx, base - 18), QPointF(cx, base + 2))
        p.setFont(ui_font(13, QFont.Weight.DemiBold))
        halo_text(p, QRectF(0, 0, w, base - 20), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
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
    """Row of aspect-ratio choices, each drawn at its true proportions.

    Items are ``(label, ratio)`` where ratio is ``None`` (free), ``"original"`` or a float.
    """

    picked = pyqtSignal(int)

    ICON_BOX = 40.0
    SHAPE = 20.0
    ITEM = 64.0

    def __init__(self, items: list[tuple[str, object]], parent=None):
        super().__init__(parent)
        self._items = items
        self._current = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setFixedSize(int(self.ITEM * len(items)), 70)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_current(self, index: int):
        if index != self._current:
            self._current = index
            self.update()

    def _index_at(self, x: float) -> int:
        i = int(x // self.ITEM)
        return i if 0 <= i < len(self._items) else -1

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for i, (label, ratio) in enumerate(self._items):
            cx = self.ITEM * (i + 0.5)
            box = QRectF(cx - self.ICON_BOX / 2, 2, self.ICON_BOX, self.ICON_BOX)
            selected = i == self._current
            if i == self._hover and not selected:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 22))
                p.drawRoundedRect(box, 8, 8)
            color = QColor(ACCENT_HOVER if selected else TEXT if i == self._hover else TEXT_DIM)
            self._paint_shape(p, box.center(), ratio, color, selected)
            p.setFont(ui_font(12, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
            p.setPen(color)
            p.drawText(QRectF(cx - self.ITEM / 2, box.bottom() + 4, self.ITEM, 20),
                       Qt.AlignmentFlag.AlignCenter, label)
        p.end()

    def _paint_shape(self, p: QPainter, c: QPointF, ratio, color: QColor, filled: bool):
        pen = QPen(color, 1.6)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        fill = QColor(color)
        fill.setAlpha(60)
        p.setBrush(fill if filled else Qt.BrushStyle.NoBrush)
        s = self.SHAPE
        if ratio is None:
            # Free: four open corners
            o, L = s / 2, s * 0.32
            p.setBrush(Qt.BrushStyle.NoBrush)
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                x, y = c.x() + dx * o, c.y() + dy * o
                corner = QPainterPath(QPointF(x - dx * L, y))
                corner.lineTo(QPointF(x, y))
                corner.lineTo(QPointF(x, y - dy * L))
                p.drawPath(corner)
            return
        if ratio == "original":
            r = QRectF(c.x() - s / 2, c.y() - s * 0.38, s, s * 0.76)
            p.drawRoundedRect(r, 2.5, 2.5)
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(QPointF(r.left() + 3, r.bottom() - 3))
            path.lineTo(QPointF(r.left() + s * 0.38, r.top() + s * 0.36))
            path.lineTo(QPointF(r.left() + s * 0.6, r.bottom() - s * 0.2))
            path.lineTo(QPointF(r.left() + s * 0.72, r.top() + s * 0.46))
            path.lineTo(QPointF(r.right() - 3, r.bottom() - 3))
            p.drawPath(path)
            return
        w, h = (s, s / ratio) if ratio >= 1 else (s * ratio, s)
        p.drawRoundedRect(QRectF(c.x() - w / 2, c.y() - h / 2, w, h), 2.5, 2.5)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().x())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, _e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        i = self._index_at(e.position().x())
        if e.button() == Qt.MouseButton.LeftButton and i >= 0:
            self.set_current(i)
            self.picked.emit(i)


class AdjustDockButton(QAbstractButton):
    """One adjustment in the bottom dock: halo icon inside a ring that shows its value.

    The ring fills clockwise for positive values and anticlockwise for negative
    ones, so every adjustment's state is readable at a glance. The selected one
    gets the accent bar underneath. Double-click resets it.
    """

    doubleClicked = pyqtSignal()
    BOX = 54
    RING = 21.0  # radius

    def __init__(self, name: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.name = name
        self._value = 0
        self._hover = False
        self.setCheckable(True)
        self.setFixedSize(self.BOX, self.BOX + 6)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_value(self, v: int):
        if v != self._value:
            self._value = v
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        e.accept()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QPointF(self.width() / 2.0, self.BOX / 2.0)
        r = self.RING
        ring = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        active = self.isChecked() or self._hover
        p.setPen(QPen(QColor(255, 255, 255, 46 if active else 28), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ring)
        if self._value:
            pen = _round_pen(QColor(ACCENT_HOVER), 2.6)
            p.setPen(pen)
            p.drawArc(ring, 90 * 16, int(-self._value / 100 * 360 * 16))  # negative span = clockwise
        if not (active or self._value):
            p.setOpacity(0.78)
        s = 24
        icons.icon(self.name, s).paint(p, QRectF(c.x() - s / 2, c.y() - s / 2, s, s).toRect())
        if self.isChecked():
            p.setOpacity(1.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(QRectF(c.x() - 9, self.height() - 3, 18, 3), 1.5, 1.5)
        p.end()


class ValueDial(QWidget):
    """Tick dial for one adjustment (-100..100), styled like the straighten ruler.

    Drag to scrub (ticks follow the pointer), wheel steps 1 (Shift: 10),
    double-click resets to 0. Snaps to 0 when passing close to it.
    """

    valueChanged = pyqtSignal(int)
    pressed = pyqtSignal()
    released = pyqtSignal()

    PX_PER_UNIT = 2.6
    SNAP = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._label = ""
        self._drag_x = None
        self._drag_value = 0
        self.setFixedHeight(56)
        self.setMinimumWidth(320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def set_label(self, label: str):
        self._label = label
        self.update()

    def value(self) -> int:
        return self._value

    def setValue(self, v: int, emit: bool = False):
        v = int(max(-100, min(100, round(v))))
        if v == self._value:
            return
        self._value = v
        self.update()
        if emit:
            self.valueChanged.emit(v)

    def sizeHint(self):
        return QSize(560, 56)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        cx = w / 2.0
        base = h - 6.0
        ppu = self.PX_PER_UNIT
        for unit in range(-100, 101, 5):
            x = cx + (unit - self._value) * ppu
            fade = max(0.0, 1.0 - (abs(x - cx) / (cx + 1)) ** 2)
            if fade <= 0:
                continue
            major = unit % 25 == 0
            length = 12.0 if unit == 0 else 8.0 if major else 4.0
            alpha = (230 if unit == 0 else 150 if major else 80) * fade
            xr = round(x) + 0.5
            p.setPen(QPen(QColor(0, 0, 0, int(alpha * 0.6)), 3))
            p.drawLine(QPointF(xr, base - length), QPointF(xr, base))
            p.setPen(QPen(QColor(255, 255, 255, int(alpha)), 1))
            p.drawLine(QPointF(xr, base - length), QPointF(xr, base))
        # filled stretch between zero and the value
        if self._value:
            p.setPen(_round_pen(QColor(ACCENT_HOVER), 2))
            p.drawLine(QPointF(cx - self._value * ppu, base + 1), QPointF(cx, base + 1))
        p.setPen(_round_pen(QColor(0, 0, 0, 150), 4))
        p.drawLine(QPointF(cx, base - 20), QPointF(cx, base + 2))
        p.setPen(_round_pen(QColor(ACCENT if self._value else TEXT), 2))
        p.drawLine(QPointF(cx, base - 20), QPointF(cx, base + 2))
        v = self._value
        number = (f"+{v}" if v > 0 else str(v).replace("-", "−"))
        p.setFont(ui_font(14))
        fm = p.fontMetrics()
        label_w = fm.horizontalAdvance(self._label + "  ")
        p.setFont(ui_font(14, QFont.Weight.DemiBold))
        num_w = p.fontMetrics().horizontalAdvance(number)
        x0 = cx - (label_w + num_w) / 2
        top = QRectF(0, 0, w, base - 22)
        p.setFont(ui_font(14))
        halo_text(p, QRectF(x0, top.y(), label_w, top.height()),
                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, self._label, QColor(TEXT_DIM))
        p.setFont(ui_font(14, QFont.Weight.DemiBold))
        halo_text(p, QRectF(x0 + label_w, top.y(), num_w + 4, top.height()),
                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, number)
        p.end()

    def _snap(self, v: float) -> float:
        return 0 if abs(v) < self.SNAP else v

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_x = e.position().x()
            self._drag_value = self._value
            self.pressed.emit()

    def mouseMoveEvent(self, e):
        if self._drag_x is None:
            return
        v = self._drag_value - (e.position().x() - self._drag_x) / self.PX_PER_UNIT
        self.setValue(self._snap(v), emit=True)

    def mouseReleaseEvent(self, e):
        if self._drag_x is not None and e.button() == Qt.MouseButton.LeftButton:
            self._drag_x = None
            self.released.emit()

    def mouseDoubleClickEvent(self, e):
        self.pressed.emit()
        self.setValue(0, emit=True)
        self.released.emit()

    def _step(self, delta: int):
        self.pressed.emit()
        self.setValue(self._value + delta, emit=True)
        self.released.emit()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0 or e.angleDelta().x() / 120.0
        if steps:
            big = e.modifiers() & Qt.KeyboardModifier.ShiftModifier
            self._step(int(round(steps * (10 if big else 1))))
        e.accept()

    def keyPressEvent(self, e):
        step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self._step(-step)
        elif e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self._step(step)
        elif e.key() == Qt.Key.Key_0:
            self._step(-self._value)
        else:
            super().keyPressEvent(e)

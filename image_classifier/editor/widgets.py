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
        self._full_width = int(self.PAD + self._size + self.GAP + tw + self.PAD + 2)
        self._compact = False
        self.setFixedWidth(self._full_width)
        self.setText(text)

    def set_compact(self, compact: bool):
        """Icon only (the label moves to the tooltip), for narrow windows."""
        if compact != self._compact:
            self._compact = compact
            self.setFixedWidth(self.PAD + self._size + self.PAD if compact else self._full_width)
            self.update()

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
        if not self._compact:
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
        drop = -8  # slides down into place
        if y + self.card.height() > parent.height() - 8:  # no room below (bottom toolbar): open above
            y = anchor.mapTo(parent, anchor.rect().topLeft()).y() - 8 - self.card.height()
            drop = 8
        from PyQt6.QtCore import QPoint
        self._slide.setStartValue(QPoint(x, y + drop))
        self._slide.setEndValue(QPoint(x, y))
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self.card.move(x, y + drop)
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


class TickDial(QWidget):
    """Fixed tick scale with a moving needle: minus on the left, plus on the right, 0 in the middle.

    Drag anywhere to move the value (right = up; hold Shift for fine control),
    wheel/arrow keys step it, double-click resets to 0. Snaps to 0 when close.
    Subclasses set the range, tick spacing and formatting.
    """

    valueChanged = pyqtSignal(float)
    pressed = pyqtSignal()
    released = pyqtSignal()

    LIMIT = 100
    MINOR, MAJOR, LABEL_EVERY = 5, 25, 50
    DECIMALS = 0
    SNAP = 2.0
    STEP, BIG_STEP = 1, 10
    MARGIN = 14.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._label = ""
        self._drag_x = None
        self._drag_value = 0.0
        self.setFixedHeight(60)
        self.setMinimumWidth(240)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    # ------------------------------------------------------------------ value
    def set_label(self, label: str):
        self._label = label
        self.update()

    def value(self):
        return round(self._value, self.DECIMALS) if self.DECIMALS else int(round(self._value))

    def setValue(self, v: float, emit: bool = False):
        v = round(max(-self.LIMIT, min(self.LIMIT, float(v))), self.DECIMALS)
        if v == self._value:
            return
        self._value = v
        self.update()
        if emit:
            self.valueChanged.emit(v)

    def number(self) -> str:
        v = self.value()
        if self.DECIMALS:
            text = f"{0.0 if abs(v) < 0.05 else v:.{self.DECIMALS}f}"
        else:
            text = f"+{v}" if v > 0 else str(v)
        return text.replace("-", "−")

    def text(self) -> str:
        return self.number()

    def px_per_unit(self) -> float:
        return max(1e-6, (self.width() - 2 * self.MARGIN) / (2 * self.LIMIT))

    def _x(self, v: float) -> float:
        return self.MARGIN + (v + self.LIMIT) * self.px_per_unit()

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        base = 38.0
        # track
        p.setPen(_round_pen(QColor(255, 255, 255, 40), 2))
        p.drawLine(QPointF(self._x(-self.LIMIT), base), QPointF(self._x(self.LIMIT), base))
        # ticks above the track, labels below it
        p.setFont(ui_font(11))
        for unit in range(-self.LIMIT, self.LIMIT + 1, self.MINOR):
            x = round(self._x(unit)) + 0.5
            major = unit % self.MAJOR == 0
            length = 10.0 if unit == 0 else 7.0 if major else 4.0
            p.setPen(QPen(QColor(255, 255, 255, 190 if unit == 0 else 120 if major else 60), 1))
            p.drawLine(QPointF(x, base - 3 - length), QPointF(x, base - 3))
            if unit % self.LABEL_EVERY == 0:
                p.setPen(QColor(255, 255, 255, 110))
                p.drawText(QRectF(x - 24, base + 5, 48, 14), Qt.AlignmentFlag.AlignCenter,
                           str(unit).replace("-", "−"))
        # fill from zero to the value, then the knob
        xz, xv = self._x(0), self._x(self._value)
        if self._value:
            p.setPen(_round_pen(QColor(ACCENT_HOVER), 3))
            p.drawLine(QPointF(xz, base), QPointF(xv, base))
        p.setPen(QPen(QColor(0, 0, 0, 140), 1))
        p.setBrush(QColor(TEXT))
        p.drawEllipse(QPointF(xv, base), 6.5, 6.5)
        # readout: label (dim) + number (bold), centred above the scale
        number = self.number() + self._suffix()
        p.setFont(ui_font(14))
        label = (self._label + "  ") if self._label else ""
        label_w = p.fontMetrics().horizontalAdvance(label)
        p.setFont(ui_font(14, QFont.Weight.DemiBold))
        num_w = p.fontMetrics().horizontalAdvance(number)
        x0 = (w - label_w - num_w) / 2
        if label:
            p.setFont(ui_font(14))
            halo_text(p, QRectF(x0, 0, label_w, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                      label, QColor(TEXT_DIM))
        p.setFont(ui_font(14, QFont.Weight.DemiBold))
        halo_text(p, QRectF(x0 + label_w, 0, num_w + 4, 20),
                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, number)
        p.end()

    def _suffix(self) -> str:
        return ""

    # ------------------------------------------------------------------ input
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
        fine = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        delta = (e.position().x() - self._drag_x) / self.px_per_unit()
        v = self._drag_value + (delta / 10.0 if fine else delta)
        self.setValue(v if fine else self._snap(v), emit=True)

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
            self._step(steps * (self.BIG_STEP if big else self.STEP))
        e.accept()

    def keyPressEvent(self, e):
        step = self.BIG_STEP if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else self.STEP
        if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self._step(-step)
        elif e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self._step(step)
        elif e.key() == Qt.Key.Key_0:
            self._step(-self._value)
        else:
            super().keyPressEvent(e)


class StraightenRuler(TickDial):
    """Straighten angle, -45..45 degrees in 0.1 steps (positive turns the photo clockwise)."""

    LIMIT = int(ANGLE_LIMIT)
    MINOR, MAJOR, LABEL_EVERY = 1, 5, 15
    DECIMALS = 1
    SNAP = 0.3
    STEP, BIG_STEP = 0.1, 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._decimal = ","

    def set_decimal_separator(self, sep: str):
        self._decimal = sep
        self.update()

    def number(self) -> str:
        return super().number().replace(".", self._decimal)

    def _suffix(self) -> str:
        return "°"

    def text(self) -> str:
        return self.number() + "°"


class ValueDial(TickDial):
    """One adjustment, -100..100."""


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

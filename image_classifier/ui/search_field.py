"""Shortcut-search helpers: forgiving text matching and a search box with a magnifier and a clear button."""

import re
import unicodedata

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton

from image_classifier.ui.scaling import px


def fold(text: str) -> str:
    """Lower case without accents, so 'navegacion' finds 'Navegación'."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def matches(query: str, key: str, description: str) -> bool:
    """True when a shortcut row should show for `query`.

    A single character must equal the key. Longer text matches anywhere in the key or description,
    and also matches a longer form of a word in the description, so 'guardar' finds 'Guarda'
    (Spanish notes are written as commands, people search for the infinitive).
    """
    query = fold(query).strip()
    if not query:
        return True
    key, description = fold(key), fold(description)
    if len(query) == 1:
        return key == query
    combined = f"{key} {description}"
    words = [w for w in re.findall(r"\w+", combined) if len(w) >= 4]
    return all(token in combined or any(token.startswith(w) for w in words) for token in query.split())


def _icon_pixmap(side: int, draw) -> QPixmap:
    """A transparent `side`x`side` (logical pixels) pixmap, drawn sharply on high-DPI screens."""
    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen else 1.0
    pixmap = QPixmap(round(side * ratio), round(side * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw(painter, side)
    painter.end()
    return pixmap


def _draw_magnifier(painter: QPainter, side: int):
    pen = QPen(QColor("#9aa1ab"))
    pen.setWidthF(side * 0.1)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    lens = side * 0.58
    painter.drawEllipse(round(side * 0.1), round(side * 0.1), round(lens), round(lens))
    painter.drawLine(round(side * 0.68), round(side * 0.68), round(side * 0.9), round(side * 0.9))


def _draw_cross(painter: QPainter, side: int):
    pen = QPen(QColor("#ffffff"))
    pen.setWidthF(side * 0.14)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    low, high = side * 0.28, side * 0.72
    painter.drawLine(round(low), round(low), round(high), round(high))
    painter.drawLine(round(high), round(low), round(low), round(high))


class SearchBox(QFrame):
    """Rounded field: magnifier, text, and a round clear button that shows only while there is text.

    Style it through the object names SearchBox, searchInput and clearBtn.
    """

    def __init__(self, placeholder: str, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchBox")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(px(16, scale), 0, px(10, scale), 0)
        row.setSpacing(px(10, scale))

        side = px(20, scale)
        magnifier = QLabel(self)
        magnifier.setPixmap(_icon_pixmap(side, _draw_magnifier))
        magnifier.setFixedSize(side, side)
        row.addWidget(magnifier, 0, Qt.AlignmentFlag.AlignVCenter)

        self.line = QLineEdit(self)
        self.line.setObjectName("searchInput")
        self.line.setPlaceholderText(placeholder)
        row.addWidget(self.line, 1)

        button_side = px(28, scale)
        cross = px(16, scale)
        self.clear_button = QPushButton(self)
        self.clear_button.setObjectName("clearBtn")
        self.clear_button.setIcon(QIcon(_icon_pixmap(cross, _draw_cross)))
        self.clear_button.setIconSize(QSize(cross, cross))
        self.clear_button.setFixedSize(button_side, button_side)
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_button.setVisible(False)
        self.clear_button.clicked.connect(self._clear)
        row.addWidget(self.clear_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.line.textChanged.connect(lambda text: self.clear_button.setVisible(bool(text)))
        self.setFocusProxy(self.line)

    def _clear(self):
        self.line.clear()
        self.line.setFocus()

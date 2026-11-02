"""Shortcut-search helpers: forgiving text matching and a clear (x) button for a line edit."""

import re
import unicodedata

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QLineEdit


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


def _clear_icon() -> QIcon:
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#4a4f58"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    pen = QPen(QColor("#e8eaed"))
    pen.setWidth(3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(11, 11, 21, 21)
    painter.drawLine(21, 11, 11, 21)
    painter.end()
    return QIcon(pixmap)


def add_clear_button(line_edit: QLineEdit, tooltip: str = "") -> QAction:
    """A round x at the right end of the field, shown only while there is text."""
    action = QAction(_clear_icon(), tooltip, line_edit)

    def clear():
        line_edit.clear()
        line_edit.setFocus()

    action.triggered.connect(clear)
    line_edit.textChanged.connect(lambda text: action.setVisible(bool(text)))
    line_edit.addAction(action, QLineEdit.ActionPosition.TrailingPosition)
    action.setVisible(bool(line_edit.text()))  # adding an action shows it, so hide it again when empty
    return action


def _search_icon() -> QIcon:
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#9aa1ab"))
    pen.setWidth(3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(5, 5, 15, 15)
    painter.drawLine(18, 18, 26, 26)
    painter.end()
    return QIcon(pixmap)


def add_search_icon(line_edit: QLineEdit) -> QAction:
    """A magnifier at the left end of the field."""
    action = QAction(_search_icon(), "", line_edit)
    line_edit.addAction(action, QLineEdit.ActionPosition.LeadingPosition)
    return action

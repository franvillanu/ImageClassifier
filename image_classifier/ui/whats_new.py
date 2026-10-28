"""Release-notes overlay: one entry (after an update) or the whole history (from About)."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


class WhatsNewOverlay(QWidget):
    """Dimmed full-window overlay with a centered card. `entries` is [(heading, text)]."""

    def __init__(self, parent, title, entries, close_text, empty_text, on_closed):
        super().__init__(parent)
        self._on_closed = on_closed
        self.setObjectName("WhatsNewOverlay")
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("#WhatsNewOverlay { background-color: rgba(0, 0, 0, 150); }")

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close_overlay).setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )

        self.card = QWidget(self)
        self.card.setObjectName("WhatsNewCard")
        self.card.setStyleSheet("""
            QWidget#WhatsNewCard {
                background-color: #14161c; border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 40);
            }
            QLabel { background: transparent; color: white; font-size: 15px; }
            QLabel#title { font-size: 21px; font-weight: bold; }
            QLabel#heading { color: #4aa3ff; font-size: 14px; font-weight: bold; }
            QLabel#empty { color: #8a8f98; }
            QFrame#divider { background-color: rgba(255, 255, 255, 30); border: none; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QPushButton {
                background-color: #DC3545; color: white; border: none;
                border-radius: 8px; padding: 8px 28px; font-size: 15px;
            }
            QPushButton:hover { background-color: #B22222; }
        """)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(18)

        title_label = QLabel(title, self.card)
        title_label.setObjectName("title")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        divider = QFrame(self.card)
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 8, 0)
        body_layout.setSpacing(4)
        if not entries:
            empty = QLabel(empty_text, body)
            empty.setObjectName("empty")
            body_layout.addWidget(empty)
        for index, (heading, text) in enumerate(entries):
            if heading:
                head = QLabel(heading, body)
                head.setObjectName("heading")
                body_layout.addWidget(head)
            item = QLabel(text, body)
            item.setWordWrap(True)
            item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body_layout.addWidget(item)
            if index < len(entries) - 1:
                body_layout.addSpacing(12)
        body_layout.addStretch(1)

        scroll = QScrollArea(self.card)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll, 1)

        close_btn = QPushButton(close_text, self.card)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.close_overlay)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self._close_btn = close_btn
        self._scroll = scroll
        self._body = body

    def _place_card(self):
        width = min(560, max(320, self.width() - 80))
        self.card.setFixedWidth(width)
        self._body.setFixedWidth(width - 26 * 2 - 8)
        content = self._body.layout().totalHeightForWidth(self._body.width())
        chrome = 190  # title, divider, button, spacing and margins
        scroll_height = min(content, max(120, int(self.height() * 0.8) - chrome))
        self._scroll.setFixedHeight(scroll_height)
        self.card.adjustSize()
        self.card.move((self.width() - self.card.width()) // 2, (self.height() - self.card.height()) // 2)

    def open_overlay(self):
        self.setGeometry(self.parentWidget().rect())
        self._place_card()
        self.show()
        self.raise_()
        self._close_btn.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.pos()):
            self.close_overlay()
        else:
            event.ignore()

    def close_overlay(self):
        if self._on_closed is None:
            return
        callback, self._on_closed = self._on_closed, None
        self.hide()
        self.deleteLater()
        callback()

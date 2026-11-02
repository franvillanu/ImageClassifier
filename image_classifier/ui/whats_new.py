"""Release-notes overlay: one entry (after an update) or the whole history (from About)."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from image_classifier.updates.notes import sections

# kind -> (icon, colour); titles come from the caller (translated)
SECTION_STYLE = {"new": ("enhance", "#3ccf7a"), "changed": ("refresh", "#b9a2ff"), "fixed": ("bug", "#ffa159")}
DEFAULT_TITLES = {"new": "New features", "changed": "Changes", "fixed": "Fixes"}


class WhatsNewOverlay(QWidget):
    """Dimmed full-window overlay with a centered card. `entries` is [(heading, text[, date])]."""

    def __init__(self, parent, title, entries, close_text, empty_text, on_closed, section_titles=None,
                 latest_text=None):
        super().__init__(parent)
        titles = {**DEFAULT_TITLES, **(section_titles or {})}
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
            QLabel#heading { color: white; font-size: 22px; font-weight: bold; }
            QLabel#chip {
                background-color: #2a77c6; color: white; border-radius: 11px;
                padding: 0 10px; font-size: 12px; font-weight: bold;
            }
            QLabel#date { color: #9aa1ab; font-size: 13px; }
            QLabel#empty { color: #8a8f98; }
            QLabel#dot { color: #8a8f98; font-size: 15px; font-weight: bold; }
            QLabel#section { font-size: 15px; font-weight: bold; }
            QFrame#divider { background-color: rgba(255, 255, 255, 60); border: none; }
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
        for index, entry in enumerate(entries):
            heading, text, *rest = entry
            date = rest[0] if rest else None
            if index:  # clear break between versions
                body_layout.addSpacing(14)
                rule = QFrame(body)
                rule.setObjectName("divider")
                rule.setFixedHeight(1)
                body_layout.addWidget(rule)
                body_layout.addSpacing(16)
            if heading:
                body_layout.addLayout(self._version_header(body, heading, date, latest_text if index == 0 else None))
                body_layout.addSpacing(8)
            groups = sections(text) or [(None, [text])]
            for g, (kind, points) in enumerate(groups):
                if g:
                    body_layout.addSpacing(14)
                if kind:  # Sidera-style section: coloured icon + title, then its points
                    body_layout.addLayout(self._section_header(body, kind, titles[kind]))
                    body_layout.addSpacing(6)
                for number, point in enumerate(points):
                    if number:
                        body_layout.addSpacing(6)
                    body_layout.addLayout(self._point_row(body, point, bullet=bool(kind) or len(points) > 1))
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

    def _version_header(self, parent, heading, date, latest_text):
        """Version number, optional 'Latest' chip, and the release date on the right."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        head = QLabel(heading, parent)
        head.setObjectName("heading")
        row.addWidget(head, 0, Qt.AlignmentFlag.AlignVCenter)
        if latest_text:
            chip = QLabel(latest_text, parent)
            chip.setObjectName("chip")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setFixedHeight(22)
            row.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        if date:
            when = QLabel(date, parent)
            when.setObjectName("date")
            row.addWidget(when, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _section_header(self, parent, kind, title):
        from PyQt6.QtCore import QSize
        from image_classifier.editor import icons
        icon_name, colour = SECTION_STYLE[kind]
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        icon = QLabel(parent)
        icon.setPixmap(icons.icon(icon_name, 20, halo=False, color=colour).pixmap(QSize(20, 20), self.devicePixelRatioF()))
        icon.setFixedSize(20, 20)
        label = QLabel(title, parent)
        label.setObjectName("section")
        label.setStyleSheet(f"color: {colour};")
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label, 1, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _point_row(self, parent, point, bullet):
        row = QHBoxLayout()
        row.setContentsMargins(28 if bullet else 0, 0, 0, 0)
        row.setSpacing(10)
        if bullet:
            dot = QLabel("•", parent)
            dot.setObjectName("dot")
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        item = QLabel(point, parent)
        item.setWordWrap(True)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(item, 1)
        return row

    def _place_card(self):
        width = min(620, max(320, self.width() - 80))
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

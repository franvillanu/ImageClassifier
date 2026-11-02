"""Help pop-up content: shortcuts as a searchable list with key-shaped chips, grouped by category."""

import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from image_classifier.ui.scaling import px
from image_classifier.ui.search_field import add_clear_button, add_search_icon, matches

HELP_STYLE = """
    QWidget#HelpContainer { background-color: #17181a; border: 1px solid #3d4047; border-radius: 12px; }
    #HelpContainer QWidget { background: transparent; }
    #HelpContainer QLabel { color: #e8eaed; font-size: 16px; border: none; }
    #HelpContainer QLabel#helpTitle { color: white; font-size: 22px; font-weight: bold; }
    #HelpContainer QLabel#note { color: #E74C3C; font-size: 16px; font-weight: bold; }
    #HelpContainer QLabel#empty { color: #9aa1ab; font-size: 16px; }
    #HelpContainer QLabel#keycap {
        background-color: #262930; color: white; font-size: 15px; font-weight: bold;
        border: 1px solid #3d4047; border-bottom: 3px solid #3d4047; border-radius: 8px; padding: 0 10px;
    }
    #HelpContainer QLabel#catTitle { font-size: 17px; font-weight: bold; }
    #HelpContainer QWidget#catHead { border-bottom: 1px solid #3d4047; }
    #HelpContainer QWidget#shortRow { border-bottom: 1px solid #22252a; }
    #HelpContainer QPushButton#closeX {
        background: transparent; color: #c9ced6; border: none; border-radius: 8px; font-size: 18px;
        min-width: 40px; min-height: 40px;
    }
    #HelpContainer QPushButton#closeX:hover { background-color: #3a3e45; }
    #HelpContainer QLineEdit {
        background-color: #0f1012; color: white; font-size: 17px; padding: 0 8px;
        border: 1px solid #3d4047; border-radius: 10px;
    }
    #HelpContainer QLineEdit:focus { border-color: #6b717b; }
    #HelpContainer QScrollBar:vertical { background: transparent; border: none; width: 8px; margin: 0; }
    #HelpContainer QScrollBar::handle:vertical { background: #3a3e45; border-radius: 4px; min-height: 28px; }
    #HelpContainer QScrollBar::handle:vertical:hover { background: #4d525a; }
    #HelpContainer QScrollBar::add-line:vertical, #HelpContainer QScrollBar::sub-line:vertical { height: 0; }
    #HelpContainer QScrollBar::add-page:vertical, #HelpContainer QScrollBar::sub-page:vertical { background: transparent; }
"""

CATEGORY_COLORS = ["#f2c14e", "#ffa159", "#5fb0ff", "#b9a2ff", "#5fd08a", "#6fd6d6", "#ffd166", "#ff8fab", "#8be9fd"]
ARROWS = {"⬅": "←", "➡": "→", "⬆": "↑", "⬇": "↓"}


def strip_html(raw: str) -> str:
    return re.sub(r"<[^>]*>", "", raw).strip()


def parse_keys(raw: str):
    """(['Ctrl', 'Shift', 'C'], has_note) from a key string such as "Shift+⬆️<span>*</span>"."""
    plain = strip_html(raw).replace("️", "")
    has_note = "*" in plain
    plain = plain.replace("*", "")
    for emoji, glyph in ARROWS.items():
        plain = plain.replace(emoji, glyph)
    if len(plain) > 1 and all(ch in "←→↑↓" for ch in plain):
        keys = list(plain)  # e.g. two arrows side by side
    elif "+" in plain.strip("+"):
        keys = [part.strip() for part in plain.split("+") if part.strip()]
    else:
        keys = [plain.strip()]
    return keys, has_note


class HelpContent:
    """Builds the header, search field and category list into `container`'s layout."""

    def __init__(self, container, title, placeholder, empty_text, categories, scale, on_close):
        s = scale
        self.rows = []
        self._groups = []  # (header widget, [row dicts])

        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(container)
        head = QHBoxLayout(header)
        head.setContentsMargins(px(28, s), px(16, s), px(16, s), px(12, s))
        heading = QLabel(title, header)
        heading.setObjectName("helpTitle")
        close_x = QPushButton("✕", header)
        close_x.setObjectName("closeX")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(on_close)
        head.addWidget(heading, 1)
        head.addWidget(close_x)
        outer.addWidget(header)

        search_holder = QWidget(container)
        search_row = QHBoxLayout(search_holder)
        search_row.setContentsMargins(px(28, s), 0, px(28, s), px(16, s))
        self.search_line = QLineEdit(search_holder)
        self.search_line.setPlaceholderText(placeholder)
        self.search_line.setFixedHeight(px(48, s))
        add_search_icon(self.search_line)
        add_clear_button(self.search_line)
        search_row.addWidget(self.search_line)
        outer.addWidget(search_holder)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(px(28, s), 0, px(28, s), px(24, s))
        body_layout.setSpacing(0)
        for index, (name, items) in enumerate(categories):
            color = CATEGORY_COLORS[index % len(CATEGORY_COLORS)]
            head_widget = self._category_header(body, name, color, s)
            body_layout.addSpacing(px(14, s))
            body_layout.addWidget(head_widget)
            group_rows = []
            for key_text, desc in items:
                row = self._row(body, key_text, desc, s)
                body_layout.addWidget(row)
                info = {"row_widget": row, "key_orig": key_text, "desc_orig": desc, "category_orig": name}
                self.rows.append(info)
                group_rows.append(info)
            self._groups.append((head_widget, group_rows))
        self._empty = QLabel(empty_text, body)
        self._empty.setObjectName("empty")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setMinimumHeight(px(120, s))
        self._empty.hide()
        body_layout.addWidget(self._empty)
        body_layout.addStretch(1)

        scroll = QScrollArea(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.search_line.textChanged.connect(self.filter)

    @staticmethod
    def _category_header(parent, name, color, s):
        head = QWidget(parent)
        head.setObjectName("catHead")
        head.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 0, px(10, s))
        row.setSpacing(px(10, s))
        dot = QLabel(head)
        dot.setFixedSize(px(10, s), px(10, s))
        dot.setStyleSheet(f"background-color: {color}; border-radius: {px(5, s)}px;")
        title = QLabel(name, head)
        title.setObjectName("catTitle")
        title.setStyleSheet(f"color: {color};")
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
        return head

    @staticmethod
    def _row(parent, key_text, desc, s):
        row_widget = QWidget(parent)
        row_widget.setObjectName("shortRow")
        row_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row_widget.setMinimumHeight(px(52, s))
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, px(6, s), 0, px(6, s))
        row.setSpacing(px(24, s))

        keys_box = QWidget(row_widget)
        keys_box.setFixedWidth(px(250, s))
        keys_row = QHBoxLayout(keys_box)
        keys_row.setContentsMargins(0, 0, 0, 0)
        keys_row.setSpacing(px(6, s))
        keys, has_note = parse_keys(key_text)
        for key in keys:
            cap = QLabel(key, keys_box)
            cap.setObjectName("keycap")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap.setFixedHeight(px(34, s))
            cap.setMinimumWidth(px(34, s))
            keys_row.addWidget(cap)
        if has_note:
            note = QLabel("*", keys_box)
            note.setObjectName("note")
            keys_row.addWidget(note)
        keys_row.addStretch(1)

        text = QLabel(desc, row_widget)
        text.setWordWrap(True)
        row.addWidget(keys_box, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(text, 1, Qt.AlignmentFlag.AlignVCenter)
        return row_widget

    def filter(self, text):
        any_visible = False
        for head_widget, group_rows in self._groups:
            shown = 0
            for info in group_rows:
                visible = matches(text, strip_html(info["key_orig"]).replace("*", ""), strip_html(info["desc_orig"]))
                info["row_widget"].setVisible(visible)
                shown += visible
            head_widget.setVisible(shown > 0)
            any_visible = any_visible or shown > 0
        self._empty.setVisible(not any_visible)

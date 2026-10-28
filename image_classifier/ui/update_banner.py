"""Floating update pill anchored to the top-center of the main window."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from image_classifier.i18n.translations import translations
from image_classifier.updates import controller as states


class UpdateBanner(QWidget):
    def __init__(self, parent, controller, get_lang, on_install):
        super().__init__(parent)
        self._controller = controller
        self._get_lang = get_lang
        self._on_install = on_install
        self._got = 0
        self._total = 0

        self.setObjectName("UpdateBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#UpdateBanner {
                background-color: rgba(20, 20, 20, 235);
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 10px;
            }
            QLabel { background: transparent; color: white; font-size: 15px; }
            QPushButton {
                background-color: #0078D7; color: white; border: none;
                border-radius: 6px; padding: 6px 14px; font-size: 14px;
            }
            QPushButton:hover { background-color: #1a8cea; }
            QPushButton#secondary { background-color: #555555; }
            QPushButton#secondary:hover { background-color: #777777; }
            QProgressBar {
                background-color: #444; border-radius: 5px; border: none;
                min-height: 10px; max-height: 10px; min-width: 220px;
            }
            QProgressBar::chunk { background-color: #0078D7; border-radius: 5px; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 8)
        layout.setSpacing(10)
        self._label = QLabel(self)
        self._bar = QProgressBar(self)
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._primary = QPushButton(self)
        self._secondary = QPushButton(self)
        self._secondary.setObjectName("secondary")
        for button in (self._primary, self._secondary):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)
        layout.addWidget(self._primary)
        layout.addWidget(self._secondary)

        self._primary.clicked.connect(self._on_primary)
        self._secondary.clicked.connect(self._on_secondary)
        controller.phase_changed.connect(self._refresh)
        controller.progress_changed.connect(self._on_progress)
        self.hide()

    # -- helpers -------------------------------------------------------------
    def _t(self):
        return translations.get(self._get_lang(), translations["en"])

    def _progress_text(self):
        t = self._t()
        if self._total:
            pct = min(100, int(self._got * 100 / self._total))
            return t["update_progress_mb"].format(
                got=f"{self._got / 1_048_576:.0f}",
                total=f"{self._total / 1_048_576:.0f}",
                pct=pct,
            )
        return t["update_progress_pct"].format(pct=0)

    def reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        self.move(max(0, (parent.width() - self.width()) // 2), 16)
        self.raise_()

    # -- state -------------------------------------------------------------
    def _on_progress(self, got, total):
        self._got, self._total = got, total
        if self._controller.phase != states.DOWNLOADING:
            return
        self._bar.setValue(min(100, int(got * 100 / total)) if total else 0)
        self._label.setText(
            self._t()["update_downloading"].format(version=self._controller.version)
            + "  " + self._progress_text()
        )
        self.reposition()

    def refresh(self):
        self._refresh(self._controller.phase)

    def _refresh(self, phase):
        t = self._t()
        version = self._controller.version or ""
        self._bar.setVisible(phase == states.DOWNLOADING)
        self._secondary.setVisible(True)
        self._primary.setVisible(True)

        if phase == states.AVAILABLE:
            self._label.setText(t["update_available"].format(version=version))
            self._primary.setText(t["update_now"])
            self._secondary.setText("✕")
        elif phase == states.DOWNLOADING:
            self._bar.setValue(0)
            self._label.setText(t["update_downloading"].format(version=version))
            self._primary.setVisible(False)
            self._secondary.setText(t["update_cancel"])
        elif phase == states.READY:
            self._label.setText(t["update_ready"].format(version=version))
            self._primary.setText(t["update_restart"])
            self._secondary.setText(t["update_later"])
        elif phase == states.FAILED:
            self._label.setText(t["update_failed"])
            self._primary.setText(t["update_retry"])
            self._secondary.setText("✕")
        elif phase in (states.CURRENT, states.UNREACHABLE):
            key = "update_current" if phase == states.CURRENT else "update_unreachable"
            self._label.setText(t[key])
            self._primary.setVisible(False)
            self._secondary.setVisible(False)
        else:
            self.hide()
            return
        self.show()
        self.reposition()

    def _on_primary(self):
        phase = self._controller.phase
        if phase in (states.AVAILABLE, states.FAILED):
            self._controller.download()
        elif phase == states.READY:
            self._on_install()

    def _on_secondary(self):
        if self._controller.phase == states.DOWNLOADING:
            self._controller.cancel()
        else:
            self._controller.dismiss()

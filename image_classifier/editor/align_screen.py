"""Rotate and align screen (SPEC-008): any angle, nothing cropped, black corners.

A small full-window overlay in the style of the editor: the whole photo tilted on a black canvas that is
as large as the result, the straighten ruler, 90-degree turns, auto-straighten and Save. The photo shown is
a reduced frame; Save renders the real file in a background job (``imaging.huge.edit_file``).
"""
from __future__ import annotations

import os
from typing import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from image_classifier.editor import align
from image_classifier.editor import icons
from image_classifier.editor.auto_straighten import estimate_angle
from image_classifier.editor.editor_window import DOCK_FILL, EDGE, _row, _unique_copy
from image_classifier.editor.qtimage import qimage_to_rgba
from image_classifier.editor.widgets import (
    STYLE, Card, Divider, HaloButton, Popover, StraightenRuler, tool_button,
)
from image_classifier.i18n.translations import translations
from image_classifier.ui.huge_job import HugeJob
from image_classifier.workers.huge_worker import HugeEditWorker

PROXY_SIDE = 2048
RULER_WIDTH = 360


class _Canvas(QWidget):
    """The tilted photo inside the result frame."""

    def __init__(self, image: QImage, true_size: tuple[int, int], rot90: int, parent=None):
        super().__init__(parent)
        self._base = image
        self._true_size = true_size
        self._rot90 = 0
        self._oriented = image
        self._angle = 0.0
        self._grid = False
        self._insets = (EDGE, EDGE, EDGE, EDGE)
        self.set_view(rot90, 0.0)

    def set_view(self, rot90: int, angle: float):
        if rot90 != self._rot90:
            self._rot90 = rot90
            self._oriented = self._base.transformed(
                QTransform().rotate(90 * rot90), Qt.TransformationMode.SmoothTransformation) if rot90 else self._base
        self._angle = angle
        self.update()

    def set_insets(self, left, top, right, bottom):
        self._insets = (left, top, right, bottom)
        self.update()

    def set_grid(self, on: bool):
        self._grid = on
        self.update()

    def frame_rect(self) -> QRectF:
        cw, ch = align.canvas_size(self._true_size, self._rot90, self._angle)
        left, top, right, bottom = self._insets
        avail = QRectF(left, top, max(1, self.width() - left - right), max(1, self.height() - top - bottom))
        s = min(avail.width() / cw, avail.height() / ch)
        c = avail.center()
        return QRectF(c.x() - cw * s / 2.0, c.y() - ch * s / 2.0, cw * s, ch * s)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        frame = self.frame_rect()
        p.fillRect(frame, QColor(0, 0, 0))
        p.setClipRect(frame)
        oriented = self._oriented
        true_w, _true_h = (self._true_size[1], self._true_size[0]) if self._rot90 % 2 else self._true_size
        cw, _ = align.canvas_size(self._true_size, self._rot90, self._angle)
        screen_per_true = frame.width() / cw
        k = screen_per_true * true_w / oriented.width()
        p.translate(frame.center())
        p.rotate(self._angle)  # Qt: positive turns the photo clockwise, like the editor's straighten
        p.scale(k, k)
        p.drawImage(QPointF(-oriented.width() / 2.0, -oriented.height() / 2.0), oriented)
        p.resetTransform()
        if self._grid:
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            for i in range(1, 8):
                x = frame.left() + frame.width() * i / 8
                y = frame.top() + frame.height() * i / 8
                p.drawLine(QPointF(x, frame.top()), QPointF(x, frame.bottom()))
                p.drawLine(QPointF(frame.left(), y), QPointF(frame.right(), y))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        p.drawRect(frame)
        p.end()


class AlignScreen(QWidget):
    saved = pyqtSignal(str, bool)  # path, overwrote original
    closed = pyqtSignal()

    def __init__(self, parent: QWidget, source: QImage, source_path: str, true_size: tuple[int, int], *,
                 language: str = "en", rot90: int = 0, copy_path_for: Callable[[], str] | None = None,
                 confirm_overwrite: Callable[[], bool] | None = None, background: str = "#000000"):
        super().__init__(parent)
        self.setObjectName("AlignScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE + f"QWidget#AlignScreen {{ background: {background}; }}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._t = {**translations["en"], **translations.get(language, {})}
        self._language = language
        self._source_path = source_path
        self._true_size = (int(true_size[0]), int(true_size[1]))
        self._copy_path_for = copy_path_for
        self._confirm_overwrite = confirm_overwrite
        self._rot90 = int(rot90) % 4
        self._angle = 0.0
        self._job = None
        self._closing = False

        image = source
        if max(image.width(), image.height()) > PROXY_SIDE:
            image = image.scaled(PROXY_SIDE, PROXY_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        self._canvas = _Canvas(image, self._true_size, self._rot90, self)
        self._canvas.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._build_controls()
        self._toast = QLabel(self)
        self._toast.setStyleSheet("background: rgba(0,0,0,0.85); border: 1px solid rgba(255,255,255,0.12);"
                                  "border-radius: 8px; padding: 9px 16px; font-size: 14px;")
        self._toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast.hide)
        self._refresh()
        if parent is not None:
            self.setGeometry(parent.rect())
            parent.installEventFilter(self)
        self.show()
        self.raise_()
        self._layout()
        self.setFocus()

    # ------------------------------------------------------------------ public state
    @property
    def angle(self) -> float:
        return self._angle

    @property
    def rot90(self) -> int:
        return self._rot90

    @property
    def result_size(self) -> tuple[int, int]:
        return align.canvas_size(self._true_size, self._rot90, self._angle)

    @property
    def changed(self) -> bool:
        return self._rot90 != 0 or abs(self._angle) > 1e-6

    def set_angle(self, angle: float):
        self._angle = round(max(-self.ruler.LIMIT, min(self.ruler.LIMIT, float(angle))), 1)
        self.ruler.setValue(self._angle, emit=False)
        self._refresh()

    def turn(self, clockwise: bool):
        self._rot90 = (self._rot90 + (1 if clockwise else -1)) % 4
        self._refresh()

    # ------------------------------------------------------------------ build
    def _tr(self, key: str) -> str:
        return self._t.get(key, key)

    def _build_controls(self):
        self.btn_rot_left = HaloButton("rotate_left", self._tr("editor_rotate_left"), size=30, box=46)
        self.btn_rot_right = HaloButton("rotate_right", self._tr("editor_rotate_right"), size=30, box=46)
        self.ruler = StraightenRuler()
        self.ruler.setToolTip(self._tr("editor_straighten_hint"))
        self.ruler.set_decimal_separator("," if self._language == "es" else ".")
        self.ruler.setFixedWidth(RULER_WIDTH)
        self.btn_auto = HaloButton("straighten", self._tr("editor_auto_straighten"), size=30, box=46)
        self.btn_reset = HaloButton("reset", self._tr("editor_reset"), size=30, box=46)
        self.btn_save = tool_button(text=self._tr("editor_save_btn"), object_name="Primary")
        self.btn_save.setIcon(icons.icon("chevron_down", 16, halo=False))
        self.btn_save.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.btn_save.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.save_menu = Popover(self)
        self.save_menu.add_item("copy", self._tr("editor_save_copy"), self._tr("editor_save_copy_hint"),
                                lambda: self.save(overwrite=False), "Ctrl+Shift+S")
        self.save_menu.add_item("replace", self._tr("editor_save_replace"), self._tr("editor_save_replace_hint"),
                                lambda: self.save(overwrite=True), "Ctrl+S")
        self.btn_cancel = HaloButton("close", self._tr("editor_cancel") + "  (Esc)", size=30, box=48)
        self.actions = _row(self.btn_cancel, spacing=0, parent=self)
        self.tools = Card(self, radius=16, fill=QColor(*DOCK_FILL))
        dock = QHBoxLayout(self.tools)
        dock.setContentsMargins(10, 4, 10, 4)
        dock.addWidget(_row(self.btn_rot_left, self.btn_rot_right, 14, self.ruler, 14, self.btn_auto, Divider(),
                            self.btn_reset, 14, self.btn_save, spacing=2))
        self.info = QLabel(self)
        self.info.setStyleSheet("background: rgba(0,0,0,0.6); border-radius: 8px; padding: 6px 12px; font-size: 14px;")
        self.info.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.btn_rot_left.clicked.connect(lambda: self.turn(False))
        self.btn_rot_right.clicked.connect(lambda: self.turn(True))
        self.btn_reset.clicked.connect(self._reset)
        self.btn_auto.clicked.connect(self._auto)
        self.btn_cancel.clicked.connect(self._close)
        self.btn_save.clicked.connect(lambda: self.save_menu.open_under(self.btn_save))
        self.ruler.pressed.connect(lambda: self._canvas.set_grid(True))
        self.ruler.released.connect(lambda: self._canvas.set_grid(False))
        self.ruler.valueChanged.connect(self.set_angle)

    def _layout(self):
        w, h = self.width(), self.height()
        self._canvas.setGeometry(0, 0, w, h)
        self.actions.adjustSize()
        self.actions.move(w - self.actions.width() - EDGE, EDGE)
        self.tools.adjustSize()
        tools_y = h - self.tools.height() - EDGE
        self.tools.move((w - self.tools.width()) // 2, tools_y)
        self.info.adjustSize()
        self.info.move(EDGE, EDGE)
        self._canvas.set_insets(EDGE, EDGE + 56, EDGE, h - tools_y + 8)
        for overlay in (self.actions, self.tools, self.info):
            overlay.raise_()

    def _refresh(self):
        self._canvas.set_view(self._rot90, self._angle)
        width, height = self.result_size
        self.info.setText(self._tr("align_result_size").format(w=width, h=height))
        self.info.adjustSize()
        self.btn_save.setEnabled(self.changed)

    def _reset(self):
        self._rot90 = 0
        self.set_angle(0.0)

    def _auto(self):
        angle = estimate_angle(qimage_to_rgba(self._canvas._oriented))
        if angle is None:
            self._show_toast(self._tr("editor_no_lines"))
            return
        self.set_angle(angle)

    def _show_toast(self, text: str, ms: int = 2200):
        self._toast.setText(text)
        self._toast.adjustSize()
        self._toast.move((self.width() - self._toast.width()) // 2, EDGE + 6)
        self._toast.show()
        self._toast.raise_()
        self._toast_timer.start(ms)

    # ------------------------------------------------------------------ save / close
    def save(self, overwrite: bool):
        """RA-4/RA-5: render the result from the file in a background job."""
        self.save_menu.close_menu()
        if self._job is not None:
            return
        if not self.changed:
            self._show_toast(self._tr("editor_nothing_to_save"))
            return
        if overwrite:
            if self._confirm_overwrite is not None and not self._confirm_overwrite():
                return
            path = self._source_path
        else:
            path = self._copy_path_for() if self._copy_path_for else _unique_copy(self._source_path)
        state = align.align_state(self._true_size, self._rot90, self._angle)
        t = self._t
        job = HugeJob(
            self, HugeEditWorker(self._source_path, path, state, self), self._language,
            on_saved=lambda saved_path: (self.saved.emit(saved_path, overwrite), self._close()),
            on_failed=lambda message: self._show_toast(t["editor_save_failed"].format(error=message), 6000),
            on_canceled=lambda: self._show_toast(t["huge_save_canceled"]))
        job.done.connect(self._on_job_done)
        self._job = job
        job.start()

    def _on_job_done(self):
        job, self._job = self._job, None
        if job is not None:
            job.deleteLater()

    def _close(self):
        if self._closing:
            return
        self._closing = True
        if self.parent() is not None:
            self.parent().removeEventFilter(self)
        self.hide()
        self.closed.emit()
        self.deleteLater()

    # ------------------------------------------------------------------ events
    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == event.Type.Resize:
            self.setGeometry(obj.rect())
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout()

    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        step = 1.0 if shift else 0.1
        if k == Qt.Key.Key_Escape:
            self._close()
        elif ctrl and k == Qt.Key.Key_S:
            self.save(overwrite=not shift)  # Ctrl+S replace, Ctrl+Shift+S copy (same as the editor)
        elif k == Qt.Key.Key_Left and not ctrl:
            self.set_angle(self._angle - step)
        elif k == Qt.Key.Key_Right and not ctrl:
            self.set_angle(self._angle + step)
        elif k == Qt.Key.Key_0:
            self.set_angle(0.0)
        else:
            super().keyPressEvent(e)
            return
        e.accept()

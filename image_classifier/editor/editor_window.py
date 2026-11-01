"""The photo editor: Recortar + Ajuste tabs over a non-destructive EditState.

All edits flow through ``_set_state``. Widgets only display state and report
user intent; history stores states; pixels are rendered from the source at
preview resolution in a worker thread and at full resolution only on save.
"""
from __future__ import annotations

import os
from dataclasses import replace
from typing import Callable

import cv2
from PyQt6.QtCore import QEventLoop, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QImage
from PyQt6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QMenu, QScrollArea,
    QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from image_classifier.editor import geometry as g
from image_classifier.editor.adjust_canvas import AdjustCanvas
from image_classifier.editor.auto_straighten import estimate_angle
from image_classifier.editor.crop_canvas import CropCanvas, build_levels
from image_classifier.editor.history import EditHistory
from image_classifier.editor.preview_worker import PreviewWorker
from image_classifier.editor.qtimage import qimage_to_rgba, rgba_to_qimage
from image_classifier.editor.render import adjust_rgba, downscale, render
from image_classifier.editor.state import EditState
from image_classifier.editor.widgets import (
    STYLE, AdjustSlider, AspectStrip, StraightenRuler, TabButton, tool_button,
)
from image_classifier.i18n.translations import translations
from image_classifier.imaging.saver import save_rgba

# (key, icon) per Ajuste slider, grouped like Windows Photos
LIGHT = [("brightness", "brightness"), ("exposure", "exposure"), ("contrast", "contrast"),
         ("highlights", "highlights"), ("shadows", "shadows"), ("vignette", "vignette")]
COLOR = [("saturation", "saturation"), ("warmth", "warmth"), ("tint", "tint"), ("sharpness", "sharpness")]

# (translation key or literal label, ratio); "original" resolves to the image's own ratio
ASPECTS = [("editor_aspect_free", None), ("editor_aspect_original", "original"),
           ("editor_aspect_square", 1.0)] + [
    (f"{a} : {b}", a / b) for a, b in ((9, 16), (16, 9), (4, 5), (5, 4), (3, 4), (4, 3),
                                       (2, 3), (3, 2), (5, 7), (7, 5), (1, 2), (2, 1))]

PROXY_MIN, PROXY_MAX = 2048, 4096


class _Task(QThread):
    """Run one callable off the GUI thread (final renders)."""

    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # reported to the user, editor stays open
            self.error.emit(str(exc) or exc.__class__.__name__)


class _Modal(QFrame):
    """Windows 11 ContentDialog drawn inside the editor: centred card, title, body, button footer.

    Without buttons it is a small busy card (e.g. "Saving…").
    """

    WIDTH = 448

    def __init__(self, parent, title: str, body: str = "", buttons: list[tuple[str, str, str]] | None = None):
        super().__init__(parent)
        self.setObjectName("DialogBack")
        self.setGeometry(parent.rect())
        self.result = None
        self._loop = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(self)
        card.setObjectName("DialogCard")
        card.setFixedWidth(self.WIDTH if buttons else 280)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 150))
        card.setGraphicsEffect(shadow)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        content = QVBoxLayout()
        content.setContentsMargins(24, 22, 24, 24)
        content.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("DialogTitle" if buttons else "")
        heading.setWordWrap(True)
        if not buttons:
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(heading)
        if body:
            text = QLabel(body)
            text.setObjectName("DialogBody")
            text.setWordWrap(True)
            content.addWidget(text)
        lay.addLayout(content)
        if buttons:
            footer = QWidget()
            footer.setObjectName("DialogFooter")
            footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row = QHBoxLayout(footer)
            row.setContentsMargins(24, 24, 24, 24)
            row.setSpacing(8)
            for key, label, obj in reversed(buttons):  # primary first, like Windows
                b = tool_button(text=label, object_name=obj)
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                b.clicked.connect(lambda _=False, k=key: self._finish(k))
                row.addWidget(b, 1)
            lay.addWidget(footer)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        self.show()
        self.raise_()

    def _finish(self, key):
        self.result = key
        if self._loop is not None:
            self._loop.quit()

    def exec(self):
        self.setFocus()
        self._loop = QEventLoop()
        self._loop.exec()
        self.deleteLater()
        return self.result

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._finish(None)
        e.accept()


class PhotoEditor(QWidget):
    saved = pyqtSignal(str, bool)  # path, overwrote original
    closed = pyqtSignal()

    def __init__(self, parent: QWidget, source: QImage, source_path: str, *, language: str = "en",
                 rot90: int = 0, tab: str = "crop", copy_path_for: Callable[[], str] | None = None):
        super().__init__(parent)
        self.setObjectName("PhotoEditor")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE)
        self._t = {**translations["en"], **translations.get(language, {})}
        self._language = language
        self._source_path = source_path
        self._copy_path_for = copy_path_for
        self._src = qimage_to_rgba(source)
        self._size = (self._src.shape[1], self._src.shape[0])
        self._proxy = downscale(self._src, self._proxy_side())
        self._proxy_scale = self._proxy.shape[1] / self._size[0]
        self._orig_levels = build_levels(self._proxy, self._size)
        self._orig_qimage = self._orig_levels[0][0]
        self._history = EditHistory(EditState.initial(self._size, rot90))
        self._state = self._history.current
        self._straighten_base = None
        self._comparing = False
        self._shown_adjust = None  # Adjustments currently displayed on the crop canvas
        self._latest = {}
        self._task = None
        self._closing = False

        self._worker = PreviewWorker(self)
        self._worker.ready.connect(self._on_preview)

        self._build_ui()
        self.crop_canvas.set_levels(self._orig_levels)
        self._shown_adjust = self._state.adjust
        self._set_state(self._state, commit=False)
        self._switch_tab(tab)
        if parent is not None:
            self.setGeometry(parent.rect())
            parent.installEventFilter(self)
        self.show()
        self.raise_()
        self.crop_canvas.setFocus()

    # ================================================================== helpers
    def tr_(self, key: str) -> str:
        return self._t.get(key, key)

    def _proxy_side(self) -> int:
        screen = self.screen() or QGuiApplication.primaryScreen()
        side = PROXY_MIN
        if screen is not None:
            sz = screen.size()
            side = int(max(sz.width(), sz.height()) * screen.devicePixelRatio())
        return max(PROXY_MIN, min(PROXY_MAX, side))

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == event.Type.Resize:
            self.setGeometry(obj.rect())
        return False

    # ================================================================== UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)
        self.stack = QStackedWidget()
        self.crop_canvas = CropCanvas()
        self.adjust_canvas = AdjustCanvas()
        self.stack.addWidget(self.crop_canvas)
        self.stack.addWidget(self.adjust_canvas)
        center.addWidget(self.stack, 1)
        self.bottom_bar = self._build_bottom_bar()
        center.addWidget(self.bottom_bar)
        body.addLayout(center, 1)
        self.panel = self._build_panel()
        body.addWidget(self.panel)
        root.addLayout(body, 1)

        self.crop_canvas.stateEdited.connect(self._on_canvas_state)
        self.crop_canvas.zoomChanged.connect(self._on_zoom)
        self.adjust_canvas.zoomChanged.connect(self._on_zoom)

        self._toast = QLabel(self)
        self._toast.setStyleSheet("background: #2b2b2b; border: 1px solid #3a3a3a; border-radius: 6px;"
                                  "padding: 8px 14px; font-size: 13px;")
        self._toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast.hide)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("EditorTopBar")
        bar.setFixedHeight(56)
        grid = QGridLayout(bar)
        grid.setContentsMargins(12, 6, 12, 6)

        left = QHBoxLayout()
        left.setSpacing(2)
        self.btn_zoom_in = tool_button("zoom_in", tooltip=self.tr_("editor_zoom_in"))
        self.btn_zoom_out = tool_button("zoom_out", tooltip=self.tr_("editor_zoom_out"))
        self.btn_fit = tool_button("fit", tooltip=self.tr_("editor_zoom_fit"))
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setObjectName("Dim")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3a3a3a;")
        self.btn_reset = tool_button(text=self.tr_("editor_reset"))
        self.btn_undo = tool_button("undo", tooltip=self.tr_("editor_undo"))
        self.btn_redo = tool_button("redo", tooltip=self.tr_("editor_redo"))
        for w in (self.btn_zoom_in, self.btn_zoom_out, self.btn_fit, self.zoom_label, sep,
                  self.btn_reset, self.btn_undo, self.btn_redo):
            left.addWidget(w)
        left.addStretch(1)

        tabs = QHBoxLayout()
        tabs.setSpacing(18)
        self.tab_crop = TabButton("crop", self.tr_("editor_tab_crop"))
        self.tab_adjust = TabButton("adjust", self.tr_("editor_tab_adjust"))
        for b in (self.tab_crop, self.tab_adjust):
            tabs.addWidget(b)

        right = QHBoxLayout()
        right.setSpacing(8)
        right.addStretch(1)
        self.btn_compare = tool_button("compare", tooltip=self.tr_("editor_compare"))
        self.btn_save = tool_button(text=self.tr_("editor_save_options"), object_name="Primary")
        self.btn_save.setIcon(_chevron())
        self.btn_save.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.btn_save.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_save.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.btn_save)
        menu.addAction(self.tr_("editor_save_copy"), lambda: self._save(overwrite=False))
        menu.addAction(self.tr_("editor_save"), lambda: self._save(overwrite=True))
        menu.addSeparator()
        menu.addAction(self.tr_("editor_copy_clipboard"), self._copy_to_clipboard)
        self.btn_save.setMenu(menu)
        self.btn_cancel = tool_button(text=self.tr_("editor_cancel"), object_name="Secondary")
        for w in (self.btn_compare, self.btn_save, self.btn_cancel):
            right.addWidget(w)

        grid.addLayout(left, 0, 0)
        grid.addLayout(tabs, 0, 1, Qt.AlignmentFlag.AlignCenter)
        grid.addLayout(right, 0, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)

        self.btn_zoom_in.clicked.connect(lambda: self._zoom(1.25))
        self.btn_zoom_out.clicked.connect(lambda: self._zoom(0.8))
        self.btn_fit.clicked.connect(self._fit)
        self.btn_reset.clicked.connect(self._reset)
        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo.clicked.connect(self._redo)
        self.tab_crop.clicked.connect(lambda: self._switch_tab("crop"))
        self.tab_adjust.clicked.connect(lambda: self._switch_tab("adjust"))
        self.btn_compare.pressed.connect(lambda: self._set_compare(True))
        self.btn_compare.released.connect(lambda: self._set_compare(False))
        self.btn_cancel.clicked.connect(self.request_cancel)
        return bar

    def _build_bottom_bar(self) -> QWidget:
        """Two pages like Windows Photos: straighten + tools, or the aspect-ratio strip + Done."""
        bar = QStackedWidget()
        bar.setObjectName("EditorBottomBar")

        # page 0: ruler above the tool row
        tools_page = QWidget()
        lay = QVBoxLayout(tools_page)
        lay.setContentsMargins(12, 4, 12, 14)
        lay.setSpacing(6)
        ruler_row = QHBoxLayout()
        ruler_row.setSpacing(8)
        ruler_row.addStretch(1)
        self.ruler = StraightenRuler()
        self.ruler.setFixedWidth(560)
        self.ruler.set_decimal_separator("," if self._language == "es" else ".")
        self.btn_auto = tool_button(text=self.tr_("editor_auto"), tooltip=self.tr_("editor_auto_straighten"),
                                    object_name="Secondary")
        ruler_spacer = QWidget()
        ruler_spacer.setFixedWidth(self.btn_auto.sizeHint().width())  # keep the ruler centred
        ruler_row.addWidget(ruler_spacer)
        ruler_row.addWidget(self.ruler)
        ruler_row.addWidget(self.btn_auto, 0, Qt.AlignmentFlag.AlignBottom)
        ruler_row.addStretch(1)
        lay.addLayout(ruler_row)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        tools.addStretch(1)
        self.btn_rot_left = tool_button("rotate_left", tooltip=self.tr_("editor_rotate_left"))
        self.btn_rot_right = tool_button("rotate_right", tooltip=self.tr_("editor_rotate_right"))
        self.btn_aspect = tool_button("aspect", self.tr_("editor_aspect_free"),
                                      tooltip=self.tr_("editor_aspect_title"))
        self.btn_aspect.setMinimumWidth(150)
        self.btn_flip_h = tool_button("flip_h", tooltip=self.tr_("editor_flip_h"))
        self.btn_flip_v = tool_button("flip_v", tooltip=self.tr_("editor_flip_v"))
        for w in (self.btn_rot_left, self.btn_rot_right):
            tools.addWidget(w)
        tools.addSpacing(40)
        tools.addWidget(self.btn_aspect)
        tools.addSpacing(40)
        for w in (self.btn_flip_h, self.btn_flip_v):
            tools.addWidget(w)
        tools.addStretch(1)
        lay.addLayout(tools)
        bar.addWidget(tools_page)

        # page 1: aspect-ratio strip
        aspect_page = QWidget()
        alay = QVBoxLayout(aspect_page)
        alay.setContentsMargins(12, 8, 12, 14)
        alay.setSpacing(6)
        self._aspect_labels = [self.tr_(k) if k.startswith("editor_") else k for k, _ in ASPECTS]
        self.aspect_strip = AspectStrip(list(zip(self._aspect_labels, (r for _, r in ASPECTS))))
        self.btn_aspect_done = tool_button(text=self.tr_("editor_done"))
        self.btn_aspect_done.setMinimumWidth(120)
        alay.addWidget(self.aspect_strip)
        alay.addWidget(self.btn_aspect_done, 0, Qt.AlignmentFlag.AlignHCenter)
        bar.addWidget(aspect_page)

        self.btn_aspect.clicked.connect(lambda: self._show_aspect_strip(True))
        self.btn_aspect_done.clicked.connect(lambda: self._show_aspect_strip(False))
        self.aspect_strip.picked.connect(lambda i: self._set_aspect(ASPECTS[i][1]))
        self.ruler.pressed.connect(self._ruler_pressed)
        self.ruler.valueChanged.connect(self._ruler_changed)
        self.ruler.released.connect(self._ruler_released)
        self.btn_auto.clicked.connect(self._auto_straighten)
        self.btn_rot_left.clicked.connect(lambda: self._orient(lambda s: g.rotate90(s, False)))
        self.btn_rot_right.clicked.connect(lambda: self._orient(lambda s: g.rotate90(s, True)))
        self.btn_flip_h.clicked.connect(lambda: self._orient(lambda s: g.flip(s, True)))
        self.btn_flip_v.clicked.connect(lambda: self._orient(lambda s: g.flip(s, False)))
        return bar

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("EditorPanel")
        panel.setFixedWidth(330)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(18, 14, 18, 18)
        lay.setSpacing(2)
        self.sliders: dict[str, AdjustSlider] = {}
        for title_key, rows in (("editor_group_light", LIGHT), ("editor_group_color", COLOR)):
            title = QLabel(self.tr_(title_key))
            title.setObjectName("GroupTitle")
            lay.addWidget(title)
            lay.addSpacing(6)
            for name, icon_name in rows:
                s = AdjustSlider(name, self.tr_(f"editor_adj_{name}"), icon_name)
                s.valueChanged.connect(self._slider_changed)
                s.committed.connect(self._slider_committed)
                self.sliders[name] = s
                lay.addWidget(s)
            lay.addSpacing(14)
        lay.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return panel

    # ================================================================== state funnel
    def _set_state(self, state: EditState, *, commit: bool, source: str = "", view: str = "keep"):
        prev = self._state
        self._state = state
        if commit:
            self._history.push(state)
        if source not in ("ruler", "auto") and state.crop != prev.crop:
            self._straighten_base = None
        if source != "canvas":
            self.crop_canvas.set_state(state, view=view)
        if source != "ruler":
            self.ruler.setValue(state.crop.angle)
        if source != "slider":
            for name, s in self.sliders.items():
                s.set_value(getattr(state.adjust, name))
        self._sync_aspect_label()
        self._update_actions()
        self._request_previews()

    def _update_actions(self):
        self.btn_undo.setEnabled(self._history.can_undo())
        self.btn_redo.setEnabled(self._history.can_redo())
        self.btn_reset.setEnabled(self._state != self._history.initial or not self._state.is_identity)
        self.btn_save.setEnabled(not self._state.is_identity)

    def _sync_aspect_label(self):
        ratio = self._state.aspect
        W, H = self._state.oriented_size
        label = f"{ratio:.2f}" if ratio is not None else ""
        for i, (_, r) in enumerate(ASPECTS):
            value = W / H if r == "original" else r
            if (ratio is None and value is None) or (
                    ratio is not None and value is not None and abs(ratio - value) < 1e-6):
                self.aspect_strip.set_current(i)
                label = self._aspect_labels[i]
                break
        self.btn_aspect.setText(" " + label)

    def _show_aspect_strip(self, show: bool):
        self.bottom_bar.setCurrentIndex(1 if show else 0)

    # ================================================================== previews
    def _request_previews(self):
        adj = self._state.adjust
        if adj != self._shown_adjust:
            self._shown_adjust = adj
            if adj.is_identity:
                self._latest["crop"] = self._worker.latest() + 1  # invalidate in-flight crop jobs
                self.crop_canvas.set_levels(self._orig_levels)
            else:
                proxy, size = self._proxy, self._size
                self._latest["crop"] = self._worker.submit(
                    "crop", lambda: build_levels(adjust_rgba(proxy, adj, vignette=False), size))
        if self.stack.currentWidget() is self.adjust_canvas:
            state, proxy = self._state, self._proxy
            dpr = self.devicePixelRatioF()
            target = max(self.adjust_canvas.width(), self.adjust_canvas.height()) * dpr * 1.25
            scale = min(self._proxy_scale, target / max(state.crop.w, state.crop.h))
            self._latest["final"] = self._worker.submit(
                "final", lambda: (rgba_to_qimage(render(proxy, state, scale=scale,
                                                        interpolation=cv2.INTER_CUBIC)), state.output_size))

    def _on_preview(self, result, gen: int, channel: str):
        if gen < self._latest.get(channel, 0) or self._closing:
            return
        if channel == "crop":
            self.crop_canvas.set_levels(result)
        else:
            image, size = result
            self.adjust_canvas.set_image(image, size)

    # ================================================================== interactions
    def _on_canvas_state(self, state: EditState, committed: bool):
        self._set_state(state, commit=committed, source="canvas")

    def _ruler_pressed(self):
        if self._straighten_base is None:
            self._straighten_base = self._state.crop
        self.crop_canvas.set_grid("fine")

    def _ruler_changed(self, angle: float):
        base = self._straighten_base or self._state.crop
        crop = g.fit_to_angle(base, angle, self._state.oriented_size)
        self._set_state(self._state.with_crop(crop), commit=False, source="ruler")

    def _ruler_released(self):
        self.crop_canvas.set_grid(None)
        self._set_state(self._state, commit=True, source="ruler")

    def _auto_straighten(self):
        angle = estimate_angle(self._proxy)
        if angle is None:
            self._show_toast(self.tr_("editor_no_lines"))
            return
        if self._state.orientation.flip:
            angle = -angle
        if self._straighten_base is None:
            self._straighten_base = self._state.crop
        crop = g.fit_to_angle(self._straighten_base, angle, self._state.oriented_size)
        self._set_state(self._state.with_crop(crop), commit=True, source="auto")

    def _orient(self, fn):
        self._set_state(fn(self._state), commit=True, view="fit")

    def _set_aspect(self, ratio):
        W, H = self._state.oriented_size
        r = W / H if ratio == "original" else ratio
        crop = g.set_aspect(self._state.crop, r, self._state.oriented_size)
        self._set_state(replace(self._state, aspect=r, crop=crop), commit=True)

    def _slider_changed(self, name: str, value: int):
        self._set_state(self._state.with_adjust(**{name: value}), commit=False, source="slider")

    def _slider_committed(self, _name: str):
        self._set_state(self._state, commit=True, source="slider")

    def _undo(self):
        self._set_state(self._history.undo(), commit=False)

    def _redo(self):
        self._set_state(self._history.redo(), commit=False)

    def _reset(self):
        self._set_state(EditState.initial(self._size), commit=True, view="fit")

    def _switch_tab(self, tab: str):
        crop = tab == "crop"
        self.tab_crop.setChecked(crop)
        self.tab_adjust.setChecked(not crop)
        self.stack.setCurrentWidget(self.crop_canvas if crop else self.adjust_canvas)
        self.bottom_bar.setVisible(crop)
        self.panel.setVisible(not crop)
        (self.crop_canvas if crop else self.adjust_canvas).setFocus()
        if not crop:
            QTimer.singleShot(0, self._request_previews)  # canvas has its final size after layout

    def _zoom(self, factor: float):
        if self.stack.currentWidget() is self.crop_canvas:
            self.crop_canvas.zoom_by(factor)
        else:
            self.adjust_canvas.zoom_by(factor)

    def _fit(self):
        if self.stack.currentWidget() is self.crop_canvas:
            self.crop_canvas.fit()
        else:
            self.adjust_canvas.fit()

    def _on_zoom(self, z: float):
        if self.sender() is self.stack.currentWidget():
            self.zoom_label.setText(f"{round(z * 100)} %")

    def _set_compare(self, on: bool):
        if on == self._comparing:
            return
        self._comparing = on
        if on:
            self._compare_return = self.stack.currentWidget()
            self.adjust_canvas.set_compare((self._orig_qimage, self._size))
            self.stack.setCurrentWidget(self.adjust_canvas)
        else:
            self.adjust_canvas.set_compare(None)
            self.stack.setCurrentWidget(self._compare_return)

    def _show_toast(self, text: str, ms: int = 1800):
        self._toast.setText(text)
        self._toast.adjustSize()
        self._toast.move((self.width() - self._toast.width()) // 2, 72)
        self._toast.show()
        self._toast.raise_()
        self._toast_timer.start(ms)

    # ================================================================== keyboard
    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if k == Qt.Key.Key_Escape and self.bottom_bar.currentIndex() == 1:
            self._show_aspect_strip(False)
        elif k == Qt.Key.Key_Escape:
            self.request_cancel()
        elif ctrl and k == Qt.Key.Key_Z and not shift:
            self._undo()
        elif ctrl and (k == Qt.Key.Key_Y or (k == Qt.Key.Key_Z and shift)):
            self._redo()
        elif ctrl and k == Qt.Key.Key_0:
            self._fit()
        elif ctrl and k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom(1.25)
        elif ctrl and k == Qt.Key.Key_Minus:
            self._zoom(0.8)
        elif k == Qt.Key.Key_Backslash and not e.isAutoRepeat():
            self._set_compare(True)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.btn_save.isEnabled():
            self.btn_save.showMenu()
        else:
            super().keyPressEvent(e)
            return
        e.accept()

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Backslash and not e.isAutoRepeat():
            self._set_compare(False)
            e.accept()
            return
        super().keyReleaseEvent(e)

    # ================================================================== save / close
    def _busy(self, text: str) -> _Modal:
        return _Modal(self, text)

    def _run_final(self, fn, on_done):
        state, src = self._state, self._src
        busy = self._busy(self.tr_("editor_saving"))
        self._task = _Task(lambda: fn(render(src, state)), self)

        def finish_ok(result):
            busy.deleteLater()
            on_done(result)

        def finish_err(msg):
            busy.deleteLater()
            _Modal(self, self.tr_("editor_save_failed").format(error=msg),
                   buttons=[("ok", "OK", "Primary")]).exec()

        self._task.done.connect(finish_ok)
        self._task.error.connect(finish_err)
        self._task.start()

    def _save(self, overwrite: bool):
        if self._task is not None and self._task.isRunning():
            return
        if overwrite:
            name = os.path.basename(self._source_path)
            choice = _Modal(self, self.tr_("editor_overwrite_title"),
                            self.tr_("editor_overwrite_message").format(name=name), [
                ("cancel", self.tr_("editor_cancel"), "Secondary"),
                ("ok", self.tr_("editor_overwrite_confirm"), "Primary"),
            ]).exec()
            if choice != "ok":
                return
            path = self._source_path
        else:
            path = self._copy_path_for() if self._copy_path_for else _unique_copy(self._source_path)
        source = self._source_path

        def write(pixels):
            save_rgba(path, pixels, source_path=source)
            return path

        def done(saved_path):
            self.saved.emit(saved_path, overwrite)
            self._close()

        self._run_final(write, done)

    def _copy_to_clipboard(self):
        if self._task is not None and self._task.isRunning():
            return

        def done(image):
            QGuiApplication.clipboard().setImage(image)
            self._show_toast(self.tr_("editor_copied"))

        self._run_final(rgba_to_qimage, done)

    def request_cancel(self):
        if self._history.is_dirty:
            choice = _Modal(self, self.tr_("editor_discard_message"), self.tr_("editor_discard_body"), [
                ("keep", self.tr_("editor_keep_editing"), "Secondary"),
                ("discard", self.tr_("editor_discard"), "Primary"),
            ]).exec()
            if choice != "discard":
                return
        self._close()

    def _close(self):
        if self._closing:
            return
        self._closing = True
        self._worker.stop()
        if self.parent() is not None:
            self.parent().removeEventFilter(self)
        self.hide()
        self.closed.emit()
        self.deleteLater()


def _chevron():
    from image_classifier.editor import icons
    return icons.icon("chevron_down", 12, "#000000")


def _unique_copy(path: str) -> str:
    folder, filename = os.path.split(path)
    name, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, f"{name}_copy{ext}")
    n = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{name}_copy_{n}{ext}")
        n += 1
    return candidate

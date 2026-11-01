"""The photo editor: crop and adjust over a non-destructive EditState.

Layout follows the viewer itself: one full-bleed canvas in the theme colour
with controls floating over it (halo icons on the left like the main menu,
a single tool row at the bottom, save/close at the top right, and a
translucent card for the adjustment sliders). The canvases are told which
margins the controls occupy, so a fitted photo is never covered.

All edits flow through ``_set_state``. Widgets only display state and report
user intent; history stores states; pixels are rendered from the source at
preview resolution in a worker thread and at full resolution only on save.
"""
from __future__ import annotations

import os
from dataclasses import replace
from typing import Callable

import cv2
from PyQt6.QtCore import QEasingCurve, QEventLoop, QPropertyAnimation, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QImage
from PyQt6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from image_classifier.editor import geometry as g
from image_classifier.editor import icons
from image_classifier.editor.adjust_canvas import AdjustCanvas
from image_classifier.editor.auto_straighten import estimate_angle
from image_classifier.editor.crop_canvas import CropCanvas, build_levels
from image_classifier.editor.history import EditHistory
from image_classifier.editor.preview_worker import PreviewWorker
from image_classifier.editor.qtimage import qimage_to_rgba, rgba_to_qimage
from image_classifier.editor.render import adjust_rgba, downscale, render
from image_classifier.editor.state import Adjustments, EditState
from image_classifier.editor.widgets import (
    STYLE, AdjustSlider, AspectStrip, Card, HaloButton, HaloTextButton, Popover, StraightenRuler, tool_button,
)
from image_classifier.i18n.translations import translations
from image_classifier.imaging.saver import save_rgba

LIGHT = ["brightness", "exposure", "contrast", "highlights", "shadows", "vignette"]
COLOR = ["saturation", "warmth", "tint", "sharpness"]

# (translation key or literal label, ratio); "original" resolves to the image's own ratio
ASPECTS = [("editor_aspect_free", None), ("editor_aspect_original", "original"),
           ("editor_aspect_square", 1.0)] + [
    (f"{a} : {b}", a / b) for a, b in ((9, 16), (16, 9), (4, 5), (5, 4), (3, 4), (4, 3),
                                       (2, 3), (3, 2), (5, 7), (7, 5), (1, 2), (2, 1))]

PROXY_MIN, PROXY_MAX = 2048, 4096
EDGE = 16  # gap between floating controls and the window edge
PANEL_W = 340


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
    """Centred confirm card over a dimmed editor, styled exactly like the viewer's own
    dialogs (export favorites, messages): black card, title on a dark pill, equal-width
    buttons with the action in blue first and the way out in red. Scales with the window.

    Without buttons it is a small busy card (e.g. "Saving...").
    """

    WIDTH = 420

    def __init__(self, parent, title: str, body: str = "", buttons: list[tuple[str, str, str]] | None = None):
        super().__init__(parent)
        self.setStyleSheet("QFrame#DialogBack { background: rgba(0,0,0,150); }")
        self.setObjectName("DialogBack")
        self.setGeometry(parent.rect())
        self.result = None
        self._loop = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        s = max(1.0, min(1.5, parent.width() / 1400))  # never tiny on a large window

        def px(v):
            return f"{round(v * s)}px"

        card = QWidget(self)
        card.setObjectName("DialogCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setFixedWidth(round((self.WIDTH if buttons else 260) * s))
        card.setStyleSheet(f"""
            QWidget#DialogCard {{ background-color: rgba(0, 0, 0, 200); border-radius: 8px;
                                  border: 1px solid rgba(255, 255, 255, 30); }}
            QLabel {{ background: transparent; color: white; font-size: {px(16)}; }}
            QLabel#DialogTitle {{ font-size: {px(18)}; font-weight: bold; background-color: rgba(25, 25, 25, 200);
                                  border-radius: 6px; padding: {px(8)}; }}
            QToolButton {{ color: white; border: none; border-radius: 6px; font-size: {px(15)};
                           padding: {px(8)} {px(12)}; min-height: {px(22)};
                           background-color: rgba(50, 50, 50, 200); }}
            QToolButton:hover {{ background-color: rgba(70, 70, 70, 220); }}
            QToolButton#Primary {{ background-color: #007BFF; }}
            QToolButton#Primary:hover {{ background-color: #0056b3; }}
            QToolButton#Danger {{ background-color: #DC3545; }}
            QToolButton#Danger:hover {{ background-color: #B22222; }}
        """)
        lay = QVBoxLayout(card)
        m = round(20 * s)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(round(12 * s))
        heading = QLabel(title)
        heading.setWordWrap(True)
        if buttons:
            heading.setObjectName("DialogTitle")
        else:
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(heading)
        if body:
            text = QLabel(body)
            text.setWordWrap(True)
            text.setContentsMargins(round(4 * s), 0, round(4 * s), 0)
            lay.addWidget(text)
        if buttons:
            lay.addSpacing(round(4 * s))
            row = QHBoxLayout()
            row.setSpacing(round(10 * s))
            for key, label, obj in buttons:
                b = tool_button(text=label, object_name=obj)
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                b.setFixedHeight(round(38 * s))
                b.clicked.connect(lambda _=False, k=key: self._finish(k))
                row.addWidget(b)
            lay.addLayout(row)
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


def _row(*widgets, spacing=4, parent=None, vertical=False) -> QWidget:
    holder = QWidget(parent)
    holder.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    lay = QVBoxLayout(holder) if vertical else QHBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        else:
            lay.addWidget(w, 0, Qt.AlignmentFlag.AlignCenter)
    holder.adjustSize()
    return holder


class PhotoEditor(QWidget):
    saved = pyqtSignal(str, bool)  # path, overwrote original
    closed = pyqtSignal()

    def __init__(self, parent: QWidget, source: QImage, source_path: str, *, language: str = "en",
                 rot90: int = 0, brightness: int = 0, tab: str = "crop",
                 copy_path_for: Callable[[], str] | None = None,
                 background: str = "#000000"):
        super().__init__(parent)
        self.setObjectName("PhotoEditor")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE + f"QWidget#PhotoEditor {{ background: {background}; }}")
        self._bg = QColor(background)
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
        start = EditState.initial(self._size, rot90)
        if brightness:  # brightness already applied in the viewer carries over (same maths)
            start = start.with_adjust(brightness=max(-100, min(100, int(brightness))))
        self._history = EditHistory(start)
        self._state = self._history.current
        self._straighten_base = None
        self._comparing = False
        self._shown_adjust = None  # Adjustments currently displayed on the crop canvas
        self._latest = {}
        self._task = None
        self._closing = False
        self._tab = "crop"
        self._crop_session = 0  # history index when the crop tool was entered; "Done" squashes after it

        self._worker = PreviewWorker(self)
        self._worker.ready.connect(self._on_preview)
        app = QGuiApplication.instance()
        if app is not None:  # never leave the render thread running at exit
            app.aboutToQuit.connect(self._worker.stop)

        self._build_ui()
        self.crop_canvas.set_levels(self._orig_levels)
        self._shown_adjust = Adjustments()  # the original levels are unadjusted
        self._set_state(self._state, commit=False)
        self._switch_tab(tab)
        if parent is not None:
            self.setGeometry(parent.rect())
            parent.installEventFilter(self)
        self.show()
        self.raise_()
        self._layout_overlays()
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
        self.stack = QStackedWidget(self)
        self.crop_canvas = CropCanvas()
        self.adjust_canvas = AdjustCanvas()
        for c in (self.crop_canvas, self.adjust_canvas):
            c.set_background(self._bg)
            self.stack.addWidget(c)
        self.crop_canvas.stateEdited.connect(self._on_canvas_state)
        self.crop_canvas.zoomChanged.connect(self._on_zoom)
        self.adjust_canvas.zoomChanged.connect(self._on_zoom)
        self.crop_canvas.userZoomed.connect(self._flash_zoom)
        self.adjust_canvas.userZoomed.connect(self._flash_zoom)
        self.adjust_canvas.userZoomed.connect(self._request_previews)  # sharper pixels when zoomed in
        self.crop_canvas.rotateStarted.connect(self._ruler_pressed)
        self.crop_canvas.rotateChanged.connect(self._ruler_changed)
        self.crop_canvas.rotateFinished.connect(self._ruler_released)

        self._build_rail()
        self._build_actions()
        self._build_crop_tools()
        self._build_panel()

        self.zoom_label = QLabel(self)
        self.zoom_label.setStyleSheet("background: rgba(0,0,0,0.75); border-radius: 6px; padding: 5px 10px;"
                                      "font-size: 13px;")
        self.zoom_label.hide()
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self.zoom_label.hide)

        self._toast = QLabel(self)
        self._toast.setStyleSheet("background: rgba(0,0,0,0.85); border: 1px solid rgba(255,255,255,0.12);"
                                  "border-radius: 8px; padding: 9px 16px; font-size: 14px;")
        self._toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast.hide)

    def _build_rail(self):
        """Vertical halo icons on the left, exactly where the viewer keeps its menu."""
        self.tab_crop = HaloButton("crop", self.tr_("editor_tab_crop"), size=34, box=52)
        self.tab_adjust = HaloButton("adjust", self.tr_("editor_tab_adjust"), size=34, box=52)
        for b in (self.tab_crop, self.tab_adjust):
            b.setCheckable(True)
        self.btn_undo = HaloButton("undo", self.tr_("editor_undo") + "  (Ctrl+Z)", size=30, box=50)
        self.btn_redo = HaloButton("redo", self.tr_("editor_redo") + "  (Ctrl+Y)", size=30, box=50)
        self.btn_reset = HaloButton("reset", self.tr_("editor_reset"), size=30, box=50)
        self.rail = _row(self.tab_crop, self.tab_adjust, 22, self.btn_undo, self.btn_redo, self.btn_reset,
                         spacing=8, parent=self, vertical=True)

        self.tab_crop.clicked.connect(lambda: self._switch_tab("crop"))
        self.tab_adjust.clicked.connect(lambda: self._switch_tab("adjust"))
        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo.clicked.connect(self._redo)
        self.btn_reset.clicked.connect(self._reset)

    def _build_actions(self):
        """Top right: one accent save button with its options, and a close icon."""
        self.btn_save = tool_button(text=self.tr_("editor_save_btn"), object_name="Primary")
        self.btn_save.setIcon(icons.icon("chevron_down", 16, halo=False))
        self.btn_save.setIconSize(QSize(16, 16))
        self.btn_save.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # chevron after the label
        self.btn_save.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.save_menu = Popover(self)
        self.save_menu.add_item("copy", self.tr_("editor_save_copy"), self.tr_("editor_save_copy_hint"),
                                lambda: self._save(overwrite=False))
        self.save_menu.add_item("replace", self.tr_("editor_save_replace"), self.tr_("editor_save_replace_hint"),
                                lambda: self._save(overwrite=True))
        self.save_menu.add_separator()
        self.save_menu.add_item("clipboard", self.tr_("editor_copy_clipboard"), "", self._copy_to_clipboard)
        self.btn_save.clicked.connect(lambda: self.save_menu.open_under(self.btn_save))
        self.btn_cancel = HaloButton("close", self.tr_("editor_cancel") + "  (Esc)", size=30, box=48)
        self.actions = _row(self.btn_save, 6, self.btn_cancel, spacing=4, parent=self)
        self.btn_cancel.clicked.connect(self.request_cancel)

    def _build_crop_tools(self):
        """Bottom row: crop tools (rotate, ruler, flip, ratio, auto), compare, and Done.

        Compare stays on every tab; the crop tools and Done only on Crop. Ratios open
        in a card above the row.
        """
        self.btn_rot_left = HaloButton("rotate_left", self.tr_("editor_rotate_left"), size=30, box=46)
        self.btn_rot_right = HaloButton("rotate_right", self.tr_("editor_rotate_right"), size=30, box=46)
        self.ruler = StraightenRuler()
        self.ruler.setFixedWidth(360)
        self.ruler.setToolTip(self.tr_("editor_straighten_hint"))
        self.ruler.set_decimal_separator("," if self._language == "es" else ".")
        self.btn_flip_h = HaloButton("flip_h", self.tr_("editor_flip_h"), size=30, box=46)
        self.btn_flip_v = HaloButton("flip_v", self.tr_("editor_flip_v"), size=30, box=46)
        self.btn_aspect = HaloTextButton(
            "aspect", self.tr_("editor_aspect_free"), self.tr_("editor_aspect_title"), size=28, height=46,
            reserve=[self.tr_(k) if k.startswith("editor_") else k for k, _ in ASPECTS])
        self.btn_aspect.setCheckable(True)
        self.btn_auto = HaloButton("auto", self.tr_("editor_auto_straighten"), size=30, box=46)
        self.crop_group = _row(self.btn_rot_left, self.btn_rot_right, 14, self.ruler, 14,
                               self.btn_flip_h, self.btn_flip_v, 18, self.btn_aspect, self.btn_auto, 10,
                               spacing=2)
        self.btn_compare = HaloButton("compare", self.tr_("editor_compare"), size=30, box=46)
        self.btn_apply = tool_button(text=self.tr_("editor_done"), tooltip=self.tr_("editor_apply_hint"),
                                     object_name="Primary")
        self.btn_apply.setIcon(icons.icon("check", 18, halo=False))
        self.btn_apply.setIconSize(QSize(18, 18))
        self.btn_apply.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.apply_group = _row(14, self.btn_apply, spacing=0)
        self.crop_tools = _row(self.crop_group, self.btn_compare, self.apply_group, spacing=0, parent=self)
        self.btn_compare.pressed.connect(lambda: self._set_compare(True))
        self.btn_compare.released.connect(lambda: self._set_compare(False))
        self.btn_apply.clicked.connect(self._apply_crop)
        self.crop_canvas.acceptRequested.connect(self._apply_crop)

        self._aspect_labels = [self.tr_(k) if k.startswith("editor_") else k for k, _ in ASPECTS]
        self.aspect_card = Card(self, radius=14)
        lay = QVBoxLayout(self.aspect_card)
        lay.setContentsMargins(10, 12, 10, 8)
        self.aspect_strip = AspectStrip(list(zip(self._aspect_labels, (r for _, r in ASPECTS))))
        lay.addWidget(self.aspect_strip)
        self.aspect_card.adjustSize()
        self.aspect_card.hide()
        self._aspect_fx = QGraphicsOpacityEffect(self.aspect_card)
        self.aspect_card.setGraphicsEffect(self._aspect_fx)
        self._aspect_anim = QPropertyAnimation(self._aspect_fx, b"opacity", self)
        self._aspect_anim.setDuration(140)
        self._aspect_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.btn_aspect.clicked.connect(lambda on: self._show_aspect_strip(on))
        self.aspect_strip.picked.connect(self._pick_aspect)
        self.ruler.pressed.connect(self._ruler_pressed)
        self.ruler.valueChanged.connect(self._ruler_changed)
        self.ruler.released.connect(self._ruler_released)
        self.btn_auto.clicked.connect(self._auto_straighten)
        self.btn_rot_left.clicked.connect(lambda: self._orient(lambda s: g.rotate90(s, False)))
        self.btn_rot_right.clicked.connect(lambda: self._orient(lambda s: g.rotate90(s, True)))
        self.btn_flip_h.clicked.connect(lambda: self._orient(lambda s: g.flip(s, True)))
        self.btn_flip_v.clicked.connect(lambda: self._orient(lambda s: g.flip(s, False)))

    def _build_panel(self):
        """Adjustment sliders in a full-height side panel on the right (Save sits at its top)."""
        self.panel = Card(self, radius=0, fill=QColor(22, 22, 25, 245))
        outer = QVBoxLayout(self.panel)
        self._panel_outer = outer
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setAutoFillBackground(False)
        scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        scroll.viewport().setStyleSheet("background: transparent;")
        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(14, 4, 14, 16)
        lay.setSpacing(6)
        self.sliders: dict[str, AdjustSlider] = {}
        for i, (title_key, names) in enumerate((("editor_group_light", LIGHT), ("editor_group_color", COLOR))):
            if i:
                lay.addSpacing(18)
            title = QLabel(self.tr_(title_key).upper())
            title.setObjectName("GroupTitle")
            title.setContentsMargins(8, 0, 0, 4)
            lay.addWidget(title)
            for name in names:
                s = AdjustSlider(name, self.tr_(f"editor_adj_{name}"))
                s.valueChanged.connect(self._slider_changed)
                s.committed.connect(self._slider_committed)
                self.sliders[name] = s
                lay.addWidget(s)
        lay.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self._panel_content = content

    def _layout_overlays(self):
        w, h = self.width(), self.height()
        self.stack.setGeometry(0, 0, w, h)
        self.rail.move(EDGE - 4, EDGE)
        self.actions.adjustSize()
        self.actions.move(w - self.actions.width() - EDGE, EDGE)
        self.crop_tools.adjustSize()
        tools_y = h - self.crop_tools.height() - EDGE
        self.crop_tools.move((w - self.crop_tools.width()) // 2, tools_y)
        self.aspect_card.adjustSize()
        self.aspect_card.move((w - self.aspect_card.width()) // 2, tools_y - self.aspect_card.height() - 8)
        top = EDGE + self.actions.height() + 8
        bottom = h - tools_y + 4
        # Edge-to-edge side panel; 1 px past the top/right/bottom so only its left border shows.
        self.panel.setGeometry(w - PANEL_W, -1, PANEL_W + 1, h + 2)
        self._panel_outer.setContentsMargins(0, top + 8, 1, 1)
        left = EDGE + self.rail.width() + 8
        self.crop_canvas.set_insets(left, top - 8, left, bottom)
        right = PANEL_W + EDGE if self._tab == "adjust" else left
        self.adjust_canvas.set_insets(left, top - 8, right, bottom)
        if self._tab == "adjust":  # centre the bottom row over the photo, not the whole window
            free = w - PANEL_W
            self.crop_tools.move((free - self.crop_tools.width()) // 2, tools_y)
        for overlay in (self.rail, self.panel, self.actions, self.crop_tools, self.aspect_card):
            overlay.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_overlays()

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
        if source != "ruler" or self.ruler.value() != state.crop.angle:
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
        if self._history.index < self._crop_session:
            self._crop_session = self._history.index  # undone past the session start
        # Done is only meaningful once this crop session changed something.
        self.btn_apply.setEnabled(self._state != self._history.state_at(self._crop_session))

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
        self.btn_aspect.setText(label)

    def _show_aspect_strip(self, show: bool):
        self.btn_aspect.setChecked(show)
        if show:
            self._layout_overlays()
            self._aspect_fx.setOpacity(0.0)
            self.aspect_card.show()
            self.aspect_card.raise_()
            self._aspect_anim.stop()
            self._aspect_anim.setStartValue(0.0)
            self._aspect_anim.setEndValue(1.0)
            self._aspect_anim.start()
        else:
            self.aspect_card.hide()

    def _pick_aspect(self, index: int):
        self._set_aspect(ASPECTS[index][1])
        QTimer.singleShot(120, lambda: self._show_aspect_strip(False))

    # ================================================================== previews
    def _request_previews(self):
        adj = self._state.adjust
        # The crop canvas's adjusted pyramid is only rebuilt while it is on screen; on the
        # Ajuste tab it would queue ahead of the preview the user is actually watching.
        if adj != self._shown_adjust and self._tab == "crop":
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
            # render exactly as many pixels as the canvas shows (capped by the proxy)
            scale = min(self._proxy_scale, self.adjust_canvas.display_scale(state.output_size))
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
        """``crop``, ``adjust``, or ``result`` (the finished photo after Done, no tool selected)."""
        crop = tab == "crop"
        if crop and self._tab != "crop":
            self._crop_session = self._history.index
        self._tab = tab
        self.tab_crop.setChecked(crop)
        self.tab_adjust.setChecked(tab == "adjust")
        self.stack.setCurrentWidget(self.crop_canvas if crop else self.adjust_canvas)
        self.crop_group.setVisible(crop)
        self.apply_group.setVisible(crop)
        if not crop:
            self._show_aspect_strip(False)
        self.panel.setVisible(tab == "adjust")
        self._layout_overlays()
        if not crop:
            self.adjust_canvas.fit()
        (self.crop_canvas if crop else self.adjust_canvas).setFocus()
        QTimer.singleShot(0, self._request_previews)  # canvas has its final size after layout

    def _apply_crop(self):
        """Done: accept the crop and show the finished photo.

        Everything done since the crop tool was opened becomes one undo step, so a
        single undo after Done brings the photo back to how it was before cropping.
        """
        if self._tab != "crop" or not self.btn_apply.isEnabled():
            return
        self._history.squash_since(self._crop_session)
        self._update_actions()
        self._switch_tab("result")

    def _zoom(self, factor: float):
        if self.stack.currentWidget() is self.crop_canvas:
            self.crop_canvas.zoom_by(factor)
        else:
            self.adjust_canvas.zoom_by(factor)
        self._flash_zoom()

    def _fit(self):
        if self.stack.currentWidget() is self.crop_canvas:
            self.crop_canvas.fit()
        else:
            self.adjust_canvas.fit()
        self._flash_zoom()

    def _on_zoom(self, z: float):
        if self.sender() is self.stack.currentWidget():
            self.zoom_label.setText(f"{round(z * 100)} %")

    def _flash_zoom(self):
        """Show the zoom level briefly after the user zooms; no permanent zoom chrome."""
        self.zoom_label.adjustSize()
        self.zoom_label.move((self.width() - self.zoom_label.width()) // 2, EDGE + 6)
        self.zoom_label.show()
        self.zoom_label.raise_()
        self._zoom_timer.start(1100)

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
        self._toast.move((self.width() - self._toast.width()) // 2, EDGE + 6)
        self._toast.show()
        self._toast.raise_()
        self._toast_timer.start(ms)

    # ================================================================== keyboard
    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if k == Qt.Key.Key_Escape and self.aspect_card.isVisible():
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
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._tab == "crop":
            self._apply_crop()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.btn_save.isEnabled():
            self.save_menu.open_under(self.btn_save)
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

    def mousePressEvent(self, e):
        if self.aspect_card.isVisible():
            self._show_aspect_strip(False)
        super().mousePressEvent(e)

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
                                ("ok", self.tr_("editor_overwrite_confirm"), "Primary"),
                                ("cancel", self.tr_("editor_cancel"), "Danger"),
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
                ("keep", self.tr_("editor_keep_editing"), "Primary"),
                ("discard", self.tr_("editor_discard"), "Danger"),
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


def _unique_copy(path: str) -> str:
    folder, filename = os.path.split(path)
    name, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, f"{name}_copy{ext}")
    n = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{name}_copy_{n}{ext}")
        n += 1
    return candidate

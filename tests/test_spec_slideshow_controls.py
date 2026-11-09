"""Executable form of docs/specs/SPEC-002-slideshow-controls.md (SC-1 .. SC-4)."""
import pytest
from PIL import Image
from PyQt6.QtCore import QEvent, QObject, QPointF, QStandardPaths, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings

REQUIRES = ["SC-1", "SC-2", "SC-3", "SC-4"]


class PaintCounter(QObject):
    def __init__(self):
        super().__init__()
        self.count = 0

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Paint:
            self.count += 1
        return False


@pytest.fixture
def player(qapp, tmp_path):
    QStandardPaths.setTestModeEnabled(True)
    paths = []
    for index in range(2):
        path = tmp_path / f"s{index}.jpg"
        Image.new("RGB", (800, 600), (60 + index * 50, 90, 140)).save(path)
        paths.append(str(path))
    win = PlayerWindow(paths, paths[0], SlideshowSettings(3, 100, False, True, False), raster=True)
    win.resize(900, 600)
    win.show()
    for _ in range(5):
        qapp.processEvents()
    win.controller.pause()
    win.reveal_controls()
    for _ in range(5):
        qapp.processEvents()
    yield win
    win.close()


def _move(widget):
    pos = QPointF(widget.rect().center())
    event = QMouseEvent(QEvent.Type.MouseMove, pos, widget.mapToGlobal(pos), Qt.MouseButton.NoButton,
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def test_sc1_mouse_move_with_visible_controls_repaints_nothing(player, qapp):
    """SC-1: moving the mouse while the bar is visible causes no repaint, only a timer restart."""
    assert not player.controls.isHidden()
    counter = PaintCounter()
    qapp.installEventFilter(counter)
    try:
        for _ in range(5):
            _move(player.surface.canvas)
            qapp.processEvents()
    finally:
        qapp.removeEventFilter(counter)
    assert counter.count == 0
    assert player.hide_timer.isActive()


def test_sc2_first_move_after_hide_reveals_once(player, qapp):
    """SC-2: after hiding, one movement shows the bar and arms the auto-hide timer."""
    player.controls.hide()
    player.hide_timer.stop()
    _move(player.surface.canvas)
    qapp.processEvents()
    assert not player.controls.isHidden()
    assert player.hide_timer.isActive()


def test_sc3_fullscreen_icon_only_set_when_mode_changes(player, qapp, monkeypatch):
    """SC-3: _update_fullscreen_control does not re-set the icon when the mode is unchanged."""
    player._update_fullscreen_control()
    calls = []
    original = player.buttons["fullscreen"].setIcon
    monkeypatch.setattr(player.buttons["fullscreen"], "setIcon", lambda icon: (calls.append(1), original(icon)))
    for _ in range(5):
        player._update_fullscreen_control()
    assert calls == []
    player.showFullScreen()
    qapp.processEvents()
    player._update_fullscreen_control()
    assert calls == [1]


def test_sc4_controls_reveal_again_after_auto_hide(player, qapp):
    """SC-4: after auto-hide the next movement reveals the controls again."""
    player.controller.pause()
    player.hide_timer.stop()
    player.controller.playing = True  # auto-hide only hides while playing
    player._hide_controls()
    qapp.processEvents()
    assert player.controls.isHidden()
    _move(player.surface.canvas)
    qapp.processEvents()
    assert not player.controls.isHidden()
    player.controller.playing = False

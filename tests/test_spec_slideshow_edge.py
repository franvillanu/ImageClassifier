"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, drawing-surface edge row (SG-1)."""
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths

from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings

REQUIRES = ["SG-1"]


def _wait(qapp, condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def player(qapp, tmp_path):
    QStandardPaths.setTestModeEnabled(True)
    path = tmp_path / "p.jpg"
    Image.new("RGB", (800, 400), (200, 60, 60)).save(path)
    win = PlayerWindow([str(path)], str(path), SlideshowSettings(30, 100, False, True, False), raster=True)
    yield win
    win.close()


def _is_whole(value):
    return abs(value - round(value)) < 1e-6


@pytest.mark.parametrize("dpr,size", [(1.5, (2559, 1439)), (1.5, (1001, 701)), (1.25, (1003, 702)), (1.0, (1001, 701))])
def test_sg1_surface_ends_on_a_whole_device_pixel(player, qapp, monkeypatch, dpr, size):
    """SG-1: at any window size and pixel ratio the surface's device size is whole and inside the window."""
    monkeypatch.setattr(player, "devicePixelRatioF", lambda: dpr)
    player.resize(*size)
    player.show()
    assert _wait(qapp, lambda: player.width() == size[0] and player.height() == size[1])
    qapp.processEvents()
    w, h = player.surface.width(), player.surface.height()
    assert _is_whole(w * dpr) and _is_whole(h * dpr)
    assert 0 <= size[0] - w < 4 and 0 <= size[1] - h < 4  # only the minimum is left uncovered
    if _is_whole(size[0] * dpr):
        assert w == size[0]  # nothing is given up when the window already ends on a whole pixel
    assert player.surface.geometry().topLeft().x() == 0 and player.surface.geometry().topLeft().y() == 0


def test_sg1_the_measured_fullscreen_case(player, qapp, monkeypatch):
    """SG-1: 3840x2160 @150% with the FS-7 border = 2559x1439 logical; the surface must stop at 2558x1438."""
    monkeypatch.setattr(player, "devicePixelRatioF", lambda: 1.5)
    player.resize(2559, 1439)
    player.show()
    assert _wait(qapp, lambda: player.width() == 2559)
    qapp.processEvents()
    assert (player.surface.width(), player.surface.height()) == (2558, 1438)

"""Executable form of docs/specs/SPEC-002-slideshow-controls.md, end of the show rows (SE-1 .. SE-3)."""
import time

import pytest
from PIL import Image
from PyQt6.QtCore import QStandardPaths

from image_classifier.slideshow.player import PlayerWindow
from image_classifier.slideshow.settings import SlideshowSettings

REQUIRES = ["SE-1", "SE-2", "SE-3"]


def _wait(qapp, condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def photos(tmp_path):
    paths = []
    for index in range(2):
        path = tmp_path / f"p{index}.jpg"
        Image.new("RGB", (800, 400), (200, 200, 200)).save(path)
        paths.append(str(path))
    return paths


@pytest.fixture
def player(qapp, photos):
    QStandardPaths.setTestModeEnabled(True)
    win = PlayerWindow(photos, photos[0], SlideshowSettings(600, 100, False, False, False), raster=True)
    win.resize(900, 600)
    win.show()
    assert _wait(qapp, lambda: win.surface.pixmap is not None and win.controller.entry is not None
                 and not win.controller._waiting)
    yield win
    win.close()


def _brightness(player, qapp):
    qapp.processEvents()
    image = player.surface.canvas.grab().toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2).red()


def _presented(player, qapp, path):
    return _wait(qapp, lambda: player.controller.entry.path == path and not player.controller._waiting
                 and player.surface.entry is not None and player.surface.entry.path == path)


def test_se3_playing_still_fades_in_at_the_start_of_a_slide(player, qapp):
    """SE-3: while playing, the very start of a slide is still transparent."""
    assert player.controller.playing
    assert _brightness(player, qapp) < 40


def test_se1_paused_photo_is_fully_visible(player, qapp):
    """SE-1: pausing at the start of a slide (opacity 0 in motion) shows the photo, not black."""
    player.controller.pause()
    assert _brightness(player, qapp) > 150


def test_se2_end_of_show_keeps_last_photo_and_previous_works(player, qapp, photos):
    """SE-2: Repeat off, time runs out on the last photo: it stays visible; Previous shows the other one."""
    player.controller.next()
    assert _presented(player, qapp, photos[1])
    player.controller.next()  # past the end: the show stops on the last photo
    assert not player.controller.playing and player.controller.progress == 1
    assert player.controller.entry.path == photos[1]
    assert _brightness(player, qapp) > 150
    player.controller.previous()
    assert _presented(player, qapp, photos[0])
    assert not player.controller.playing
    assert _brightness(player, qapp) > 150

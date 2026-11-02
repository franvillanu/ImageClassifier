"""Guards for the app.py split and the viewport multisampling setting."""
import importlib

import pytest
from PyQt6.QtGui import QSurfaceFormat

MOVED = {
    "image_classifier.ui.image_viewer": "AdvancedGraphicsImageViewer",
    "image_classifier.ui.viewport": "NearestViewport",
    "image_classifier.ui.crop_overlay": "CropOverlay",
    "image_classifier.ui.sharpness_overlay": "SharpnessOverlay",
}


@pytest.mark.parametrize("module,name", MOVED.items())
def test_moved_classes_live_in_their_module_and_app_still_exposes_them(module, name):
    cls = getattr(importlib.import_module(module), name)
    assert cls.__module__ == module
    if name != "NearestViewport":
        app_module = importlib.import_module("image_classifier.app")
        assert getattr(app_module, name) is cls


def test_app_defines_only_the_main_window():
    app_module = importlib.import_module("image_classifier.app")
    own = [
        n for n, v in vars(app_module).items()
        if isinstance(v, type) and v.__module__ == app_module.__name__
    ]
    assert own == ["PhotoViewer"]


def test_multisampling_is_off(qapp):
    from image_classifier.ui.viewport import VIEWPORT_SAMPLES, NearestViewport

    importlib.import_module("image_classifier.app")
    assert VIEWPORT_SAMPLES == 0
    assert QSurfaceFormat.defaultFormat().samples() <= 0
    assert NearestViewport().format().samples() <= 0

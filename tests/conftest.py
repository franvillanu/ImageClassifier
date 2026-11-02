"""Shared pytest fixtures for Qt-backed tests."""
import os

import pytest
from PyQt6.QtWidgets import QApplication


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# No GL context exists under the offscreen platform; without this PyOpenGL raises on
# glGetError inside the viewer's paintEvent and the app's excepthook blocks on a dialog.
os.environ.setdefault("PYOPENGL_ERROR_CHECKING", "0")


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app

"""Shared pytest fixtures for Qt-backed tests."""
import os

import pytest
from PyQt6.QtWidgets import QApplication


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app

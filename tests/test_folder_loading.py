"""Tests for selecting and dropping folders."""
import os
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QWidget

import image_classifier.app as app_module
from image_classifier.app import PhotoViewer
from image_classifier.ui.widgets import MyDragOverlay


class FakeMimeData:
    def __init__(self, paths):
        self._urls = [QUrl.fromLocalFile(str(path)) for path in paths]

    def hasUrls(self):
        return True

    def urls(self):
        return self._urls


class FakeDropEvent:
    def __init__(self, paths):
        self._mime_data = FakeMimeData(paths)
        self.accepted = False
        self.ignored = False

    def mimeData(self):
        return self._mime_data

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def test_drag_overlay_loads_dropped_folder(qapp, tmp_path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"test")

    parent = QWidget()
    loaded = []
    parent.load_directory_from_input = (
        lambda directory, selected_file=None: loaded.append(
            (directory, selected_file)
        )
    )
    overlay = MyDragOverlay(parent)
    event = FakeDropEvent([tmp_path])

    overlay.dropEvent(event)

    assert event.accepted
    assert len(loaded) == 1
    assert os.path.normpath(loaded[0][0]) == os.path.normpath(tmp_path)
    assert loaded[0][1] is None


def test_drag_overlay_preserves_dropped_image_selection(qapp, tmp_path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"test")

    parent = QWidget()
    loaded = []
    parent.load_directory_from_input = (
        lambda directory, selected_file=None: loaded.append(
            (directory, selected_file)
        )
    )
    overlay = MyDragOverlay(parent)
    event = FakeDropEvent([image])

    overlay.dropEvent(event)

    assert event.accepted
    assert len(loaded) == 1
    assert os.path.normpath(loaded[0][0]) == os.path.normpath(tmp_path)
    assert os.path.normpath(loaded[0][1]) == os.path.normpath(image)


def test_open_directory_uses_folder_picker(monkeypatch, tmp_path):
    calls = []

    class FakeFileDialog:
        class Option:
            ShowDirsOnly = object()

        @staticmethod
        def getExistingDirectory(parent, title, start_directory, options):
            calls.append((parent, title, start_directory, options))
            return str(tmp_path)

    viewer = type(
        "FakeViewer",
        (),
        {
            "current_language": "en",
            "current_directory": None,
            "load_directory_from_input": lambda self, directory: calls.append(
                directory
            ),
        },
    )()
    monkeypatch.setattr(app_module, "QFileDialog", FakeFileDialog)

    PhotoViewer.open_directory(viewer)

    assert calls[-1] == str(tmp_path)
    assert calls[0][1] == "Select Folder"


def test_load_directory_from_input_rejects_empty_folder(tmp_path):
    dialogs = []
    loaded = []
    viewer = type(
        "FakeViewer",
        (),
        {
            "current_language": "en",
            "show_custom_dialog": lambda self, message, **kwargs: dialogs.append(
                (message, kwargs)
            ),
            "load_directory": lambda self, directory, selected_file=None: loaded.append(
                (directory, selected_file)
            ),
        },
    )()

    result = PhotoViewer.load_directory_from_input(viewer, str(tmp_path))

    assert result is False
    assert not loaded
    assert dialogs[0][1]["icon_type"] == "warning"


def test_load_directory_from_input_loads_supported_images(tmp_path):
    image = Path(tmp_path) / "photo.webp"
    image.write_bytes(b"test")
    loaded = []
    viewer = type(
        "FakeViewer",
        (),
        {
            "current_language": "en",
            "show_custom_dialog": lambda self, *args, **kwargs: None,
            "load_directory": lambda self, directory, selected_file=None: loaded.append(
                (directory, selected_file)
            ),
        },
    )()

    result = PhotoViewer.load_directory_from_input(
        viewer,
        str(tmp_path),
        selected_file=str(image),
    )

    assert result is True
    assert loaded == [(str(tmp_path), str(image))]

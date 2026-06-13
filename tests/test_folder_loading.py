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
    parent.load_directory = (
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
    parent.load_directory = (
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


def test_open_directory_keeps_original_image_picker(monkeypatch, tmp_path):
    loaded = []
    image = tmp_path / "chosen.jpg"
    image.write_bytes(b"test")

    class FakeFileDialog:
        class FileMode:
            ExistingFiles = "existing-files"

        class ViewMode:
            List = "list"

        def __init__(self, parent, title):
            self.calls = [("init", parent, title)]

        def setFileMode(self, mode):
            self.calls.append(("file-mode", mode))

        def setNameFilter(self, name_filter):
            self.calls.append(("name-filter", name_filter))

        def setViewMode(self, view_mode):
            self.calls.append(("view-mode", view_mode))

        def setDirectory(self, directory):
            self.calls.append(("directory", directory))

        def exec(self):
            return True

        def selectedFiles(self):
            return [str(image)]

    viewer = type(
        "FakeViewer",
        (),
        {
            "current_language": "en",
            "current_directory": None,
            "show_custom_dialog": lambda self, *args, **kwargs: None,
            "load_directory": (
                lambda self, directory, selected_file=None: loaded.append(
                    (directory, selected_file)
                )
            ),
        },
    )()
    monkeypatch.setattr(app_module, "QFileDialog", FakeFileDialog)

    PhotoViewer.open_directory(viewer)

    assert loaded == [(str(tmp_path), str(image))]
    assert viewer.dialog.calls[0][2] == "Select Folder"
    assert (
        "file-mode",
        FakeFileDialog.FileMode.ExistingFiles,
    ) in viewer.dialog.calls
    assert (
        "view-mode",
        FakeFileDialog.ViewMode.List,
    ) in viewer.dialog.calls
    assert any(
        call[0] == "name-filter" and "*.jpg" in call[1]
        for call in viewer.dialog.calls
    )

"""Tests for selecting and dropping folders."""
import os
from pathlib import Path

from PyQt6.QtCore import QFileInfo, QSize, QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QWidget

import image_classifier.app as app_module
from image_classifier.app import PhotoViewer
from image_classifier.ui.widgets import ImageThumbnailIconProvider, MyDragOverlay


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
    loaded = []

    class FakeFileDialog:
        class FileMode:
            Directory = "directory"

        class Option:
            DontUseNativeDialog = "non-native"
            ShowDirsOnly = "show-dirs-only"

        class ViewMode:
            List = "list"

        def __init__(self, parent):
            self.parent = parent
            self.calls = []

        def setOption(self, option, enabled):
            self.calls.append(("option", option, enabled))

        def setWindowTitle(self, title):
            self.calls.append(("title", title))

        def setDirectory(self, directory):
            self.calls.append(("directory", directory))

        def setFileMode(self, mode):
            self.calls.append(("file-mode", mode))

        def setNameFilter(self, name_filter):
            self.calls.append(("name-filter", name_filter))

        def setIconProvider(self, provider):
            self.calls.append(("icon-provider", provider))

        def setViewMode(self, view_mode):
            self.calls.append(("view-mode", view_mode))

        def findChild(self, widget_type, object_name):
            self.calls.append(("find-child", widget_type, object_name))
            return None

        def exec(self):
            return True

        def selectedFiles(self):
            return [str(tmp_path)]

    viewer = type(
        "FakeViewer",
        (),
        {
            "current_language": "en",
            "current_directory": None,
            "load_directory_from_input": lambda self, directory: loaded.append(
                directory
            ),
        },
    )()
    monkeypatch.setattr(app_module, "QFileDialog", FakeFileDialog)

    PhotoViewer.open_directory(viewer)

    assert loaded == [str(tmp_path)]
    assert viewer.dialog.calls[0] == (
        "option",
        FakeFileDialog.Option.DontUseNativeDialog,
        True,
    )
    assert ("title", "Select Folder") in viewer.dialog.calls
    assert (
        "file-mode",
        FakeFileDialog.FileMode.Directory,
    ) in viewer.dialog.calls
    assert (
        "option",
        FakeFileDialog.Option.ShowDirsOnly,
        False,
    ) in viewer.dialog.calls
    assert any(
        call[0] == "name-filter" and "*.jpg" in call[1]
        for call in viewer.dialog.calls
    )
    assert any(
        call[0] == "icon-provider"
        and isinstance(call[1], ImageThumbnailIconProvider)
        for call in viewer.dialog.calls
    )
    assert (
        "view-mode",
        FakeFileDialog.ViewMode.List,
    ) in viewer.dialog.calls


def test_thumbnail_provider_returns_image_preview(qapp, tmp_path):
    path = tmp_path / "preview.png"
    image = QImage(320, 180, QImage.Format.Format_RGB32)
    image.fill(0xFF336699)
    assert image.save(str(path))

    provider = ImageThumbnailIconProvider(QSize(144, 108))
    icon = provider.icon(QFileInfo(str(path)))
    pixmap = icon.pixmap(QSize(144, 108))

    assert not pixmap.isNull()
    assert pixmap.width() == 144
    assert pixmap.height() == 81


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

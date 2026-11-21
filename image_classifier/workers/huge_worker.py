"""Background jobs for huge images (SPEC-007): the detail frame, and rotate-and-save."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage

from image_classifier.imaging import huge
from image_classifier.imaging.loader import (
    SOURCE_SIZE_KEY,
    ImageLoaderRunnable,
    image_source_size,
    to_display_format,
)


def pil_to_qimage(img) -> QImage:
    """RGB Pillow image -> QImage in the display format (conversion done off the GUI thread)."""
    data = img.tobytes("raw", "RGB")
    image = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
    return to_display_format(image.convertToFormat(QImage.Format.Format_RGB32))  # detaches from ``data``


class DetailSignals(QObject):
    progress = pyqtSignal(int)             # whole percent of the file read
    ready = pyqtSignal(object, object)     # QImage, (source_width, source_height)
    error = pyqtSignal(str)


class HugeDetailRunnable(QRunnable):
    """HI-4/HI-5: decode the detail frame; cached in memory and on disk like any other preview."""

    def __init__(self, image_path: str, max_dimension: int | None = None):
        super().__init__()
        self.image_path = ImageLoaderRunnable.normalize_path(image_path)
        self.max_dimension = max_dimension or huge.DETAIL_DIMENSION
        self.signals = DetailSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @pyqtSlot()
    def run(self):
        try:
            cached = ImageLoaderRunnable.get_cached_preview(self.image_path, self.max_dimension)
            if cached is None:
                cached = ImageLoaderRunnable._load_disk_preview(self.image_path, self.max_dimension)
            if cached is not None and image_source_size(cached) is not None:
                self.signals.progress.emit(100)
                self.signals.ready.emit(cached, image_source_size(cached))
                return
            img, source_size = huge.decode_reduced(
                self.image_path, self.max_dimension,
                progress=lambda fraction: self.signals.progress.emit(int(fraction * 100)),
                cancelled=lambda: self._cancelled,
            )
            image = pil_to_qimage(img)
            image.setText(SOURCE_SIZE_KEY, f"{source_size[0]},{source_size[1]}")
            ImageLoaderRunnable._preview_cache.put(
                ImageLoaderRunnable._preview_key(self.image_path, self.max_dimension), image)
            ImageLoaderRunnable._store_disk_preview(self.image_path, self.max_dimension, image)
            if not self._cancelled:
                self.signals.ready.emit(image, source_size)
        except huge.Cancelled:
            return
        except Exception as exc:  # HI-2: a worker never ends without a result
            if not self._cancelled:
                self.signals.error.emit(str(exc) or type(exc).__name__)


class HugeFileWorker(QThread):
    """Run ``job(progress, cancelled)`` on a file in the background (HI-6, HI-10), writing ``dst``."""

    progressChanged = pyqtSignal(str, int)   # stage ("read"/"rotate"/"render"/"write"), percent or -1 if unknown
    saved = pyqtSignal(str)
    failed = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, dst: str, job, parent=None):
        super().__init__(parent)
        self.dst = dst
        self._job = job
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        def progress(stage, fraction):
            self.progressChanged.emit(stage, -1 if fraction is None else int(fraction * 100))
        try:
            self._job(progress, lambda: self._cancel)
        except huge.Cancelled:
            self.canceled.emit()
        except Exception as exc:  # HI-2
            self.failed.emit(str(exc) or type(exc).__name__)
        else:
            self.saved.emit(self.dst)


class HugeRotateWorker(HugeFileWorker):
    """HI-6: rotate ``src`` by ``quarter_turns`` clockwise and write ``dst`` (may equal ``src``)."""

    def __init__(self, src: str, dst: str, quarter_turns: int, parent=None):
        super().__init__(dst, lambda progress, cancelled: huge.rotate_file(
            src, dst, quarter_turns, progress=progress, cancelled=cancelled), parent)


class HugeEditWorker(HugeFileWorker):
    """HI-10: render an editor ``EditState`` from ``src`` into ``dst`` (may equal ``src``)."""

    def __init__(self, src: str, dst: str, state, parent=None):
        super().__init__(dst, lambda progress, cancelled: huge.edit_file(
            src, dst, state, progress=progress, cancelled=cancelled), parent)

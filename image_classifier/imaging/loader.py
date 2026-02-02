"""Async image loader with shared LRU cache."""
from collections import OrderedDict
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QImageReader, QPixmap


class WorkerSignals(QObject):
    finished = pyqtSignal(QPixmap)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)


class ImageLoaderRunnable(QRunnable):
    _pixmap_cache = OrderedDict()
    _cache_limit = 10000

    def __init__(self, image_path: str, max_dimension: int = 4096):
        super().__init__()
        self.image_path = image_path
        self.max_dimension = max_dimension
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @pyqtSlot()
    def run(self):
        import time

        if self._cancelled:
            return

        cache = ImageLoaderRunnable._pixmap_cache

        if self.image_path in cache:
            pix = cache[self.image_path]
            cache.move_to_end(self.image_path)
            self.signals.finished.emit(pix)
            return

        reader = QImageReader(self.image_path)
        reader.setAutoTransform(True)
        reader.setAllocationLimit(512 * 1024 * 1024)

        img = reader.read()
        if img.isNull():
            self.signals.error.emit(f"Failed to read {self.image_path}")
            return
        qimg = img.convertToFormat(QImage.Format.Format_RGBA8888)
        pix = QPixmap.fromImage(qimg)

        cache[self.image_path] = pix
        if len(cache) > ImageLoaderRunnable._cache_limit:
            cache.popitem(last=False)

        self.signals.finished.emit(pix)

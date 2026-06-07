"""Async image loader with shared LRU cache."""
import os
from collections import OrderedDict

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QImageReader, QPixmap

register_heif_opener()


def _read_with_pillow(image_path: str) -> QImage:
    """Read formats unavailable to Qt, including HEIC/HEIF."""
    with Image.open(image_path) as pil_image:
        pil_image = ImageOps.exif_transpose(pil_image).convert("RGBA")
        data = pil_image.tobytes("raw", "RGBA")
        image = QImage(
            data,
            pil_image.width,
            pil_image.height,
            pil_image.width * 4,
            QImage.Format.Format_RGBA8888,
        )
        return image.copy()


def save_pixmap(pixmap: QPixmap, image_path: str) -> bool:
    """Save a pixmap, using Pillow for HEIC/HEIF output."""
    if os.path.splitext(image_path)[1].lower() not in (".heic", ".heif"):
        return pixmap.save(image_path)

    try:
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        bits = image.bits()
        bits.setsize(image.sizeInBytes())
        pil_image = Image.frombytes(
            "RGBA",
            (image.width(), image.height()),
            bytes(bits),
            "raw",
            "RGBA",
            image.bytesPerLine(),
        )
        pil_image.save(image_path, format="HEIF", quality=90)
        return True
    except (OSError, ValueError):
        return False


class WorkerSignals(QObject):
    finished = pyqtSignal(QPixmap)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)


class ImageLoaderRunnable(QRunnable):
    _pixmap_cache = OrderedDict()
    _pixmap_sizes = {}
    _cache_limit = 128
    _cache_bytes_limit = 512 * 1024 * 1024
    _cache_bytes = 0

    def __init__(self, image_path: str, max_dimension: int = 4096):
        super().__init__()
        self.image_path = self.normalize_path(image_path)
        self.max_dimension = max_dimension
        self.signals = WorkerSignals()
        self._cancelled = False

    @classmethod
    def normalize_path(cls, image_path: str) -> str:
        return os.path.normcase(os.path.abspath(image_path))

    @classmethod
    def get_cached_pixmap(cls, image_path: str):
        norm_path = cls.normalize_path(image_path)
        pix = cls._pixmap_cache.get(norm_path)
        if pix is None:
            return None
        cls._pixmap_cache.move_to_end(norm_path)
        return pix

    @classmethod
    def drop_cached_pixmap(cls, image_path: str):
        norm_path = cls.normalize_path(image_path)
        pix = cls._pixmap_cache.pop(norm_path, None)
        size = cls._pixmap_sizes.pop(norm_path, 0)
        cls._cache_bytes = max(0, cls._cache_bytes - size)
        return pix

    @classmethod
    def cache_pixmap(cls, image_path: str, pixmap: QPixmap, size_bytes: int):
        norm_path = cls.normalize_path(image_path)

        if norm_path in cls._pixmap_cache:
            cls.drop_cached_pixmap(norm_path)

        cls._pixmap_cache[norm_path] = pixmap
        cls._pixmap_sizes[norm_path] = size_bytes
        cls._cache_bytes += size_bytes
        cls._pixmap_cache.move_to_end(norm_path)

        while (
            len(cls._pixmap_cache) > cls._cache_limit
            or cls._cache_bytes > cls._cache_bytes_limit
        ):
            oldest_path, _ = cls._pixmap_cache.popitem(last=False)
            oldest_size = cls._pixmap_sizes.pop(oldest_path, 0)
            cls._cache_bytes = max(0, cls._cache_bytes - oldest_size)

    def cancel(self):
        self._cancelled = True

    @pyqtSlot()
    def run(self):
        if self._cancelled:
            return

        pix = ImageLoaderRunnable.get_cached_pixmap(self.image_path)
        if pix is not None:
            self.signals.finished.emit(pix)
            return

        reader = QImageReader(self.image_path)
        reader.setAutoTransform(True)
        reader.setAllocationLimit(512 * 1024 * 1024)

        img = reader.read()
        if img.isNull():
            try:
                img = _read_with_pillow(self.image_path)
            except (OSError, ValueError):
                self.signals.error.emit(f"Failed to read {self.image_path}")
                return
        qimg = img.convertToFormat(QImage.Format.Format_RGBA8888)
        pix = QPixmap.fromImage(qimg)

        ImageLoaderRunnable.cache_pixmap(self.image_path, pix, qimg.sizeInBytes())

        self.signals.finished.emit(pix)

"""Progressive image loading with bounded memory and disk preview caches."""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass

from PIL import Image, ImageOps
from PyQt6.QtCore import (
    QObject,
    QRunnable,
    QSize,
    QStandardPaths,
    Qt,
    QThread,
    QThreadPool,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QImage, QImageReader, QPixmap

HEIF_EXTENSIONS = (".heic", ".heif")
PREVIEW_CACHE_VERSION = 1
DEFAULT_PREVIEW_DIMENSION = 2048
MIN_PREVIEW_DIMENSION = 1024
MAX_PREVIEW_DIMENSION = 4096
PREVIEW_DIMENSION_STEP = 128

# Thread-pool priorities (higher runs first). The image on screen always wins; the
# next image in the travel direction comes before the full-resolution upgrade.
PRIORITY_CURRENT = 10
PRIORITY_PRELOAD_NEXT = 6
PRIORITY_FULL_RESOLUTION = 5
PRIORITY_PRELOAD_PREVIOUS = 4
PRIORITY_PRELOAD_AHEAD = 3

_heif_registered = False
_heif_lock = threading.Lock()


def _decode_thread_count() -> int:
    """Concurrent decodes: enough to overlap preloads, few enough to keep memory bounded."""
    return max(2, min(4, QThread.idealThreadCount() - 1))


def preview_dimension_for(width: float, height: float, device_pixel_ratio: float = 1.0) -> int:
    """Longest preview side that covers a viewport 1:1 in physical pixels.

    A photo fitted to the viewport is never drawn larger than the viewport's longest
    side, so decoding beyond that only costs time and memory. The value is rounded up
    to a fixed step so small window-size changes keep hitting the same cache entries.
    """
    longest = max(float(width), float(height)) * max(1.0, float(device_pixel_ratio or 1.0))
    stepped = int(math.ceil(longest / PREVIEW_DIMENSION_STEP)) * PREVIEW_DIMENSION_STEP
    return max(MIN_PREVIEW_DIMENSION, min(MAX_PREVIEW_DIMENSION, stepped))


def to_display_format(image: QImage) -> QImage:
    """Return ``image`` in QPixmap's native raster format.

    ``QPixmap.fromImage`` runs on the GUI thread. With a native-format image it is
    effectively free; with any other format (e.g. RGBA8888) it performs a full-frame
    conversion that freezes the UI for tens of milliseconds per photo. Converting here,
    on the worker thread, keeps that cost off the GUI thread.
    """
    if image.isNull():
        return image
    target = (
        QImage.Format.Format_ARGB32_Premultiplied
        if image.hasAlphaChannel()
        else QImage.Format.Format_RGB32
    )
    if image.format() == target:
        return image
    return image.convertToFormat(target)


class _LoadCancelled(Exception):
    """Raised inside a worker when its result is no longer wanted."""


def _ensure_heif_registered():
    global _heif_registered
    if _heif_registered:
        return
    with _heif_lock:
        if _heif_registered:
            return
        from pillow_heif import register_heif_opener

        register_heif_opener(decode_threads=4)
        _heif_registered = True


@dataclass(frozen=True)
class ImageFrame:
    """A decoded image frame safe to pass from a worker to the GUI thread."""

    path: str
    image: QImage
    full_resolution: bool


def _read_with_pillow(image_path: str) -> QImage:
    """Read formats unavailable to Qt, including HEIC/HEIF."""
    if os.path.splitext(image_path)[1].lower() in HEIF_EXTENSIONS:
        _ensure_heif_registered()
    with Image.open(image_path) as pil_image:
        pil_image = ImageOps.exif_transpose(pil_image)
        has_alpha = pil_image.mode in ("RGBA", "LA", "PA", "RGBa", "La") or (
            pil_image.mode == "P" and "transparency" in pil_image.info
        )
        if has_alpha:
            pil_image = pil_image.convert("RGBA")
            data = pil_image.tobytes("raw", "RGBA")
            image = QImage(
                data,
                pil_image.width,
                pil_image.height,
                pil_image.width * 4,
                QImage.Format.Format_RGBA8888,
            )
            # convertToFormat always allocates here (formats differ), detaching from ``data``.
            return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        pil_image = pil_image.convert("RGB")
        data = pil_image.tobytes("raw", "RGB")
        image = QImage(
            data,
            pil_image.width,
            pil_image.height,
            pil_image.width * 3,
            QImage.Format.Format_RGB888,
        )
        return image.convertToFormat(QImage.Format.Format_RGB32)


def save_pixmap(pixmap: QPixmap, image_path: str) -> bool:
    """Save a pixmap, using Pillow for HEIC/HEIF output."""
    if os.path.splitext(image_path)[1].lower() not in HEIF_EXTENSIONS:
        return pixmap.save(image_path)

    try:
        _ensure_heif_registered()
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
    previewReady = pyqtSignal(object)
    fullReady = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)


class _ImageCache:
    """Thread-safe, byte-bounded QImage LRU cache."""

    def __init__(self, byte_limit: int):
        self.byte_limit = byte_limit
        self._items = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

    def get(self, key):
        with self._lock:
            image = self._items.get(key)
            if image is None:
                return None
            self._items.move_to_end(key)
            return image

    def put(self, key, image: QImage):
        size = image.sizeInBytes()
        with self._lock:
            previous = self._items.pop(key, None)
            if previous is not None:
                self._bytes -= previous.sizeInBytes()
            self._items[key] = image
            self._bytes += size
            while self._items and self._bytes > self.byte_limit:
                _, evicted = self._items.popitem(last=False)
                self._bytes -= evicted.sizeInBytes()

    def drop_path(self, normalized_path: str):
        with self._lock:
            stale = [
                key for key in self._items
                if key == normalized_path
                or (isinstance(key, tuple) and key[0] == normalized_path)
            ]
            for key in stale:
                image = self._items.pop(key)
                self._bytes -= image.sizeInBytes()

    def clear(self):
        with self._lock:
            self._items.clear()
            self._bytes = 0


class ImageLoaderRunnable(QRunnable):
    """Load a full image, preserving the legacy single-result API."""

    _pixmap_cache = OrderedDict()
    _pixmap_sizes = {}
    _cache_limit = 128
    _cache_bytes_limit = 512 * 1024 * 1024
    _cache_bytes = 0
    _full_cache = _ImageCache(_cache_bytes_limit)
    # Screen-sized previews are ~9 MB at 1080p and ~38 MB at 4K; 256 MB keeps the
    # current photo, the preload window and recent history resident on either.
    _preview_cache = _ImageCache(256 * 1024 * 1024)
    _cache_lock = threading.RLock()
    _native_decode_slots = threading.Semaphore(_decode_thread_count())
    _heif_decode_slots = threading.Semaphore(1)
    _disk_cache_limit = 1024 * 1024 * 1024
    _disk_cache_enabled = True
    _disk_cache_estimate = None
    _disk_cache_lock = threading.Lock()
    _thread_pool = None

    def __init__(
        self,
        image_path: str,
        max_dimension: int = DEFAULT_PREVIEW_DIMENSION,
        *,
        progressive: bool = False,
        load_full: bool = True,
        load_preview: bool = True,
    ):
        super().__init__()
        self.image_path = self.normalize_path(image_path)
        self.max_dimension = max(256, int(max_dimension))
        self.progressive = progressive
        self.load_full = load_full
        self.load_preview = load_preview
        self.signals = WorkerSignals()
        self._cancelled = False

    @classmethod
    def thread_pool(cls) -> QThreadPool:
        """Dedicated decode pool.

        Sized to the number of decode slots so queued work waits in the pool's
        priority queue (where the on-screen image can overtake preloads) instead of
        blocking on a semaphore in arrival order.
        """
        if cls._thread_pool is None:
            pool = QThreadPool()
            pool.setMaxThreadCount(_decode_thread_count())
            pool.setExpiryTimeout(30000)
            cls._thread_pool = pool
        return cls._thread_pool

    def start(self, priority: int = 0):
        """Queue this loader on the decode pool."""
        self.thread_pool().start(self, priority)

    @classmethod
    def normalize_path(cls, image_path: str) -> str:
        return os.path.normcase(os.path.abspath(image_path))

    @classmethod
    def configure_disk_cache(cls, *, enabled: bool, limit_mb: int):
        cls._disk_cache_enabled = bool(enabled)
        cls._disk_cache_limit = max(64, int(limit_mb)) * 1024 * 1024

    @classmethod
    def _memory_source_key(cls, image_path: str):
        normalized = cls.normalize_path(image_path)
        try:
            stat = os.stat(normalized)
            return (normalized, stat.st_size, stat.st_mtime_ns)
        except OSError:
            return (normalized, 0, 0)

    @classmethod
    def _preview_key(cls, image_path: str, max_dimension: int):
        return (*cls._memory_source_key(image_path), int(max_dimension))

    @classmethod
    def get_cached_preview(cls, image_path: str, max_dimension: int):
        return cls._preview_cache.get(cls._preview_key(image_path, max_dimension))

    @classmethod
    def seed_preview(cls, image_path: str, max_dimension: int, image: QImage) -> bool:
        """Store an already decoded frame as ``image_path``'s preview for ``max_dimension``.

        Used when the slideshow closes so the classifier shows the same photo at once
        (SPEC-002 SX-3). Larger frames are scaled down to the preview size; smaller ones are kept
        as they are (the photo itself is that small)."""
        if image is None or image.isNull() or max_dimension <= 0:
            return False
        if max(image.width(), image.height()) > max_dimension:
            image = image.scaled(max_dimension, max_dimension, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        cls._preview_cache.put(cls._preview_key(cls.normalize_path(image_path), max_dimension), image)
        return True

    @classmethod
    def get_cached_image(cls, image_path: str):
        return cls._full_cache.get(cls._memory_source_key(image_path))

    @classmethod
    def get_cached_pixmap(cls, image_path: str):
        image = cls.get_cached_image(image_path)
        if image is None:
            return None
        return QPixmap.fromImage(image)

    @classmethod
    def drop_cached_pixmap(cls, image_path: str):
        norm_path = cls.normalize_path(image_path)
        cls._full_cache.drop_path(norm_path)
        cls._preview_cache.drop_path(norm_path)
        with cls._cache_lock:
            pix = cls._pixmap_cache.pop(norm_path, None)
            size = cls._pixmap_sizes.pop(norm_path, 0)
            cls._cache_bytes = max(0, cls._cache_bytes - size)
        return pix

    @classmethod
    def cache_pixmap(cls, image_path: str, pixmap: QPixmap, size_bytes: int):
        """Compatibility helper used by existing tests and save paths."""
        norm_path = cls.normalize_path(image_path)
        image = pixmap.toImage()
        cls._full_cache.put(cls._memory_source_key(norm_path), image)
        with cls._cache_lock:
            if norm_path in cls._pixmap_cache:
                cls.drop_cached_pixmap(norm_path)
            cls._pixmap_cache[norm_path] = pixmap
            cls._pixmap_sizes[norm_path] = size_bytes
            cls._cache_bytes += size_bytes
            while (
                len(cls._pixmap_cache) > cls._cache_limit
                or cls._cache_bytes > cls._cache_bytes_limit
            ):
                oldest_path, _ = cls._pixmap_cache.popitem(last=False)
                oldest_size = cls._pixmap_sizes.pop(oldest_path, 0)
                cls._cache_bytes = max(0, cls._cache_bytes - oldest_size)

    @classmethod
    def _disk_cache_dir(cls):
        root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        )
        path = os.path.join(root, "preview-cache-v1")
        os.makedirs(path, exist_ok=True)
        return path

    @classmethod
    def _source_signature(cls, image_path: str):
        stat = os.stat(image_path)
        value = json.dumps(
            [
                PREVIEW_CACHE_VERSION,
                cls.normalize_path(image_path),
                stat.st_size,
                stat.st_mtime_ns,
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _disk_preview_path(cls, image_path: str, max_dimension: int):
        signature = cls._source_signature(image_path)
        return os.path.join(
            cls._disk_cache_dir(),
            f"{signature}-{int(max_dimension)}.jpg",
        )

    @classmethod
    def _load_disk_preview(cls, image_path: str, max_dimension: int):
        if not cls._disk_cache_enabled:
            return None
        try:
            cache_path = cls._disk_preview_path(image_path, max_dimension)
            image = QImage(cache_path)
            if image.isNull():
                return None
            try:
                os.utime(cache_path, None)
            except OSError:
                pass
            return image
        except OSError:
            return None

    @classmethod
    def _store_disk_preview(
        cls,
        image_path: str,
        max_dimension: int,
        image: QImage,
    ):
        if not cls._disk_cache_enabled or image.isNull():
            return
        try:
            cache_path = cls._disk_preview_path(image_path, max_dimension)
            temp_path = cache_path + ".tmp"
            if image.save(temp_path, "JPG", 88):
                os.replace(temp_path, cache_path)
                written = os.path.getsize(cache_path)
                # Only rescan the folder when the running estimate crosses the limit.
                with cls._disk_cache_lock:
                    if cls._disk_cache_estimate is None:
                        needs_scan = True
                    else:
                        cls._disk_cache_estimate += written
                        needs_scan = cls._disk_cache_estimate > cls._disk_cache_limit
                if needs_scan:
                    cls._prune_disk_cache()
        except OSError:
            return

    @classmethod
    def _prune_disk_cache(cls):
        try:
            entries = []
            total = 0
            with os.scandir(cls._disk_cache_dir()) as scanner:
                for entry in scanner:
                    if not entry.is_file() or not entry.name.endswith(".jpg"):
                        continue
                    stat = entry.stat()
                    total += stat.st_size
                    entries.append((stat.st_atime_ns, stat.st_size, entry.path))
            if total <= cls._disk_cache_limit:
                with cls._disk_cache_lock:
                    cls._disk_cache_estimate = total
                return
            entries.sort()
            target = int(cls._disk_cache_limit * 0.9)
            for _, size, path in entries:
                try:
                    os.remove(path)
                    total -= size
                except OSError:
                    pass
                if total <= target:
                    break
            with cls._disk_cache_lock:
                cls._disk_cache_estimate = total
        except OSError:
            return

    @classmethod
    def clear_disk_cache(cls):
        try:
            with os.scandir(cls._disk_cache_dir()) as scanner:
                for entry in scanner:
                    if entry.is_file():
                        try:
                            os.remove(entry.path)
                        except OSError:
                            pass
        except OSError:
            pass
        with cls._disk_cache_lock:
            cls._disk_cache_estimate = None

    @classmethod
    def disk_cache_size(cls):
        total = 0
        try:
            with os.scandir(cls._disk_cache_dir()) as scanner:
                for entry in scanner:
                    if entry.is_file():
                        total += entry.stat().st_size
        except OSError:
            pass
        return total

    def cancel(self):
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def _raise_if_cancelled(self):
        if self._cancelled:
            raise _LoadCancelled()

    def _scaled_preview(self, image: QImage):
        if max(image.width(), image.height()) <= self.max_dimension:
            return image
        return image.scaled(
            QSize(self.max_dimension, self.max_dimension),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _read_qt_preview(self):
        """Decode a screen-sized frame.

        Returns ``(image, is_full)``; ``is_full`` is True when the source already fits
        the preview size, so the decoded frame *is* the full-resolution image.
        """
        with self._native_decode_slots:
            self._raise_if_cancelled()
            reader = QImageReader(self.image_path)
            reader.setAutoTransform(True)
            reader.setAllocationLimit(512)
            size = reader.size()
            scaled = False
            if size.isValid() and max(size.width(), size.height()) > self.max_dimension:
                size.scale(
                    self.max_dimension,
                    self.max_dimension,
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
                reader.setScaledSize(size)
                scaled = True
            return reader.read(), not scaled

    def _read_full(self):
        with self._native_decode_slots:
            self._raise_if_cancelled()
            reader = QImageReader(self.image_path)
            reader.setAutoTransform(True)
            reader.setAllocationLimit(512)
            image = reader.read()
        if not image.isNull():
            return image
        return _read_with_pillow(self.image_path)

    def _emit_preview(self, image: QImage):
        image = to_display_format(image)
        self._preview_cache.put(
            self._preview_key(self.image_path, self.max_dimension),
            image,
        )
        self.signals.previewReady.emit(
            ImageFrame(self.image_path, image, full_resolution=False)
        )

    def _emit_full(self, image: QImage):
        image = to_display_format(image)
        self._full_cache.put(self._memory_source_key(self.image_path), image)
        frame = ImageFrame(self.image_path, image, full_resolution=True)
        self.signals.fullReady.emit(frame)
        if not self.progressive:
            self.signals.finished.emit(QPixmap.fromImage(image))

    @pyqtSlot()
    def run(self):
        if self._cancelled:
            return
        try:
            self._run()
        except _LoadCancelled:
            return

    def _run(self):
        full = self.get_cached_image(self.image_path)
        if full is not None:
            if self.progressive and self.load_preview:
                preview = self._scaled_preview(full)
                self._emit_preview(preview)
            if self.load_full:
                self._emit_full(full)
            return

        if not self.progressive:
            try:
                self._emit_full(self._read_full())
            except (OSError, ValueError, SyntaxError, RuntimeError, EOFError):
                self.signals.error.emit(f"Failed to read {self.image_path}")
            return

        preview = None
        if self.load_preview:
            preview = self.get_cached_preview(self.image_path, self.max_dimension)
            if preview is None:
                preview = self._load_disk_preview(self.image_path, self.max_dimension)
            if preview is not None:
                self._emit_preview(preview)
                if not self.load_full:
                    return

        extension = os.path.splitext(self.image_path)[1].lower()
        try:
            if extension in HEIF_EXTENSIONS:
                # pillow-heif cannot perform a reduced decode. Decode once, derive the
                # preview, then retain the same full frame for the quality upgrade.
                with self._heif_decode_slots:
                    self._raise_if_cancelled()
                    full = to_display_format(self._read_full())
                if not self.load_full:
                    # Keep the expensive decode so the later upgrade is a cache hit.
                    self._full_cache.put(self._memory_source_key(self.image_path), full)
                if self.load_preview and preview is None and not self._cancelled:
                    preview = self._scaled_preview(full)
                    self._emit_preview(preview)
                    self._store_disk_preview(
                        self.image_path,
                        self.max_dimension,
                        preview,
                    )
                if self.load_full and not self._cancelled:
                    self._emit_full(full)
                return

            if self.load_preview and preview is None:
                preview, is_full = self._read_qt_preview()
                if preview.isNull():
                    raise OSError("preview decode failed")
                if self._cancelled:
                    return
                if is_full:
                    # Source fits the screen: this decode is the full image.
                    self._emit_full(preview)
                    return
                self._emit_preview(preview)
                self._store_disk_preview(
                    self.image_path,
                    self.max_dimension,
                    preview,
                )

            if self.load_full and not self._cancelled:
                full = self._read_full()
                if not self._cancelled:
                    self._emit_full(full)
        except (OSError, ValueError, SyntaxError, RuntimeError, EOFError):
            if not self._cancelled:
                self.signals.error.emit(f"Failed to read {self.image_path}")

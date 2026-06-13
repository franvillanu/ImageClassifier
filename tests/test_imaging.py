"""Tests for imaging (sharpen, loader)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pillow_heif import register_heif_opener
from PyQt6.QtGui import QPixmap, QImage
from image_classifier.imaging.sharpen import sharpen_cv2
from image_classifier.imaging.loader import (
    ImageFrame,
    ImageLoaderRunnable,
    WorkerSignals,
    _read_with_pillow,
    save_pixmap,
)
from image_classifier.ui.widgets import ALLOWED_EXTENSIONS

register_heif_opener()


def test_sharpen_returns_pixmap(qapp):
    """sharpen_cv2 returns a QPixmap of same size."""
    img = QImage(100, 80, QImage.Format.Format_RGBA8888)
    img.fill(0xFF808080)
    pix = QPixmap.fromImage(img)
    out = sharpen_cv2(pix, radius=1, amount=0.5)
    assert not out.isNull()
    assert out.width() == 100
    assert out.height() == 80


def test_worker_signals_exists(qapp):
    sig = WorkerSignals()
    assert hasattr(sig, "finished")
    assert hasattr(sig, "error")
    assert hasattr(sig, "progress")


def test_loader_cache_attributes():
    assert hasattr(ImageLoaderRunnable, "_pixmap_cache")
    assert hasattr(ImageLoaderRunnable, "_cache_limit")
    assert ImageLoaderRunnable._cache_limit > 0
    assert hasattr(ImageLoaderRunnable, "_cache_bytes_limit")
    assert ImageLoaderRunnable._cache_bytes_limit > 0
    assert callable(ImageLoaderRunnable.get_cached_pixmap)
    assert callable(ImageLoaderRunnable.drop_cached_pixmap)


def test_progressive_loader_emits_preview_then_full(qapp, tmp_path):
    source = QImage(2400, 1600, QImage.Format.Format_RGB32)
    source.fill(0xFF336699)
    path = tmp_path / "large.jpg"
    assert source.save(str(path), "JPG", 90)

    ImageLoaderRunnable.drop_cached_pixmap(str(path))
    worker = ImageLoaderRunnable(
        str(path),
        max_dimension=800,
        progressive=True,
        load_full=True,
    )
    frames = []
    worker.signals.previewReady.connect(frames.append)
    worker.signals.fullReady.connect(frames.append)

    worker.run()

    assert len(frames) == 2
    assert all(isinstance(frame, ImageFrame) for frame in frames)
    assert frames[0].full_resolution is False
    assert max(frames[0].image.width(), frames[0].image.height()) <= 800
    assert frames[1].full_resolution is True
    assert frames[1].image.size() == source.size()


def test_progressive_heic_decodes_full_frame_once(qapp, tmp_path, monkeypatch):
    source = QImage(1200, 800, QImage.Format.Format_RGBA8888)
    source.fill(0xFF884422)
    path = tmp_path / "large.heic"
    assert save_pixmap(QPixmap.fromImage(source), str(path))

    ImageLoaderRunnable.drop_cached_pixmap(str(path))
    ImageLoaderRunnable.configure_disk_cache(enabled=False, limit_mb=64)
    worker = ImageLoaderRunnable(
        str(path),
        max_dimension=400,
        progressive=True,
        load_full=True,
    )
    original_read_full = worker._read_full
    calls = []

    def counted_read_full():
        calls.append(True)
        return original_read_full()

    monkeypatch.setattr(worker, "_read_full", counted_read_full)
    frames = []
    worker.signals.previewReady.connect(frames.append)
    worker.signals.fullReady.connect(frames.append)

    worker.run()

    assert len(calls) == 1
    assert [frame.full_resolution for frame in frames] == [False, True]
    ImageLoaderRunnable.configure_disk_cache(enabled=True, limit_mb=1024)


def test_memory_cache_invalidates_when_source_changes(qapp, tmp_path):
    path = tmp_path / "changing.png"
    first = QImage(20, 10, QImage.Format.Format_RGB32)
    first.fill(0xFF112233)
    assert first.save(str(path), "PNG")

    ImageLoaderRunnable.drop_cached_pixmap(str(path))
    worker = ImageLoaderRunnable(str(path))
    worker.run()
    cached_first = ImageLoaderRunnable.get_cached_image(str(path))
    assert cached_first is not None
    assert cached_first.size() == first.size()

    second = QImage(30, 15, QImage.Format.Format_RGB32)
    second.fill(0xFF445566)
    assert second.save(str(path), "PNG")

    assert ImageLoaderRunnable.get_cached_image(str(path)) is None


def test_heic_extensions_are_allowed():
    assert ".heic" in ALLOWED_EXTENSIONS
    assert ".heif" in ALLOWED_EXTENSIONS


def test_heic_round_trip(qapp, tmp_path):
    source = QImage(24, 16, QImage.Format.Format_RGBA8888)
    source.fill(0xFF336699)
    path = tmp_path / "iphone-photo.heic"

    assert save_pixmap(QPixmap.fromImage(source), str(path))

    loaded = _read_with_pillow(str(path))
    assert not loaded.isNull()
    assert loaded.size() == source.size()

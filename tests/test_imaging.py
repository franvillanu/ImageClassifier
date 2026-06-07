"""Tests for imaging (sharpen, loader)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pillow_heif import register_heif_opener
from PyQt6.QtGui import QPixmap, QImage
from image_classifier.imaging.sharpen import sharpen_cv2
from image_classifier.imaging.loader import (
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

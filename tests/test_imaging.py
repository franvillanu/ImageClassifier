"""Tests for imaging (sharpen, loader)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtGui import QPixmap, QImage
from image_classifier.imaging.sharpen import sharpen_cv2
from image_classifier.imaging.loader import ImageLoaderRunnable, WorkerSignals


def test_sharpen_returns_pixmap():
    """sharpen_cv2 returns a QPixmap of same size."""
    img = QImage(100, 80, QImage.Format.Format_RGBA8888)
    img.fill(0xFF808080)
    pix = QPixmap.fromImage(img)
    out = sharpen_cv2(pix, radius=1, amount=0.5)
    assert not out.isNull()
    assert out.width() == 100
    assert out.height() == 80


def test_worker_signals_exists():
    sig = WorkerSignals()
    assert hasattr(sig, "finished")
    assert hasattr(sig, "error")
    assert hasattr(sig, "progress")


def test_loader_cache_attributes():
    assert hasattr(ImageLoaderRunnable, "_pixmap_cache")
    assert hasattr(ImageLoaderRunnable, "_cache_limit")
    assert ImageLoaderRunnable._cache_limit == 10000

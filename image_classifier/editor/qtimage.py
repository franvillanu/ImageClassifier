"""QImage <-> numpy conversion (RGBA8888, always copying)."""
from __future__ import annotations

import numpy as np
from PyQt6.QtGui import QImage


def qimage_to_rgba(image: QImage) -> np.ndarray:
    img = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine())
    return arr[:, : w * 4].reshape(h, w, 4).copy()


def rgba_to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.ndim == 3 and arr.shape[2] == 3:
        return QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
    return QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()

"""LAB unsharp mask via OpenCV."""
import cv2
import numpy as np
from PyQt6.QtGui import QPixmap, QImage


def sharpen_cv2(pixmap: QPixmap, radius: int, amount: float, threshold: int = 2) -> QPixmap:
    qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    ptr = qimg.bits()
    ptr.setsize(w * h * 4)
    arr = np.frombuffer(ptr, np.uint8).reshape(h, w, 4)

    bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    Lf = L.astype(np.float32)

    def blur_L(Lf, r):
        k = max(1, 2 * r + 1)
        return cv2.GaussianBlur(Lf, (k, k), sigmaX=r)

    blur1 = blur_L(Lf, radius)
    blur2 = blur_L(Lf, radius * 2)
    diff1 = Lf - blur1
    diff2 = Lf - blur2

    if threshold > 0:
        m1 = np.abs(diff1)
        m2 = np.abs(diff2)
        mask1 = (m1.max(axis=2 if m1.ndim == 3 else 1) if m1.ndim == 3 else m1) >= threshold
        mask2 = (m2.max(axis=2 if m2.ndim == 3 else 1) if m2.ndim == 3 else m2) >= threshold
        diff1[~mask1] = 0
        diff2[~mask2] = 0

    L_new = Lf + amount * diff1 + (amount * 0.5) * diff2
    L_clipped = np.clip(L_new, 0, 255).astype(np.uint8)
    lab_new = cv2.merge([L_clipped, A, B])
    bgr_new = cv2.cvtColor(lab_new, cv2.COLOR_LAB2BGR)
    rgba = cv2.cvtColor(bgr_new, cv2.COLOR_BGR2RGBA)
    qimg2 = QImage(rgba.data, w, h, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg2.copy())

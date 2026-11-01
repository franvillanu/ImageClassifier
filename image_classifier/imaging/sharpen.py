"""LAB unsharp mask via OpenCV."""
from PyQt6.QtGui import QPixmap, QImage


def sharpen_array(rgb, radius: float, amount: float, threshold: int = 2):
    """Sharpen an RGB uint8 array (H, W, 3) on the LAB lightness channel only."""
    import cv2
    import numpy as np

    lab = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2LAB)
    L, A, B = cv2.split(lab)
    Lf = L.astype(np.float32)

    def blur_L(Lf, r):
        k = max(1, 2 * int(np.ceil(r)) + 1)
        return cv2.GaussianBlur(Lf, (k, k), sigmaX=r)

    diff1 = Lf - blur_L(Lf, radius)
    diff2 = Lf - blur_L(Lf, radius * 2)

    if threshold > 0:
        diff1[np.abs(diff1) < threshold] = 0
        diff2[np.abs(diff2) < threshold] = 0

    L_new = Lf + amount * diff1 + (amount * 0.5) * diff2
    L_clipped = np.clip(L_new, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge([L_clipped, A, B]), cv2.COLOR_LAB2RGB)


def sharpen_qimage(
    image: QImage,
    radius: int,
    amount: float,
    threshold: int = 2,
) -> QImage:
    import numpy as np

    qimg = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    ptr = qimg.bits()
    ptr.setsize(qimg.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, qimg.bytesPerLine())[:, : w * 4].reshape(h, w, 4)

    rgba = arr.copy()
    rgba[..., :3] = sharpen_array(arr[..., :3], radius, amount, threshold)
    qimg2 = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return qimg2.copy()


def sharpen_cv2(
    pixmap: QPixmap,
    radius: int,
    amount: float,
    threshold: int = 2,
) -> QPixmap:
    return QPixmap.fromImage(
        sharpen_qimage(pixmap.toImage(), radius, amount, threshold)
    )

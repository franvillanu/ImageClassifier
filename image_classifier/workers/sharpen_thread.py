"""Background sharpen (LAB unsharp) via OpenCV."""
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from image_classifier.imaging.sharpen import sharpen_qimage


class SharpenThread(QThread):
    progressChanged = pyqtSignal(int)
    finished = pyqtSignal(object)
    errorOccurred = pyqtSignal(str)

    def __init__(self, orig: QPixmap, radius: int, amount: float, parent=None):
        super().__init__(parent)
        self.orig = orig.toImage()
        self.radius = radius
        self.amount = amount
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            result = sharpen_qimage(self.orig, self.radius, self.amount)
            if self._cancel:
                return
            self.finished.emit(result)
        except Exception as e:
            self.errorOccurred.emit(str(e))

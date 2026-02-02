"""Delete non-favorites (send to recycle bin)."""
import os
import send2trash
from PyQt6.QtCore import QObject, QCoreApplication, pyqtSignal


class DeleteNonFavoritesWorker(QObject):
    progressChanged = pyqtSignal(int)
    finished = pyqtSignal(int)
    errorOccurred = pyqtSignal(str)

    def __init__(self, images_to_delete):
        super().__init__()
        self.images = list(images_to_delete)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        count = 0
        total = len(self.images)
        for i, image in enumerate(self.images):
            if self._cancelled:
                self.finished.emit(count)
                return
            if os.path.exists(image):
                try:
                    send2trash.send2trash(image)
                    count += 1
                except Exception as e:
                    self.errorOccurred.emit(str(e))
                    self.finished.emit(count)
                    return
            progress = int(((i + 1) / total) * 100)
            self.progressChanged.emit(progress)
            QCoreApplication.processEvents()
        self.finished.emit(count)

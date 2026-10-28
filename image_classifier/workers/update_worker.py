"""Background workers for the in-app updater."""
from PyQt6.QtCore import QObject, pyqtSignal

from image_classifier.updates.check import check_for_update
from image_classifier.updates.download import DownloadCancelled, download_installer


class UpdateCheckWorker(QObject):
    finished = pyqtSignal(object)

    def run(self):
        try:
            result = check_for_update()
        except Exception:
            result = {"state": "failed"}
        self.finished.emit(result)


class UpdateDownloadWorker(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, offer):
        super().__init__()
        self.offer = offer
        self._cancelled = False

    def cancel(self):
        # Called directly from the GUI thread; the download loop polls this flag.
        self._cancelled = True

    def run(self):
        try:
            path = download_installer(
                self.offer,
                on_progress=self.progress.emit,
                is_cancelled=lambda: self._cancelled,
            )
        except DownloadCancelled:
            self.failed.emit("")
            return
        except Exception as exc:
            self.failed.emit(str(exc) or "error")
            return
        self.finished.emit(path)

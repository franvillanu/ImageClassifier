"""Export favorites to a folder."""
import os
from PyQt6.QtCore import QObject, QCoreApplication, pyqtSignal


class ExportWorker(QObject):
    progressChanged = pyqtSignal(int)
    finished = pyqtSignal(int)
    errorOccurred = pyqtSignal(str)

    def __init__(self, favorites, export_dir, norm_dict):
        super().__init__()
        self.favorites = list(favorites)
        self.export_dir = export_dir
        self.norm_dict = norm_dict
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def copy_file_with_cancel(self, src, dest, chunk_size=1 * 1024 * 1024):
        try:
            with open(src, "rb") as fsrc, open(dest, "wb") as fdst:
                while True:
                    if self._cancelled:
                        fdst.close()
                        if os.path.exists(dest):
                            os.remove(dest)
                        return False
                    chunk = fsrc.read(chunk_size)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    QCoreApplication.processEvents()
            return True
        except Exception as e:
            self.errorOccurred.emit(str(e))
            return False

    def run(self):
        count = 0
        total = len(self.favorites)
        for i, fav_path in enumerate(self.favorites):
            if self._cancelled:
                self.finished.emit(count)
                return
            if os.path.exists(fav_path):
                original_path = self.norm_dict.get(fav_path, fav_path)
                basename = os.path.basename(original_path)
                dest = os.path.join(self.export_dir, basename)
                if not self.copy_file_with_cancel(fav_path, dest):
                    self.finished.emit(count)
                    return
                count += 1
            progress = int(((i + 1) / total) * 100)
            self.progressChanged.emit(progress)
        self.finished.emit(count)

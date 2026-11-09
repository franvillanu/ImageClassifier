"""Player-owned coordination around the application's bounded asynchronous loader."""
from collections import OrderedDict
import os
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from image_classifier.imaging.loader import ImageLoaderRunnable, PRIORITY_CURRENT, PRIORITY_PRELOAD_NEXT


class SlideLoader(QObject):
    ready = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dimension = 2048
        self._jobs = {}
        self._frames = OrderedDict()
        self._closed = False

    def request(self, path, token, current=True):
        if self._closed:
            return
        try:
            source = os.stat(path)
        except OSError:
            # Still use the shared worker for failure delivery. Emitting inline
            # would recursively navigate a large playlist of removed files.
            source = None
        key = (path, self.dimension, source.st_mtime_ns if source else None, source.st_size if source else None)
        frame = self._frames.get(key)
        if frame is not None:
            self._frames.move_to_end(key)
            self.ready.emit(token, frame)
            return
        worker = ImageLoaderRunnable(path, self.dimension, progressive=True, load_full=False)
        self._jobs[worker.signals] = (worker, token, key)
        worker.signals.previewReady.connect(self._ready)
        # The shared loader emits fullReady directly when the source already
        # fits the requested preview size, even for a preview-only request.
        worker.signals.fullReady.connect(self._ready)
        worker.signals.error.connect(self._failed)
        worker.start(PRIORITY_CURRENT if current else PRIORITY_PRELOAD_NEXT)

    @pyqtSlot(object)
    def _ready(self, frame):
        job = self._jobs.pop(self.sender(), None)
        if self._closed or job is None:
            return
        _, token, key = job
        self._frames[key] = frame
        while len(self._frames) > 3:
            self._frames.popitem(last=False)
        self.ready.emit(token, frame)

    @pyqtSlot(str)
    def _failed(self, message):
        job = self._jobs.pop(self.sender(), None)
        if not self._closed and job is not None:
            self.failed.emit(job[1], job[2][0])

    def cancel_pending(self):
        for worker, _, _ in self._jobs.values():
            worker.cancel()
        self._jobs.clear()

    def close(self):
        self._closed = True
        self.cancel_pending()
        self._frames.clear()

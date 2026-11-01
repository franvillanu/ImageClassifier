"""Background rendering with latest-wins coalescing.

The GUI submits jobs as fast as sliders move; the worker only ever renders the
newest pending job and tags results with a generation number so the GUI can
drop anything stale. numpy/OpenCV release the GIL, so the GUI stays fluid.
"""
from __future__ import annotations

import traceback
from typing import Callable

from PyQt6.QtCore import QMutex, QMutexLocker, QThread, QWaitCondition, pyqtSignal


class PreviewWorker(QThread):
    ready = pyqtSignal(object, int, str)  # result, generation, channel
    failed = pyqtSignal(str, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._pending: dict[str, tuple[int, Callable[[], object]]] = {}
        self._stop = False
        self._generation = 0

    def submit(self, channel: str, job: Callable[[], object]) -> int:
        """Queue ``job`` on ``channel``, replacing any job still pending there."""
        with QMutexLocker(self._mutex):
            self._generation += 1
            gen = self._generation
            self._pending[channel] = (gen, job)
            self._cond.wakeOne()
        if not self.isRunning():
            self.start()
        return gen

    def latest(self) -> int:
        with QMutexLocker(self._mutex):
            return self._generation

    def stop(self):
        with QMutexLocker(self._mutex):
            self._stop = True
            self._pending.clear()
            self._cond.wakeOne()
        self.wait(5000)

    def run(self):
        while True:
            self._mutex.lock()
            while not self._pending and not self._stop:
                self._cond.wait(self._mutex)
            if self._stop:
                self._mutex.unlock()
                return
            channel, (gen, job) = next(iter(self._pending.items()))
            del self._pending[channel]
            self._mutex.unlock()
            try:
                result = job()
            except Exception:  # surfaced to the GUI, never kills the thread
                self.failed.emit(traceback.format_exc(), gen, channel)
                continue
            self.ready.emit(result, gen, channel)

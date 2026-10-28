"""Update state machine shared by the banner and the app (the URL never leaves here)."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from image_classifier.updates.check import UpdateOffer
from image_classifier.updates.install import launch_installer
from image_classifier.workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker

ANSWER_MS = 4000

IDLE = "idle"
CHECKING = "checking"
AVAILABLE = "available"
DOWNLOADING = "downloading"
READY = "ready"
FAILED = "failed"
CURRENT = "current"
UNREACHABLE = "unreachable"


class UpdateController(QObject):
    phase_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, int)  # bytes received, total (0 = unknown)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase = IDLE
        self.version: Optional[str] = None
        self.size: Optional[int] = None
        self._offer: Optional[UpdateOffer] = None
        self._installer_path: Optional[str] = None
        self._thread: Optional[QThread] = None
        self._worker = None

    # -- state -------------------------------------------------------------
    def _set_phase(self, phase: str):
        self.phase = phase
        self.phase_changed.emit(phase)
        if phase in (CURRENT, UNREACHABLE):
            QTimer.singleShot(ANSWER_MS, lambda p=phase: self._expire(p))

    def _expire(self, phase: str):
        if self.phase == phase:
            self._set_phase(IDLE)

    def notes_text(self, lang: str) -> Optional[str]:
        """Release notes of the offered version in `lang`, if the release carries them."""
        if self._offer is None:
            return None
        return (self._offer.notes_es if lang == "es" else self._offer.notes_en) or self._offer.notes_en

    def is_busy(self) -> bool:
        return self.phase in (CHECKING, DOWNLOADING)

    # -- thread plumbing -----------------------------------------------------
    def _run(self, worker):
        self._worker = worker
        self._thread = QThread()
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        self._thread.start()

    def _stop_thread(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None

    # -- check -----------------------------------------------------------------
    def check(self, manual: bool = False):
        if self.is_busy() or self.phase in (AVAILABLE, READY):
            return
        if manual:
            self._set_phase(CHECKING)
        else:
            self.phase = CHECKING  # silent: no UI change unless an update exists
        worker = UpdateCheckWorker()
        worker.finished.connect(lambda result, m=manual: self._on_checked(result, m))
        self._run(worker)

    def _on_checked(self, result: dict, manual: bool):
        self._stop_thread()
        state = result.get("state")
        if state == "available":
            self._offer = result["offer"]
            self.version = self._offer.version
            self.size = self._offer.size
            self._installer_path = None
            self._set_phase(AVAILABLE)
        elif manual:
            self._set_phase(CURRENT if state == "current" else UNREACHABLE)
        else:
            self.phase = IDLE

    # -- download ----------------------------------------------------------------
    def download(self):
        if self._offer is None or self.phase == DOWNLOADING:
            return
        self._set_phase(DOWNLOADING)
        self.progress_changed.emit(0, self.size or 0)
        worker = UpdateDownloadWorker(self._offer)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_downloaded)
        worker.failed.connect(self._on_failed)
        self._run(worker)

    def _on_progress(self, got: int, total: int):
        if total and not self.size:
            self.size = total
        self.progress_changed.emit(got, total)

    def _on_downloaded(self, path: str):
        self._stop_thread()
        self._installer_path = path
        self._set_phase(READY)

    def _on_failed(self, reason: str):
        self._stop_thread()
        # An empty reason means the user cancelled: go back to the offer.
        self._set_phase(AVAILABLE if not reason else FAILED)

    def cancel(self):
        if self.phase == DOWNLOADING and self._worker is not None:
            self._worker.cancel()

    # -- install -----------------------------------------------------------------
    def install(self, lang: str = "en") -> bool:
        """Start the installer. True means the caller should now close the app."""
        if self.phase != READY or not self._installer_path:
            return False
        return launch_installer(self._installer_path, lang)

    def dismiss(self):
        if self.phase in (AVAILABLE, READY, FAILED):
            self._set_phase(IDLE)

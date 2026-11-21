"""Progress dialog + callbacks for a background job on a huge file (SPEC-007 HI-6, HI-10)."""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from image_classifier.i18n.translations import translations
from image_classifier.ui.dialogs import OverlayProgressDialog


class HugeJob(QObject):
    """Shows the stage and a real percentage while ``worker`` runs; Cancel stops it until it starts writing.

    Exactly one of ``on_saved(path)``, ``on_failed(message)``, ``on_canceled()`` is called, after the dialog
    is closed; ``done`` is emitted once the thread has ended.
    """

    done = pyqtSignal()

    def __init__(self, parent, worker, language, on_saved, on_failed, on_canceled):
        super().__init__(parent)
        self._t = {**translations["en"], **translations.get(language, {})}
        self.worker = worker
        self.dialog = OverlayProgressDialog(
            self._t["huge_save_title"], self._t["huge_stage_read"].format(pct=0), parent=parent)
        self.dialog.cancelButton.setText(self._t["cancel"])
        self.dialog.setValue(0)
        self.dialog.cancelButton.clicked.connect(worker.cancel)
        worker.progressChanged.connect(self.on_progress)
        worker.saved.connect(lambda path: (self._close_dialog(), on_saved(path)))
        worker.failed.connect(lambda message: (self._close_dialog(), on_failed(message)))
        worker.canceled.connect(lambda: (self._close_dialog(), on_canceled()))
        worker.finished.connect(self._on_thread_finished)

    def start(self):
        self.dialog.show()
        self.dialog.raise_()
        self.worker.start()

    def cancel_and_wait(self, timeout_ms=15000):
        """For window close: a QThread must not be destroyed while running."""
        self.worker.cancel()
        self.worker.wait(timeout_ms)

    def on_progress(self, stage, percent):
        dialog = self.dialog
        if dialog is None:
            return
        t = self._t
        text = (t["huge_stage_read"].format(pct=percent) if stage == "read"
                else t["huge_stage_render"].format(pct=percent) if stage == "render"
                else t["huge_stage_rotate"] if stage == "rotate" else t["huge_stage_write"])
        dialog.messageLabel.setText(text)
        bar = dialog.progressBar
        if percent >= 0:
            bar.setRange(0, 100)
            bar.setValue(percent)
        else:
            bar.setRange(0, 0)  # animated: no percentage exists for this stage, so none is shown
        if stage == "write":
            dialog.cancelButton.setEnabled(False)  # the atomic replace cannot be interrupted
        dialog.container.adjustSize()
        dialog.container.move((dialog.width() - dialog.container.width()) // 2,
                              (dialog.height() - dialog.container.height()) // 2)

    def _close_dialog(self):
        if self.dialog is not None:
            self.dialog.hide()
            self.dialog.deleteLater()
            self.dialog = None

    def _on_thread_finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.done.emit()

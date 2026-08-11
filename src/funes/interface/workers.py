"""Worker objects for long-running interface tasks."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class Worker(QObject):
    """Base class for Qt workers."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


class ServiceWorker(Worker):
    """Run a synchronous service call on a Qt worker thread."""

    def __init__(self, call: Callable[[], Any]) -> None:
        super().__init__()
        self._call = call

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._call()
        except Exception as exc:  # pragma: no cover - exercised through Qt signals
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)

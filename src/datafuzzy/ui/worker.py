"""Run a function on Qt's thread pool and get the result back on the UI thread."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # surfaced to the user, not swallowed
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.done.emit(result)


def run_task(fn: Callable[[], object], on_done: Callable[[object], None],
             on_failed: Callable[[str], None]) -> Task:
    task = Task(fn)
    task.signals.done.connect(on_done)
    task.signals.failed.connect(on_failed)
    QThreadPool.globalInstance().start(task)
    return task

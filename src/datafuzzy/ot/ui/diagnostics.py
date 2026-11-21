"""A local log of why the app stopped: uncaught errors, hard crashes, Qt warnings, and which code
closed a window or quit. Only code locations and error messages are written, never a chart; the
file stays on this computer (see log_path)."""

from __future__ import annotations

import faulthandler
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import TextIO

from platformdirs import user_log_path
from PySide6.QtCore import QEvent, QObject, QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QWidget

from .. import APP_NAME

KEEP_BYTES = 1_000_000  # a longer log is started over at launch


def log_path() -> Path:
    return user_log_path(APP_NAME) / f"{APP_NAME.lower()}.log"


class Diagnostics(QObject):
    """Writes to `path` until the app ends; installed by start_diagnostics."""

    def __init__(self, app: QApplication, path: Path) -> None:
        super().__init__(app)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > KEEP_BYTES:
            path.unlink()
        self.path = path
        self.file: TextIO = path.open("a", encoding="utf-8", buffering=1)
        faulthandler.enable(self.file, all_threads=True)
        self._excepthook = sys.excepthook
        sys.excepthook = self._uncaught
        self._qt_handler = qInstallMessageHandler(self._qt_message)
        app.installEventFilter(self)
        app.lastWindowClosed.connect(lambda: self.write("last window closed", stack=True))
        app.aboutToQuit.connect(lambda: self.write("quitting", stack=True))
        self.write(f"started {APP_NAME} {app.applicationVersion()}")

    def stop(self) -> None:
        """Put back what start_diagnostics replaced (for tests; the app logs until it ends)."""
        QApplication.instance().removeEventFilter(self)
        sys.excepthook = self._excepthook
        qInstallMessageHandler(self._qt_handler)
        faulthandler.disable()
        self.file.close()

    def write(self, what: str, stack: bool = False) -> None:
        self.file.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {what}\n")
        if stack:
            self.file.write("".join(traceback.format_stack()[:-1]))

    def _uncaught(self, kind, error, tb) -> None:
        self.write("uncaught error:\n" + "".join(traceback.format_exception(kind, error, tb)))
        self._excepthook(kind, error, tb)

    def _qt_message(self, kind: QtMsgType, context, message: str) -> None:
        if kind != QtMsgType.QtDebugMsg:
            self.write(f"Qt {kind.name}: {message}")
        if sys.stderr:
            sys.stderr.write(message + "\n")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (event.type() == QEvent.Type.Close and isinstance(watched, QWidget) and watched.isWindow()
                and not watched.inherits("QMenu")):
            self.write(f"window closed: {type(watched).__name__}"
                       f" ({'by the system' if event.spontaneous() else 'by the app'})", stack=True)
        return False


def start_diagnostics(app: QApplication, path: Path | None = None) -> Diagnostics | None:
    """Start logging, or None if the log cannot be written (the app runs on without it)."""
    try:
        return Diagnostics(app, path or log_path())
    except OSError:
        return None

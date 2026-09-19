"""Entry point: `uv run datafuzzy` or `python -m datafuzzy`."""

from __future__ import annotations

import atexit
import signal
import sys


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .core.pipeline import Pipeline
    from .core.store import SessionStore, sweep_stale
    from .ui.main_window import MainWindow

    sweep_stale()
    store = SessionStore()
    atexit.register(store.cleanup)

    app = QApplication(sys.argv)
    app.setApplicationName("DataFuzzy")
    app.aboutToQuit.connect(store.cleanup)

    # Qt's event loop blocks Python signal handlers; a periodic no-op timer lets them run,
    # so SIGINT/SIGTERM go through a normal quit (and cleanup) instead of killing us.
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(250)

    window = MainWindow(Pipeline(), store)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

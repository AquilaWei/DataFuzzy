"""Entry point: `uv run datafuzzy` or `python -m datafuzzy`."""

from __future__ import annotations

import atexit
import signal
import sys


def main() -> int:
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication

    from .core.models import is_installed, load_manifest, models_dir
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

    specs = load_manifest()
    root = models_dir()
    pipeline = Pipeline()
    pipeline.load_models(specs, root)
    window = MainWindow(pipeline, store, specs, root)
    window.show()

    # First launch without any model: offer the download once.
    settings = QSettings("DataFuzzy", "DataFuzzy")
    if not any(is_installed(s, root) for s in specs) and not settings.value("models/prompted", False, bool):
        settings.setValue("models/prompted", True)
        QTimer.singleShot(0, window.open_model_manager)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

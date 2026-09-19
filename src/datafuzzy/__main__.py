"""Entry point: `uv run datafuzzy` or `python -m datafuzzy`."""

from __future__ import annotations

import atexit
import os
import signal
import sys


def self_test() -> int:
    """Headless smoke check for packaged builds: every runtime piece loads and a text
    round-trips. With DATAFUZZY_REQUIRE_MODEL set, every model must be installed and used."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import ssl

    import certifi
    from PySide6.QtWidgets import QApplication

    from . import __version__
    from .core.models import load_manifest, models_dir
    from .core.pipeline import Pipeline
    from .core.store import SessionStore
    from .ui.main_window import MainWindow

    ssl.create_default_context(cafile=certifi.where())  # model downloads need the CA bundle
    app = QApplication([])
    specs, root = load_manifest(), models_dir()
    pipeline = Pipeline()
    pipeline.load_models(specs, root)
    store = SessionStore()
    try:
        MainWindow(pipeline, store, specs, root)
        session = store.new_session()
        text = "請 John Smith 跟王小明確認，信寄到 alice@acme.com。"
        result = pipeline.obfuscate(text, session)
        assert "alice@acme.com" not in result.text, result.text
        assert pipeline.restore(result.text, session).text == text
        if os.environ.get("DATAFUZZY_REQUIRE_MODEL"):
            assert pipeline.pii is not None
            assert sorted(pipeline.models) == sorted(s.lang for s in specs if s.kind == "ner"), pipeline.models
            for name in ("John Smith", "王小明"):
                assert name not in result.text, result.text
        loaded = [d.name for d in (pipeline.pii, *pipeline.models.values()) if d]
        print(f"DataFuzzy {__version__} self-test OK; models: {loaded}; "
              f"{result.text}")
    finally:
        store.cleanup()
        app.quit()
    return 0


def main() -> int:
    if "--version" in sys.argv[1:]:
        from . import __version__
        print(f"DataFuzzy {__version__}")
        return 0
    if "--self-test" in sys.argv[1:]:
        return self_test()

    from importlib.resources import files

    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtGui import QIcon
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
    app.setWindowIcon(QIcon(str(files("datafuzzy").joinpath("icon.png"))))
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

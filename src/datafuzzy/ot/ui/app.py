"""TheraNote's entry point: `uv run theranote` (also `datafuzzy`) or `python -m datafuzzy.ot.ui.app`.

The window opens only after the key is obtained: until then no chart is read, and a cancelled
or failed unlock ends the app with a message.
"""

from __future__ import annotations

import importlib
import os
import signal
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from ... import __version__
from ...core.models import ModelSpec, is_installed, load_manifest, models_dir
from ...core.pipeline import Pipeline
from ...core.store import sweep_stale
from ...ui.worker import run_task
from .. import APP_NAME
from ..crypto import DecryptionError
from ..db import RecordStore, default_db_path
from ..keys import KeyProvider, UnlockCancelled, UnlockError, default_provider
from .main_window import TheraNoteWindow
from .theme import apply_theme
from .unlock import PasswordPrompter

ProviderFactory = Callable[[Path, Callable[[bool, bool], str | None]], KeyProvider]

CANCELLED_TEXT = f"已取消解鎖。資料沒有被讀取，{APP_NAME} 將關閉。"
FAILED_TEXT = "無法解鎖：{reason}\n資料沒有被讀取，" + APP_NAME + " 將關閉。"
MISMATCH_TEXT = (f"取得的金鑰打不開這個資料庫（{{path}}）。\n可能是鑰匙圈被重設，或密碼不是當初設定的那組。"
                 f"資料沒有被改動，{APP_NAME} 將關閉。")


def unlock_key(path: Path, provider_factory: ProviderFactory,
               ask_password: Callable[[bool, bool], str | None]) -> tuple[str, object]:
    """Get the database key, on a worker thread. Returns ("key", bytes), ("cancelled", reason)
    or ("failed", reason); anything unexpected is raised."""
    try:
        return "key", provider_factory(path, ask_password).get_key()
    except UnlockCancelled as e:
        return "cancelled", str(e)
    except UnlockError as e:
        return "failed", str(e)


def show_warning(title: str, text: str) -> None:
    QMessageBox.warning(None, title, text)


class Launcher(QObject):
    """Unlocks, then opens the main window. `outcome` ends as "ok", "cancelled", "failed" or
    "mismatch"; for anything but "ok" the app is told to exit and no window is made."""

    def __init__(self, app: QApplication, pipeline: Pipeline, specs: list[ModelSpec], models_root: Path,
                 db_path: Path | None = None, provider_factory: ProviderFactory = default_provider,
                 prompter: PasswordPrompter | None = None,
                 show_message: Callable[[str, str], None] = show_warning,
                 exit_app: Callable[[int], None] | None = None, offer_models: bool = True) -> None:
        super().__init__(app)
        self.pipeline = pipeline
        self.specs = specs
        self.models_root = models_root
        self.db_path = db_path or default_db_path()
        self.provider_factory = provider_factory
        self.prompter = prompter or PasswordPrompter()
        self.show_message = show_message
        self.exit_app = exit_app or app.exit
        self.offer_models = offer_models
        self.outcome = ""
        self.store: RecordStore | None = None
        self.window: TheraNoteWindow | None = None
        self._task = None

    def start(self) -> None:
        # Off the GUI thread: the system may ask the user to authenticate, and may block.
        self._task = run_task(
            lambda: unlock_key(self.db_path, self.provider_factory, self.prompter.ask),
            self._unlocked, lambda message: self._stop("failed", FAILED_TEXT.format(reason=message)))

    def _unlocked(self, result: tuple[str, object]) -> None:
        kind, value = result
        if kind == "cancelled":
            self._stop("cancelled", CANCELLED_TEXT)
        elif kind == "failed":
            self._stop("failed", FAILED_TEXT.format(reason=value))
        else:
            self._open(value)

    def _open(self, key: bytes) -> None:
        try:
            self.store = RecordStore(self.db_path, key)
        except DecryptionError:
            self._stop("mismatch", MISMATCH_TEXT.format(path=self.db_path))
            return
        self.window = TheraNoteWindow(self.store, self.pipeline, self.specs, self.models_root)
        self.window.show()
        self.outcome = "ok"
        if self.offer_models:
            self._offer_models()

    def _offer_models(self) -> None:
        """First launch without any model: offer the download once."""
        settings = QSettings(APP_NAME, APP_NAME)
        if (not any(is_installed(s, self.models_root) for s in self.specs)
                and not settings.value("models/prompted", False, bool)):
            settings.setValue("models/prompted", True)
            QTimer.singleShot(0, self.window.open_model_manager)

    def _stop(self, outcome: str, message: str) -> None:
        self.outcome = outcome
        self.show_message(APP_NAME, message)
        self.exit_app(1)

    def shutdown(self) -> None:
        """Save pending edits and close the database (on quit)."""
        if self.window is not None:
            self.window.flush()
        if self.store is not None:
            self.store.close()
            self.store = None


def self_test() -> int:
    """Headless smoke check for packaged builds: the interface builds, the key libraries for
    this platform are bundled, and a chart exports and comes back with the name restored.
    With DATAFUZZY_REQUIRE_MODEL set, the detection models must be installed and used."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from ..exchange import apply_import, export_range, preview_import

    bundled = ["keyring", "keyring.backends.macOS", "LocalAuthentication"] if sys.platform == "darwin" else [
        "keyring", "keyring.backends.SecretService", "secretstorage", "jeepney"]
    for name in bundled:
        importlib.import_module(name)

    app = QApplication([])
    apply_theme(app)
    specs, root = load_manifest(), models_dir()
    pipeline = Pipeline()
    pipeline.load_models(specs, root)
    with tempfile.TemporaryDirectory() as tmp, RecordStore(Path(tmp) / "selftest.db", os.urandom(32)) as store:
        window = TheraNoteWindow(store, pipeline, specs, root)
        student_id = window.add_student("王小明")
        window.new_record(student_id, date(2026, 10, 1))
        window.editor.zh_edit.setPlainText("請 John Smith 跟王小明確認，信寄到 alice@acme.com。")
        window.flush()
        text = export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline).text
        assert "王小明" not in text, text
        preview = preview_import(store, text)
        assert apply_import(store, preview) == 1
        assert store.get_record(1).en_text.startswith("請"), store.get_record(1).en_text
        if os.environ.get("DATAFUZZY_REQUIRE_MODEL"):
            assert pipeline.pii is not None
            assert "John Smith" not in text, text
        print(f"{APP_NAME} {__version__} self-test OK; bundled: {bundled}; {text.strip()}")
    app.quit()
    return 0


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"{APP_NAME} {__version__}")
        return 0
    if "--self-test" in sys.argv[1:]:
        return self_test()

    sweep_stale()  # temp folders left by crashed DataFuzzy runs
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(files("datafuzzy").joinpath("icon.png"))))
    apply_theme(app)

    # Qt's event loop blocks Python signal handlers; a periodic no-op timer lets them run,
    # so SIGINT/SIGTERM go through a normal quit (and save pending edits) instead of killing us.
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(250)

    specs = load_manifest()
    root = models_dir()
    pipeline = Pipeline()
    pipeline.load_models(specs, root)
    launcher = Launcher(app, pipeline, specs, root)
    app.aboutToQuit.connect(launcher.shutdown)
    QTimer.singleShot(0, launcher.start)  # once the event loop runs, so a dialog can be shown
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

"""The real app must delete its code files when it is closed or terminated."""

import os
import signal
import subprocess
import sys
import time

import pytest

SCRIPT = """
import sys, tempfile
from pathlib import Path
from PySide6.QtCore import QTimer
import datafuzzy.core.store as store_mod

base = Path(sys.argv[1])
store_mod.tempfile.gettempdir = lambda: str(base)
orig_init = store_mod.SessionStore.__init__

def init(self, _base=None):
    orig_init(self, base)
    self.new_session()           # create a code file on disk
    print("READY", flush=True)

store_mod.SessionStore.__init__ = init
if sys.argv[2] == "quit":
    # Simulate the user closing the window once it is shown.
    import datafuzzy.ui.main_window as mw
    orig_show = mw.MainWindow.show

    def show(self):
        orig_show(self)
        QTimer.singleShot(500, self.close)

    mw.MainWindow.show = show
from datafuzzy.__main__ import main
sys.exit(main())
"""


def run_app(tmp_path, how):
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    proc = subprocess.Popen([sys.executable, "-c", SCRIPT, str(tmp_path), how],
                            stdout=subprocess.PIPE, text=True, env=env)
    assert proc.stdout.readline().strip() == "READY"
    session_dir = tmp_path / f"datafuzzy-{proc.pid}"
    assert list(session_dir.glob("*.dfmap"))
    return proc, session_dir


@pytest.mark.parametrize("how", ["quit", "sigterm", "sigint"])
def test_files_removed_on_exit(tmp_path, how):
    proc, session_dir = run_app(tmp_path, how)
    if how != "quit":
        time.sleep(0.5)
        proc.send_signal(signal.SIGTERM if how == "sigterm" else signal.SIGINT)
    assert proc.wait(timeout=10) == 0
    assert not session_dir.exists()


def test_kill9_leftovers_swept_on_next_start(tmp_path):
    proc, session_dir = run_app(tmp_path, "sigterm")
    proc.kill()
    proc.wait(timeout=10)
    assert session_dir.exists()  # SIGKILL can't be handled...

    proc2, _ = run_app(tmp_path, "quit")  # ...but the next launch sweeps it
    assert proc2.wait(timeout=10) == 0
    assert not session_dir.exists()


def test_version_and_self_test_flags(tmp_path):
    """The packaged builds are smoke-tested with these flags in the release workflow."""
    from datafuzzy import __version__

    env = {**os.environ, "DATAFUZZY_MODELS_DIR": str(tmp_path), "DATAFUZZY_REQUIRE_MODEL": ""}

    def run(flag):
        return subprocess.run([sys.executable, "-m", "datafuzzy", flag], env=env,
                              capture_output=True, text=True, check=True).stdout

    assert run("--version").strip() == f"DataFuzzy {__version__}"
    out = run("--self-test")
    assert "self-test OK" in out and "[EMAIL_A]" in out

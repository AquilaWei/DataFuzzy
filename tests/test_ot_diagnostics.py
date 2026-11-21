import sys

from PySide6.QtCore import qWarning
from PySide6.QtWidgets import QApplication, QWidget

from datafuzzy.ot.ui.diagnostics import KEEP_BYTES, start_diagnostics


def test_log_names_the_code_that_closed_a_window(qtbot, tmp_path):
    log = tmp_path / "logs" / "t.log"
    diagnostics = start_diagnostics(QApplication.instance(), log)
    try:
        window = QWidget()
        qtbot.addWidget(window)
        window.show()
        window.close()
        qWarning("something odd")
        text = log.read_text()
        assert "window closed: QWidget (by the app)" in text
        assert "test_log_names_the_code_that_closed_a_window" in text
        assert "Qt QtWarningMsg: something odd" in text
    finally:
        diagnostics.stop()


def test_uncaught_error_is_logged(qtbot, tmp_path):
    log = tmp_path / "t.log"
    diagnostics = start_diagnostics(QApplication.instance(), log)
    try:
        diagnostics._excepthook = lambda *_: None  # pytest-qt's own hook would fail the test
        try:
            raise ValueError("boom")
        except ValueError:
            diagnostics._uncaught(*sys.exc_info())
        assert "ValueError: boom" in log.read_text()
    finally:
        diagnostics.stop()


def test_a_long_log_starts_over(qtbot, tmp_path):
    log = tmp_path / "t.log"
    log.write_text("x" * (KEEP_BYTES + 1))
    diagnostics = start_diagnostics(QApplication.instance(), log)
    try:
        assert log.stat().st_size < 200
    finally:
        diagnostics.stop()

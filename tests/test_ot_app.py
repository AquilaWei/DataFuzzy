import os
import subprocess
import sys
from datetime import date
from importlib.metadata import entry_points

from PySide6.QtWidgets import QApplication

from datafuzzy import __version__
from datafuzzy.core.pipeline import Pipeline
from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.keys import PasswordKeyProvider, UnlockCancelled, UnlockFailed
from datafuzzy.ot.ui.app import CANCELLED_TEXT, Launcher
from datafuzzy.ot.ui.unlock import PasswordDialog, PasswordPrompter

KEY = bytes(range(32))


class FakeProvider:
    """A key provider that returns `key`, or raises `error`; counts how often it was asked."""

    def __init__(self, key=KEY, error=None):
        self.key = key
        self.error = error
        self.calls = 0

    def get_key(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.key


class Recorder:
    def __init__(self):
        self.messages = []
        self.exit_codes = []

    def show(self, title, text):
        self.messages.append((title, text))

    def exit(self, code):
        self.exit_codes.append(code)


def make_launcher(qtbot, tmp_path, provider=None, factory=None, prompter=None):
    recorder = Recorder()
    provider = provider or FakeProvider()
    launcher = Launcher(
        QApplication.instance(), Pipeline(), [], tmp_path, db_path=tmp_path / "t.db",
        provider_factory=factory or (lambda path, ask: provider), prompter=prompter,
        show_message=recorder.show, exit_app=recorder.exit, offer_models=False)
    launcher.recorder = recorder
    return launcher


def run_unlock(qtbot, launcher):
    launcher.start()
    qtbot.waitUntil(lambda: launcher.outcome != "", timeout=10000)
    return launcher


def test_successful_unlock_opens_the_main_window_on_the_database(qtbot, tmp_path):
    launcher = run_unlock(qtbot, make_launcher(qtbot, tmp_path))
    qtbot.addWidget(launcher.window)
    assert (launcher.outcome, launcher.window.isVisible(), launcher.recorder.exit_codes) == ("ok", True, [])
    launcher.shutdown()


def test_cancelled_unlock_shows_message_and_exits_without_window(qtbot, tmp_path):
    launcher = run_unlock(qtbot, make_launcher(qtbot, tmp_path, FakeProvider(error=UnlockCancelled("x"))))
    assert launcher.outcome == "cancelled"
    assert launcher.recorder.messages == [("TheraNote", CANCELLED_TEXT)]
    assert launcher.recorder.exit_codes == [1]
    assert launcher.window is None


def test_cancelled_unlock_never_opens_or_creates_the_database(qtbot, tmp_path):
    launcher = run_unlock(qtbot, make_launcher(qtbot, tmp_path, FakeProvider(error=UnlockCancelled("x"))))
    assert launcher.store is None
    assert not (tmp_path / "t.db").exists()


def test_failed_unlock_shows_reason_and_exits_without_window(qtbot, tmp_path):
    launcher = run_unlock(qtbot, make_launcher(qtbot, tmp_path, FakeProvider(error=UnlockFailed("denied by user"))))
    assert launcher.outcome == "failed"
    assert "denied by user" in launcher.recorder.messages[0][1]
    assert (launcher.recorder.exit_codes, launcher.window) == ([1], None)


def test_unexpected_error_while_unlocking_is_shown_and_exits(qtbot, tmp_path):
    launcher = run_unlock(qtbot, make_launcher(qtbot, tmp_path, FakeProvider(error=RuntimeError("boom"))))
    assert launcher.outcome == "failed"
    assert "RuntimeError: boom" in launcher.recorder.messages[0][1]


def test_key_that_does_not_open_the_database_is_reported_and_leaves_it_alone(qtbot, tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as store:
        store.add_student("王小明")
    launcher = run_unlock(qtbot, make_launcher(qtbot, tmp_path, FakeProvider(key=bytes(32))))
    assert (launcher.outcome, launcher.window, launcher.recorder.exit_codes) == ("mismatch", None, [1])
    with RecordStore(tmp_path / "t.db", KEY) as again:
        assert [s.name for s in again.students()] == ["王小明"]


def test_shutdown_saves_pending_edit_and_closes_the_database(qtbot, tmp_path):
    launcher = run_unlock(qtbot, make_launcher(qtbot, tmp_path))
    qtbot.addWidget(launcher.window)
    launcher.window._editor_kwargs = {"debounce_ms": 60000}
    student_id = launcher.window.add_student("王小明")
    record_id = launcher.window.new_record(student_id, date(2026, 10, 1))
    launcher.window.editor.zh_edit.setPlainText("退出前輸入")
    launcher.shutdown()
    with RecordStore(tmp_path / "t.db", KEY) as again:
        assert again.get_record(record_id).zh_text == "退出前輸入"


def test_password_unlock_creates_password_on_first_launch_and_opens_window(qtbot, tmp_path):
    asked = []

    def show(creating, retry):
        asked.append((creating, retry))
        return "hunter2"

    launcher = run_unlock(qtbot, make_launcher(
        qtbot, tmp_path, factory=lambda path, ask: PasswordKeyProvider(path, ask), prompter=PasswordPrompter(show)))
    qtbot.addWidget(launcher.window)
    assert (launcher.outcome, asked) == ("ok", [(True, False)])
    launcher.shutdown()


def test_password_unlock_asks_again_after_a_wrong_password(qtbot, tmp_path):
    PasswordKeyProvider(tmp_path / "t.db", lambda creating, retry: "hunter2").get_key()
    answers = iter(["wrong", "hunter2"])
    asked = []

    def show(creating, retry):
        asked.append((creating, retry))
        return next(answers)

    launcher = run_unlock(qtbot, make_launcher(
        qtbot, tmp_path, factory=lambda path, ask: PasswordKeyProvider(path, ask), prompter=PasswordPrompter(show)))
    qtbot.addWidget(launcher.window)
    assert (launcher.outcome, asked) == ("ok", [(False, False), (False, True)])
    launcher.shutdown()


def test_cancelled_password_prompt_exits_without_window_or_database(qtbot, tmp_path):
    launcher = run_unlock(qtbot, make_launcher(
        qtbot, tmp_path, factory=lambda path, ask: PasswordKeyProvider(path, ask),
        prompter=PasswordPrompter(lambda creating, retry: None)))
    assert (launcher.outcome, launcher.window, launcher.recorder.exit_codes) == ("cancelled", None, [1])
    assert not (tmp_path / "t.db").exists()


def test_password_dialog_when_creating_needs_matching_confirmation(qtbot):
    dialog = PasswordDialog(creating=True)
    qtbot.addWidget(dialog)
    dialog.password_edit.setText("hunter2")
    dialog.confirm_edit.setText("hunter3")
    assert (dialog.ok_btn.isEnabled(), dialog.problem.text()) == (False, "兩次輸入的密碼不一致。")


def test_password_dialog_when_creating_accepts_matching_passwords(qtbot):
    dialog = PasswordDialog(creating=True)
    qtbot.addWidget(dialog)
    dialog.password_edit.setText("hunter2")
    dialog.confirm_edit.setText("hunter2")
    assert (dialog.ok_btn.isEnabled(), dialog.password()) == (True, "hunter2")


def test_password_dialog_when_unlocking_needs_no_confirmation(qtbot):
    dialog = PasswordDialog(creating=False)
    qtbot.addWidget(dialog)
    dialog.password_edit.setText("hunter2")
    assert dialog.ok_btn.isEnabled() is True


def test_password_dialog_rejects_an_empty_password(qtbot):
    dialog = PasswordDialog(creating=False)
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.isEnabled() is False


def test_password_dialog_says_when_the_last_password_was_wrong(qtbot):
    dialog = PasswordDialog(creating=False, retry=True)
    qtbot.addWidget(dialog)
    assert dialog.problem.text() == "密碼不正確，請再試一次。"


def test_datafuzzy_and_theranote_scripts_launch_theranote():
    scripts = {e.name: e.value for e in entry_points(group="console_scripts") if e.name in ("datafuzzy", "theranote")}
    assert scripts == {"datafuzzy": "datafuzzy.ot.ui.app:main", "theranote": "datafuzzy.ot.ui.app:main"}


def run_app(flag, tmp_path):
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "DATAFUZZY_MODELS_DIR": str(tmp_path),
           "DATAFUZZY_REQUIRE_MODEL": ""}
    return subprocess.run([sys.executable, "-m", "datafuzzy.ot.ui.app", flag], env=env,
                          capture_output=True, text=True, check=True).stdout


def test_version_flag_prints_app_name_and_version(tmp_path):
    assert run_app("--version", tmp_path).strip() == f"TheraNote {__version__}"


def test_self_test_flag_round_trips_a_chart_with_the_name_masked(tmp_path):
    out = run_app("--self-test", tmp_path)
    assert "TheraNote" in out and "self-test OK" in out and "[PERSON_A]" in out

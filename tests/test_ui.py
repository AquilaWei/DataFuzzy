from datafuzzy.core.pipeline import Pipeline
from datafuzzy.core.store import SessionStore
from datafuzzy.ui.main_window import NEW_SESSION, MainWindow


def make_window(qtbot, tmp_path):
    store = SessionStore(tmp_path)
    win = MainWindow(Pipeline(), store)
    qtbot.addWidget(win)
    win.qtbot = qtbot
    return win, store


def send(win, text):
    win.input.setPlainText(text)
    win.submit()
    win.qtbot.waitUntil(lambda: not win.busy, timeout=10000)


def test_obfuscate_then_restore(qtbot, tmp_path):
    win, store = make_window(qtbot, tmp_path)
    send(win, "寄給 amy@x.com，主機 10.0.0.8")
    assert len(store.list()) == 1
    session = store.list()[0]
    assert win.chat.reply_text(0) == "寄給 [EMAIL_A]，主機 [IP_A]"

    # Second input into the same (now selected) session keeps codes stable.
    assert win.session_box.currentData() == session.id
    send(win, "再寄一次 amy@x.com")
    assert win.chat.reply_text(1) == "再寄一次 [EMAIL_A]"
    assert len(store.list()) == 1

    win.restore_btn.setChecked(True)
    assert win.session_box.findData(NEW_SESSION) == -1
    send(win, "請 [EMAIL_A] 檢查 [IP_A] 與 [PERSON_Q]")
    assert win.chat.reply_text(2) == "請 amy@x.com 檢查 10.0.0.8 與 [PERSON_Q]"


def test_new_session_option_creates_second_file(qtbot, tmp_path):
    win, store = make_window(qtbot, tmp_path)
    send(win, "a@b.co")
    win.session_box.setCurrentIndex(win.session_box.findData(NEW_SESSION))
    send(win, "c@d.co")
    assert len(store.list()) == 2
    assert len(list(store.dir.glob("*.dfmap"))) == 2


def test_restore_without_sessions(qtbot, tmp_path):
    win, _ = make_window(qtbot, tmp_path)
    win.restore_btn.setChecked(True)
    send(win, "[EMAIL_A]")
    assert "目前沒有代號檔" in win.chat.toPlainText()


def test_copy_link_copies_reply(qtbot, tmp_path):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication

    win, _ = make_window(qtbot, tmp_path)
    send(win, "a@b.co")
    win.chat.anchorClicked.emit(QUrl("copy:0"))
    assert QGuiApplication.clipboard().text() == "[EMAIL_A]"


def test_notice_when_no_model(qtbot, tmp_path):
    win, _ = make_window(qtbot, tmp_path)
    send(win, "Alice wrote to a@b.co")
    assert "未安裝英文模型" in win.chat.toPlainText()
    assert "僅規則模式" in win.model_status.text()


def test_model_manager_download_and_delete(qtbot, tmp_path, file_server):
    from datafuzzy.ui.model_manager import ModelManager

    spec = file_server.spec(lang="en")
    root = tmp_path / "models"
    store = SessionStore(tmp_path)
    win = MainWindow(Pipeline(), store, [spec], root)
    qtbot.addWidget(win)

    dialog = ModelManager([spec], root, win)
    qtbot.addWidget(dialog)
    dialog.models_changed.connect(win.reload_models)
    row = dialog.rows[0]
    assert row.button.text() == "下載"

    with qtbot.waitSignal(dialog.models_changed, timeout=10000):
        row.button.click()
    qtbot.waitUntil(lambda: row.thread is None)
    assert row.button.text() == "刪除"
    assert "en" in win.pipeline.models
    assert "英文" in win.model_status.text()

    row.button.click()
    assert row.button.text() == "下載"
    assert win.pipeline.models == {}

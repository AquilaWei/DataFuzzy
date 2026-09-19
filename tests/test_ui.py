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


def test_unmark_code_updates_replies_and_future_input(qtbot, tmp_path):
    from PySide6.QtCore import QUrl

    win, store = make_window(qtbot, tmp_path)
    send(win, "主機 10.0.0.8，寄給 a@b.co")
    send(win, "再查 10.0.0.8")
    session = store.list()[0]

    with qtbot.waitSignal(win.chat.code_clicked) as clicked:
        win.chat.anchorClicked.emit(QUrl("code:0:0"))
    assert clicked.args == [0, "[IP_A]"]

    win.unmark(0, "[IP_A]")
    assert win.chat.reply_text(0) == "主機 10.0.0.8，寄給 [EMAIL_A]"
    assert win.chat.reply_text(1) == "再查 10.0.0.8"
    assert [s.text for s in win.chat.replies[0].spans] == ["[EMAIL_A]"]
    assert "已取消標記 「10.0.0.8」" in win.chat.toPlainText()
    assert store.load(session.id).ignored == {"10.0.0.8": "[IP_A]"}
    assert win.panel.table.rowCount() == 1

    send(win, "10.0.0.8 與 10.0.0.9")
    assert win.chat.reply_text(2) == "10.0.0.8 與 [IP_B]"


def test_panel_rename_preview_and_delete(qtbot, tmp_path):
    win, store = make_window(qtbot, tmp_path)
    send(win, "John Smith? no: a@b.co and 10.0.0.8")
    session = store.list()[0]
    assert win.panel.current_id == session.id
    assert win.panel.table.rowCount() == 2
    assert win.panel.table.item(0, 0).text() == "[EMAIL_A]"
    assert win.panel.table.item(0, 1).text() == "a@b.co"

    item = win.panel.list.item(0)
    win.panel.start_rename(item)
    item.setText("客戶 A")  # what committing the inline editor does
    assert store.sessions[session.id].label == "客戶 A"
    assert win.session_box.currentText().startswith("客戶 A")
    assert win.panel.list.item(0).text().startswith("客戶 A\n")

    win.delete_session(session.id)
    assert store.list() == [] and not list(store.dir.glob("*.dfmap"))
    assert win.panel.list.count() == 0 and win.panel.table.rowCount() == 0
    assert win.chat.replies[0].session_id is None


def test_restore_recommends_matching_code_file(qtbot, tmp_path):
    win, store = make_window(qtbot, tmp_path)
    send(win, "a@b.co")
    win.session_box.setCurrentIndex(win.session_box.findData(NEW_SESSION))
    send(win, "c@d.co 與 10.0.0.8")
    first, second = store.list()

    win.restore_btn.setChecked(True)
    win.input.setPlainText("請 [EMAIL_A] 看 [IP_A]")
    assert win.session_box.currentData() == second.id
    assert "可還原 2 個代號" in win.recommend_hint.text()

    # A manual choice sticks while the best match stays the same.
    win.session_box.setCurrentIndex(win.session_box.findData(first.id))
    win.input.setPlainText("請 [EMAIL_A] 看 [IP_A]。")
    assert win.session_box.currentData() == first.id

    win.input.setPlainText("沒有代號")
    assert win.recommend_hint.text() == ""


def select(chat, needle, occurrence):
    """Select the `occurrence`-th appearance of `needle` in the transcript."""
    doc = chat.toPlainText()
    pos = -1
    for _ in range(occurrence + 1):
        pos = doc.index(needle, pos + 1)
    cursor = chat.textCursor()
    cursor.setPosition(pos)
    cursor.setPosition(pos + len(needle), cursor.MoveMode.KeepAnchor)
    chat.setTextCursor(cursor)


def test_mark_missed_value_in_replies_and_future_input(qtbot, tmp_path):
    win, store = make_window(qtbot, tmp_path)  # no models: names are missed
    send(win, "顧秀的信箱是 a@b.co")
    send(win, "請顧秀回電")
    session = store.list()[0]

    select(win.chat, "顧秀", 0)  # in the user's own message: not a reply
    assert win.chat.selected_mark() is None
    select(win.chat, "顧秀", 1)  # in the first reply
    assert win.chat.selected_mark() == (0, "顧秀")
    menu = win.chat.context_menu(win.chat.cursorRect().center())
    sub = menu.actions()[0].menu()
    assert menu.actions()[0].text() == "將「顧秀」標記為敏感資料"
    assert [a.text() for a in sub.actions()] == ["人名", "組織", "地點", "其他"]
    doc = win.chat.toPlainText()  # from the first reply into the next message
    cursor = win.chat.textCursor()
    cursor.setPosition(doc.index("[EMAIL_A]"))
    cursor.setPosition(doc.index("請顧秀") + 1, cursor.MoveMode.KeepAnchor)
    win.chat.setTextCursor(cursor)
    assert win.chat.selected_mark() is None

    with qtbot.waitSignal(win.chat.mark_requested) as marked:
        sub.actions()[0].trigger()
    assert marked.args == [0, "顧秀", "PERSON"]
    assert win.chat.reply_text(0) == "[PERSON_A]的信箱是 [EMAIL_A]"
    assert win.chat.reply_text(1) == "請[PERSON_A]回電"
    assert "已將「顧秀」標記為 [PERSON_A]，替換 2 處" in win.chat.toPlainText()
    assert store.load(session.id).to_code["顧秀"] == "[PERSON_A]"
    assert win.panel.table.rowCount() == 2

    send(win, "顧秀明天請假")
    assert win.chat.reply_text(2) == "[PERSON_A]明天請假"

    win.unmark(0, "[PERSON_A]")  # un-mark, then mark again: the old code comes back
    win.mark(0, "顧秀", "PERSON")
    assert win.chat.reply_text(0) == "[PERSON_A]的信箱是 [EMAIL_A]"


def test_mark_rejects_selection_with_a_code(qtbot, tmp_path):
    win, store = make_window(qtbot, tmp_path)
    send(win, "顧秀的信箱是 a@b.co")
    win.mark(0, "是 [EMAIL_A]", "OTHER")
    assert win.chat.reply_text(0) == "顧秀的信箱是 [EMAIL_A]"
    assert "選取範圍不能包含代號" in win.chat.toPlainText()

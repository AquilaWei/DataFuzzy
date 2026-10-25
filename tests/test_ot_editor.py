from datetime import date, datetime

import pytest

from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.ui.editor import RecordEditor

KEY = bytes(range(32))
DAY = date(2026, 10, 1)


@pytest.fixture
def store(tmp_path):
    ticks = iter(datetime(2026, 10, 1, 9, 0, s) for s in range(60))
    with RecordStore(tmp_path / "t.db", KEY, now=lambda: next(ticks)) as s:
        yield s


@pytest.fixture
def record(store):
    student = store.add_student("王小明")
    return store.add_record(student.id, DAY, "新竹國小", "今天練習剪紙", "Cutting practice")


def make_editor(qtbot, store, record, debounce_ms=10):
    editor = RecordEditor(store, record.id, debounce_ms=debounce_ms)
    qtbot.addWidget(editor)
    return editor


def test_editor_shows_student_date_and_both_texts(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    assert editor.title.text() == "王小明 · 2026-10-01"
    assert (editor.zh_edit.toPlainText(), editor.en_edit.toPlainText()) == ("今天練習剪紙", "Cutting practice")


def test_editor_shows_record_location(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    assert editor.location_box.currentText() == "新竹國小"


def test_location_drop_down_lists_locations_used_so_far(qtbot, store, record):
    other = store.add_student("陳美玲")
    store.add_record(other.id, date(2026, 10, 2), "台北診所")
    editor = make_editor(qtbot, store, record)
    assert [editor.location_box.itemText(i) for i in range(editor.location_box.count())] == ["台北診所", "新竹國小"]


def test_typing_chinese_text_is_saved_after_the_pause(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.zh_edit.setPlainText("改過的中文")
    qtbot.waitUntil(lambda: store.get_record(record.id).zh_text == "改過的中文", timeout=2000)


def test_typing_english_text_is_saved_and_chinese_stays(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.en_edit.setPlainText("New English")
    qtbot.waitUntil(lambda: store.get_record(record.id).en_text == "New English", timeout=2000)
    assert store.get_record(record.id).zh_text == "今天練習剪紙"


def test_changing_location_is_saved(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.location_box.setEditText("台北診所")
    qtbot.waitUntil(lambda: store.get_record(record.id).location == "台北診所", timeout=2000)


def test_nothing_is_written_before_the_pause_has_passed(qtbot, store, record):
    editor = make_editor(qtbot, store, record, debounce_ms=60000)
    editor.zh_edit.setPlainText("還沒存")
    assert store.get_record(record.id).zh_text == "今天練習剪紙"


def test_flush_saves_immediately(qtbot, store, record):
    editor = make_editor(qtbot, store, record, debounce_ms=60000)
    editor.zh_edit.setPlainText("馬上存")
    editor.flush()
    assert store.get_record(record.id).zh_text == "馬上存"


def test_back_button_saves_pending_text_and_signals_closed(qtbot, store, record):
    editor = make_editor(qtbot, store, record, debounce_ms=60000)
    editor.zh_edit.setPlainText("離開前的字")
    with qtbot.waitSignal(editor.closed, timeout=1000):
        editor.back_btn.click()
    assert store.get_record(record.id).zh_text == "離開前的字"


def test_saving_announces_the_record_id(qtbot, store, record):
    editor = make_editor(qtbot, store, record, debounce_ms=60000)
    editor.zh_edit.setPlainText("x")
    with qtbot.waitSignal(editor.saved, timeout=1000) as saved:
        editor.flush()
    assert saved.args == [record.id]


def test_opening_the_editor_does_not_write_anything(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.flush()
    assert store.get_record(record.id).updated_at == record.updated_at


def test_reload_shows_english_text_written_elsewhere(qtbot, store, record):
    editor = make_editor(qtbot, store, record, debounce_ms=60000)
    store.set_en_texts({record.id: "From import"})
    editor.reload()
    assert editor.en_edit.toPlainText() == "From import"


def test_reload_does_not_discard_pending_chinese_edit(qtbot, store, record):
    editor = make_editor(qtbot, store, record, debounce_ms=60000)
    editor.zh_edit.setPlainText("還沒存的中文")
    editor.reload()
    assert store.get_record(record.id).zh_text == "還沒存的中文"


def test_editor_shows_the_records_activity(qtbot, store):
    student = store.add_student("陳美玲")
    record = store.add_record(student.id, DAY, activity="串珠")
    editor = make_editor(qtbot, store, record)
    assert editor.activity_edit.toPlainText() == "串珠"


def test_typing_an_activity_is_saved_and_texts_stay(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.activity_edit.setPlainText("平衡木、拋接球")
    qtbot.waitUntil(lambda: store.get_record(record.id).activity == "平衡木、拋接球", timeout=2000)
    assert (store.get_record(record.id).zh_text, store.get_record(record.id).en_text) == ("今天練習剪紙", "Cutting practice")


def test_activity_box_stays_visible_above_the_tabs(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.show()
    editor.tabs.setCurrentIndex(1)
    assert editor.activity_edit.isVisible()
    assert editor.activity_edit.geometry().bottom() < editor.tabs.geometry().top()


def test_changing_the_date_moves_the_record_and_updates_the_title(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    with qtbot.waitSignal(editor.saved):
        assert editor.change_date(date(2026, 10, 2))
    assert editor.title.text() == "王小明 · 2026-10-02"
    assert store.get_record(record.id).visit_date == date(2026, 10, 2)


def test_date_already_taken_is_refused(qtbot, store, record, monkeypatch):
    store.add_record(record.student_id, date(2026, 10, 2))
    editor = make_editor(qtbot, store, record)
    warned = []
    monkeypatch.setattr(editor, "_warn_taken", warned.append)
    assert not editor.change_date(date(2026, 10, 2))
    assert warned == [date(2026, 10, 2)]
    assert editor.title.text() == "王小明 · 2026-10-01"


def test_cancelled_date_prompt_changes_nothing(qtbot, store, record, monkeypatch):
    editor = make_editor(qtbot, store, record)
    monkeypatch.setattr(editor, "_ask_date", lambda: None)
    editor.date_btn.click()
    assert store.get_record(record.id).visit_date == DAY

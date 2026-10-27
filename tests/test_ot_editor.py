from datetime import date, datetime

import pytest

from datafuzzy.ot.db import RecordStore, StudentProfile
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
    assert (editor.profile.name.text(), editor.title.text()) == ("王小明", "2026-10-01  週四")
    assert (editor.zh_edit.toPlainText(), editor.en_edit.toPlainText()) == ("今天練習剪紙", "Cutting practice")


def test_profile_is_shown_above_the_chart(qtbot, store, record):
    store.set_profile(record.student_id, StudentProfile(diagnosis="ADHD, ODD", grade="3", location="新竹國小"))
    editor = make_editor(qtbot, store, record)
    values = editor.profile.values
    assert (values["diagnosis"].text(), values["grade"].text(), values["location"].text(), values["age"].text()) == (
        "ADHD, ODD", "3", "新竹國小", "—")
    page = editor.page_layout
    assert page.indexOf(editor.profile) < page.indexOf(editor.splitter)


def test_profile_without_a_location_shows_the_latest_visits(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    assert editor.profile.values["location"].text() == "新竹國小"


def test_editor_has_no_location_field_and_shows_the_records_place(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    assert not hasattr(editor, "location_box")
    assert editor.record_place.text() == "地點：新竹國小"


def test_profile_edit_button_asks_for_the_students_profile(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    with qtbot.waitSignal(editor.edit_profile) as signal:
        editor.profile.edit_btn.click()
    assert signal.args == [record.student_id]


def test_typing_chinese_text_is_saved_after_the_pause(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.zh_edit.setPlainText("改過的中文")
    qtbot.waitUntil(lambda: store.get_record(record.id).zh_text == "改過的中文", timeout=2000)


def test_typing_english_text_is_saved_and_chinese_stays(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.en_edit.setPlainText("New English")
    qtbot.waitUntil(lambda: store.get_record(record.id).en_text == "New English", timeout=2000)
    assert store.get_record(record.id).zh_text == "今天練習剪紙"


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
    assert editor.title.text() == "2026-10-02  週五"
    assert store.get_record(record.id).visit_date == date(2026, 10, 2)


def test_date_already_taken_is_refused(qtbot, store, record, monkeypatch):
    store.add_record(record.student_id, date(2026, 10, 2))
    editor = make_editor(qtbot, store, record)
    warned = []
    monkeypatch.setattr(editor, "_warn_taken", warned.append)
    assert not editor.change_date(date(2026, 10, 2))
    assert warned == [date(2026, 10, 2)]
    assert editor.title.text() == "2026-10-01  週四"


def test_cancelled_date_prompt_changes_nothing(qtbot, store, record, monkeypatch):
    editor = make_editor(qtbot, store, record)
    monkeypatch.setattr(editor, "_ask_date", lambda: None)
    editor.date_btn.click()
    assert store.get_record(record.id).visit_date == DAY


def test_double_clicking_a_tab_copies_that_chart(qtbot, store, record):
    from PySide6.QtGui import QGuiApplication
    editor = make_editor(qtbot, store, record)
    editor.tabs.tabBarDoubleClicked.emit(1)
    assert QGuiApplication.clipboard().text() == "Cutting practice"
    assert editor.status.text() == "已複製英文病歷"
    editor.tabs.tabBarDoubleClicked.emit(0)
    assert QGuiApplication.clipboard().text() == "今天練習剪紙"
    assert editor.status.text() == "已複製中文病歷"


@pytest.mark.parametrize("typed, saved", [
    ("9:30", "09:30"), ("14：05", "14:05"), ("", ""), ("9:30 AM", "09:30"), ("2:05 pm", "14:05"),
    ("12:00 PM", "12:00"), ("12:15 AM", "00:15"), ("1:30PM", "13:30")])
def test_start_time_is_saved_as_hh_mm(qtbot, store, record, typed, saved):
    store.update_record(record.id, start_time="08:00")
    editor = make_editor(qtbot, store, record)
    editor.time_box.setEditText(typed)
    editor.flush()
    assert store.get_record(record.id).start_time == saved


def test_start_time_is_shown_as_am_pm(qtbot, store, record):
    store.update_record(record.id, start_time="14:05")
    editor = make_editor(qtbot, store, record)
    assert (editor.time_box.currentText(), editor.time_box.itemText(0)) == ("2:05 PM", "7:00 AM")
    editor.flush()
    assert store.get_record(record.id).start_time == "14:05"


@pytest.mark.parametrize("typed", ["13:00 PM", "0:30 AM", "24:00"])
def test_impossible_times_are_not_saved(qtbot, store, record, typed):
    store.update_record(record.id, start_time="08:00")
    editor = make_editor(qtbot, store, record)
    editor.time_box.setEditText(typed)
    editor.flush()
    assert store.get_record(record.id).start_time == "08:00"


def test_changing_the_start_moves_the_default_end_along(qtbot, store, record):
    store.update_record(record.id, start_time="08:00", end_time="08:30")
    editor = make_editor(qtbot, store, record)
    editor.time_box.setEditText("9:15 AM")
    editor.flush()
    assert editor.end_box.currentText() == "9:45 AM"
    assert store.get_record(record.id).end_time == "09:45"


def test_end_set_by_hand_stays_when_the_start_changes(qtbot, store, record):
    store.update_record(record.id, start_time="08:00", end_time="08:30")
    editor = make_editor(qtbot, store, record)
    editor.end_box.setEditText("9:00 AM")
    editor.time_box.setEditText("8:15 AM")
    editor.flush()
    assert (store.get_record(record.id).start_time, store.get_record(record.id).end_time) == ("08:15", "09:00")


def test_end_saved_earlier_by_hand_stays_when_the_start_changes(qtbot, store, record):
    store.update_record(record.id, start_time="08:00", end_time="08:50")
    editor = make_editor(qtbot, store, record)
    editor.time_box.setEditText("8:15 AM")
    editor.flush()
    assert store.get_record(record.id).end_time == "08:50"


def test_half_typed_start_time_is_not_saved(qtbot, store, record):
    store.update_record(record.id, start_time="08:00")
    editor = make_editor(qtbot, store, record)
    editor.time_box.setEditText("9:")
    editor.flush()
    assert store.get_record(record.id).start_time == "08:00"
    assert "9:30 AM" in editor.status.text()


def compare_setup(store, record):
    student_id = record.student_id
    older = store.add_record(student_id, date(2026, 9, 10), "新竹國小", "最早一次")
    nearer = store.add_record(student_id, date(2026, 9, 24), "新竹國小", "上一次", activity="串珠")
    later = store.add_record(student_id, date(2026, 10, 8), "新竹國小", "下一次")
    return older, nearer, later


def test_compare_list_starts_at_the_nearest_earlier_visit_and_goes_back(qtbot, store, record):
    compare_setup(store, record)
    editor = make_editor(qtbot, store, record)
    assert [a.text()[:10] for a in editor.compare_menu().actions()] == [
        "2026-09-24", "2026-09-10", "2026-10-08"]


def test_compare_list_says_when_there_is_nothing_else(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    [only] = editor.compare_menu().actions()
    assert (only.text(), only.isEnabled()) == ("這位學生沒有其他病歷", False)


def test_picking_a_visit_shows_it_beside_the_chart(qtbot, store, record):
    _, nearer, _ = compare_setup(store, record)
    editor = make_editor(qtbot, store, record)
    editor.compare_menu().actions()[0].trigger()
    panel = editor.compare
    assert panel.record_id == nearer.id
    assert (panel.activity.toPlainText(), panel.tabs.widget(0).toPlainText()) == ("串珠", "上一次")
    assert panel.tabs.widget(0).isReadOnly()
    assert editor.splitter.indexOf(panel) == 1


def test_the_profile_stays_above_both_charts_while_comparing(qtbot, store, record):
    compare_setup(store, record)
    editor = make_editor(qtbot, store, record)
    editor.compare_menu().actions()[0].trigger()
    assert editor.profile.parent() is editor.scroll.widget()
    assert editor.splitter.count() == 2


def test_the_comparisons_rows_line_up_with_the_charts(qtbot, store, record):
    compare_setup(store, record)
    editor = make_editor(qtbot, store, record)
    editor.compare_menu().actions()[0].trigger()
    panel = editor.compare
    assert panel.heading_row.height() == editor.heading_row.height()
    assert panel.times_row.height() == editor.times_row.height()
    assert panel.activity.height() == editor.activity_edit.height()


def test_long_activities_make_the_box_taller(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    editor.show()
    short = editor.activity_edit.height()
    editor.activity_edit.setPlainText("串珠\n平衡木\n拋接球\n剪紙\n跳格子\n盪鞦韆")
    qtbot.wait(10)
    assert editor.activity_edit.height() > short
    assert editor.activity_edit.verticalScrollBar().maximum() == 0


def test_the_profile_and_chart_scroll_as_one_page(qtbot, store, record):
    editor = make_editor(qtbot, store, record)
    assert editor.scroll.widget().isAncestorOf(editor.profile)
    assert editor.scroll.widget().isAncestorOf(editor.splitter)


def test_a_longer_compared_activity_makes_both_boxes_taller(qtbot, store, record):
    older, _, _ = compare_setup(store, record)
    store.update_record(older.id, activity="串珠\n平衡木\n拋接球\n剪紙\n跳格子\n盪鞦韆")
    editor = make_editor(qtbot, store, record)
    short = editor.activity_edit.height()
    editor.show_compare(older.id)
    assert editor.activity_edit.height() == editor.compare.activity.height() > short


def test_closing_the_comparison_gives_the_activity_its_own_height_back(qtbot, store, record):
    older, _, _ = compare_setup(store, record)
    store.update_record(older.id, activity="串珠\n平衡木\n拋接球\n剪紙\n跳格子\n盪鞦韆")
    editor = make_editor(qtbot, store, record)
    short = editor.activity_edit.height()
    editor.show_compare(older.id)
    editor.close_compare()
    assert editor.activity_edit.height() == short


def test_the_comparison_shows_its_own_times(qtbot, store, record):
    older, _, _ = compare_setup(store, record)
    store.update_record(older.id, start_time="14:00", end_time="14:30")
    editor = make_editor(qtbot, store, record)
    editor.compare_menu().actions()[1].trigger()
    assert (editor.compare.start.text(), editor.compare.end.text()) == ("2:00 PM", "2:30 PM")


def test_picking_another_visit_replaces_the_shown_one(qtbot, store, record):
    older, _, _ = compare_setup(store, record)
    editor = make_editor(qtbot, store, record)
    editor.compare_menu().actions()[0].trigger()
    editor.compare_menu().actions()[1].trigger()
    assert editor.compare.record_id == older.id
    assert editor.splitter.count() == 2


def test_closing_the_comparison_leaves_the_chart_alone(qtbot, store, record):
    compare_setup(store, record)
    editor = make_editor(qtbot, store, record)
    editor.compare_menu().actions()[0].trigger()
    editor.compare.close_btn.click()
    assert editor.compare is None

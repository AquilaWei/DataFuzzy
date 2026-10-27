from dataclasses import replace
from datetime import date

import pytest
from PySide6.QtCore import QDate, QPoint, Qt
from PySide6.QtWidgets import QFrame

from datafuzzy import __version__
from datafuzzy.core.pipeline import Pipeline
from datafuzzy.ot.db import RecordStore, Session, StudentProfile
from datafuzzy.ot.ui import main_window
from datafuzzy.ot.ui.date_view import NAME_ROLE, PLACE_ROLE
from datafuzzy.ot.ui.main_window import (
    DATE_MODE,
    LOCATION_MODE,
    STUDENT_MODE,
    TheraNoteWindow,
)

KEY = bytes(range(32))
OCT_1 = date(2026, 10, 1)


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


def make_window(qtbot, store, debounce_ms=10):
    window = TheraNoteWindow(store, Pipeline(), debounce_ms=debounce_ms)
    qtbot.addWidget(window)
    window.show()
    return window


def student_names(window):
    return [window.student_list.item(i).text() for i in range(window.student_list.count())]


def test_window_title_has_app_name_and_version(qtbot, store):
    window = make_window(qtbot, store)
    assert window.windowTitle() == f"TheraNote {__version__}"


def test_new_record_button_is_disabled_until_a_student_exists(qtbot, store):
    window = make_window(qtbot, store)
    assert window.add_record_btn.isEnabled() is False


def test_added_student_is_listed_and_selected(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    assert student_names(window) == ["王小明"]
    assert window.current_student_id() == student_id


def test_empty_student_name_adds_nobody(qtbot, store):
    window = make_window(qtbot, store)
    assert window.add_student("  ") is None
    assert store.students() == []


def test_add_student_asks_for_the_name_when_none_given(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_ask_student_name", lambda: "陳美玲")
    window.add_student()
    assert student_names(window) == ["陳美玲"]


def test_cancelled_name_prompt_adds_nobody(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_ask_student_name", lambda: "")
    window.add_student()
    assert store.students() == []


def test_selecting_a_student_shows_their_cards_newest_first(qtbot, store):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1), "A校", "一")
    store.add_record(student.id, date(2026, 10, 8), "A校", "二")
    window = make_window(qtbot, store)
    window.student_list.setCurrentRow(0)
    assert [c.date_label.text()[:10] for c in window.student_view.stack.cards] == ["2026-10-08", "2026-10-01"]


def test_first_record_of_a_student_without_a_location_has_none(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    record_id = window.new_record(student_id, OCT_1)
    assert store.get_record(record_id).location == ""


def test_new_record_takes_the_location_from_the_profile(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    store.set_profile(student_id, StudentProfile(location="新竹國小"))
    record_id = window.new_record(student_id, OCT_1)
    assert store.get_record(record_id).location == "新竹國小"


def test_without_a_profile_location_a_new_record_takes_the_last_visits(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    first = window.new_record(student_id, OCT_1)
    store.update_record(first, location="新竹國小")
    second = window.new_record(student_id, date(2026, 10, 8))
    assert store.get_record(second).location == "新竹國小"


def test_changing_the_profile_location_keeps_old_records_where_they_were(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    store.set_profile(student_id, StudentProfile(location="A校"))
    old = window.new_record(student_id, OCT_1)
    monkeypatch.setattr(window, "_ask_profile", lambda name, current: StudentProfile(location="B校"))
    window.edit_profile(student_id)
    new = window.new_record(student_id, date(2026, 10, 8))
    assert (store.get_record(old).location, store.get_record(new).location) == ("A校", "B校")
    assert window.editor.profile.values["location"].text() == "B校"
    assert location_names(window) == ["B校", "A校"]


def test_new_record_ends_thirty_minutes_after_its_start(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    first = window.new_record(student_id, OCT_1)
    store.update_record(first, start_time="10:30")
    second = window.new_record(student_id, date(2026, 10, 8))
    assert store.get_record(second).end_time == "11:00"
    assert window.editor.end_box.currentText() == "11:00 AM"


def test_new_record_takes_the_time_slot_of_the_same_weekday(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    store.add_record(student_id, date(2026, 10, 2), start_time="14:00", end_time="14:45")  # Friday
    store.add_record(student_id, date(2026, 10, 5), start_time="09:00", end_time="09:30")  # Monday
    record_id = window.new_record(student_id, date(2026, 10, 9))  # Friday
    assert (store.get_record(record_id).start_time, store.get_record(record_id).end_time) == ("14:00", "14:45")
    assert (window.editor.time_box.currentText(), window.editor.end_box.currentText()) == ("2:00 PM", "2:45 PM")


def test_next_record_starts_with_the_students_last_start_time(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    first = window.new_record(student_id, OCT_1)
    store.update_record(first, start_time="10:30")
    window.new_record(student_id, date(2026, 10, 8))
    assert window.editor.time_box.currentText() == "10:30 AM"


def test_new_record_opens_the_editor(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.new_record(student_id, OCT_1)
    assert (window.content.currentWidget() is window.editor, window.editor.profile.name.text(),
            window.editor.title.text()) == (True, "王小明", "2026-10-01  週四")


def test_new_record_appears_as_a_card(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.new_record(student_id, OCT_1)
    assert len(window.student_view.stack.cards) == 1


def test_second_record_on_same_day_asks_and_opens_the_existing_one(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    first = window.new_record(student_id, OCT_1)
    window.close_editor()
    asked = []
    monkeypatch.setattr(window, "_confirm_open_existing", lambda name, day: asked.append((name, day)) or True)
    again = window.new_record(student_id, OCT_1)
    assert (again, asked, window.editor.record_id) == (first, [("王小明", OCT_1)], first)
    assert len(store.records_for_student(student_id)) == 1


def test_declining_the_duplicate_prompt_opens_nothing(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.new_record(student_id, OCT_1)
    window.close_editor()
    monkeypatch.setattr(window, "_confirm_open_existing", lambda name, day: False)
    assert window.new_record(student_id, OCT_1) is None
    assert window.editor is None


def test_new_record_button_asks_which_student_and_day(qtbot, store, monkeypatch):
    student = store.add_student("王小明")
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_pick_new_record", lambda: (student.id, OCT_1))
    window.add_record_btn.click()
    assert window.editor.record_id == store.find_record(student.id, OCT_1).id


def _dialog_setup(store):
    a, b, c = (store.add_student(n) for n in ("甲", "乙", "丙"))
    store.add_record(a.id, OCT_1, "A校")
    store.add_record(b.id, OCT_1, "B校")
    store.add_record(c.id, date(2026, 10, 2), "A校")
    store.set_profile(c.id, StudentProfile(location="B校"))  # moved from A校 to B校
    return a, b, c


def _names(box):
    return {box.itemText(i) for i in range(box.count())}


def test_new_record_dialog_by_location_lists_the_students_located_there(qtbot, store):
    _dialog_setup(store)
    dialog = main_window.NewRecordDialog(store, None, OCT_1, by_location=True, location="B校")
    qtbot.addWidget(dialog)
    assert _names(dialog.student_box) == {"乙", "丙"}
    dialog.location_box.setCurrentIndex(dialog.location_box.findData("A校"))
    assert _names(dialog.student_box) == {"甲"}
    dialog.location_box.setCurrentIndex(dialog.location_box.findData(None))
    assert _names(dialog.student_box) == {"甲", "乙", "丙"}


def test_new_record_dialog_starts_at_the_days_location(qtbot, store):
    _dialog_setup(store)
    dialog = main_window.NewRecordDialog(store, None, OCT_1, by_location=True)
    qtbot.addWidget(dialog)
    assert dialog.location_box.currentText() in ("A校", "B校")
    dialog = main_window.NewRecordDialog(store, None, OCT_1, by_location=True, location="A校")
    qtbot.addWidget(dialog)
    assert (dialog.location(), _names(dialog.student_box)) == ("A校", {"甲"})


def test_new_record_dialog_by_student_has_no_location(qtbot, store):
    _dialog_setup(store)
    dialog = main_window.NewRecordDialog(store, None, OCT_1)
    qtbot.addWidget(dialog)
    assert (dialog.location_box, len(_names(dialog.student_box)), dialog.location()) == (None, 3, None)


def test_cancelled_new_record_dialog_creates_nothing(qtbot, store, monkeypatch):
    store.add_student("王小明")
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_pick_new_record", lambda: None)
    window.add_record_btn.click()
    assert store.records_between(date(2000, 1, 1), date(2100, 1, 1)) == []


def test_typing_in_the_editor_is_saved_to_the_database(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    record_id = window.new_record(student_id, OCT_1)
    window.editor.zh_edit.setPlainText("今天練習剪紙")
    qtbot.waitUntil(lambda: store.get_record(record_id).zh_text == "今天練習剪紙", timeout=2000)


def test_saved_text_shows_up_on_the_card(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.new_record(student_id, OCT_1)
    window.editor.zh_edit.setPlainText("今天練習剪紙")
    qtbot.waitUntil(lambda: window.student_view.stack.cards[0].preview_label.text() == "今天練習剪紙", timeout=2000)


def test_closing_the_window_saves_pending_edit(qtbot, store):
    window = make_window(qtbot, store, debounce_ms=60000)
    student_id = window.add_student("王小明")
    record_id = window.new_record(student_id, OCT_1)
    window.editor.zh_edit.setPlainText("關閉前輸入")
    window.close()
    assert store.get_record(record_id).zh_text == "關閉前輸入"


def test_quitting_flush_saves_pending_edit(qtbot, store):
    window = make_window(qtbot, store, debounce_ms=60000)
    student_id = window.add_student("王小明")
    record_id = window.new_record(student_id, OCT_1)
    window.editor.en_edit.setPlainText("typed before quit")
    window.flush()
    assert store.get_record(record_id).en_text == "typed before quit"


def test_selecting_another_student_saves_and_leaves_the_editor(qtbot, store):
    window = make_window(qtbot, store, debounce_ms=60000)
    store.add_student("陳美玲")
    student_id = window.add_student("王小明")
    record_id = window.new_record(student_id, OCT_1)
    window.editor.zh_edit.setPlainText("換人前輸入")
    window.student_list.setCurrentRow(1)  # 陳美玲; 王小明 sorts first and is selected
    assert store.get_record(record_id).zh_text == "換人前輸入"
    assert window.editor is None


def test_back_button_returns_to_the_students_cards(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.new_record(student_id, OCT_1)
    window.editor.back_btn.click()
    assert window.content.currentWidget() is window.student_view


def test_opening_a_card_opens_the_editor_for_that_record(qtbot, store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, OCT_1, "A校", "內容")
    window = make_window(qtbot, store)
    window.student_list.setCurrentRow(0)
    qtbot.mouseClick(window.student_view.stack.cards[0], Qt.MouseButton.LeftButton)
    assert window.editor.record_id == record.id


def test_export_saves_pending_edit_first(qtbot, store, monkeypatch):
    monkeypatch.setattr(main_window.ExportDialog, "exec", lambda self: 0)
    window = make_window(qtbot, store, debounce_ms=60000)
    student_id = window.add_student("王小明")
    record_id = window.new_record(student_id, OCT_1)
    window.editor.zh_edit.setPlainText("匯出前輸入")
    window.export_btn.click()
    assert store.get_record(record_id).zh_text == "匯出前輸入"


def test_import_applied_refreshes_open_editor(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    record_id = window.new_record(student_id, OCT_1)

    def fake_exec(dialog):
        store.set_en_texts({record_id: "Imported"})
        dialog.applied.emit(1)

    monkeypatch.setattr(main_window.ImportDialog, "exec", fake_exec)
    window.import_btn.click()
    assert window.editor.en_edit.toPlainText() == "Imported"


def test_date_mode_lists_children_seen_on_the_selected_day(qtbot, store):
    wang = store.add_student("王小明")
    chen = store.add_student("陳美玲")
    store.add_record(wang.id, OCT_1, "A校", "王")
    store.add_record(chen.id, OCT_1, "B校", "陳")
    store.add_record(wang.id, date(2026, 10, 8), "A校", "王二")
    window = make_window(qtbot, store)
    window.set_mode(DATE_MODE)
    window.calendar.setSelectedDate(QDate(2026, 10, 1))
    assert (window.content.currentWidget() is window.day_view, window.day_view.list.count()) == (True, 2)


def test_date_mode_marks_days_with_records(qtbot, store):
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    window.set_mode(DATE_MODE)
    window.calendar.setCurrentPage(2026, 10)
    assert OCT_1 in window.calendar.marked_dates()


def test_opening_a_child_from_the_day_list_opens_the_editor(qtbot, store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    window.set_mode(DATE_MODE)
    window.calendar.setSelectedDate(QDate(2026, 10, 1))
    rect = window.day_view.list.visualItemRect(window.day_view.list.item(0))
    qtbot.mouseClick(window.day_view.list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert window.editor.record_id == record.id


def test_back_from_editor_in_date_mode_returns_to_the_day_list(qtbot, store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    window.set_mode(DATE_MODE)
    window.open_record(record.id)
    window.editor.back_btn.click()
    assert window.content.currentWidget() is window.day_view


def test_new_record_marks_its_day_in_the_calendar(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.set_mode(DATE_MODE)
    window.calendar.setCurrentPage(2026, 10)
    window.new_record(student_id, date(2026, 10, 15))
    assert date(2026, 10, 15) in window.calendar.marked_dates()


def test_switching_mode_with_the_sidebar_control(qtbot, store):
    window = make_window(qtbot, store)
    window.mode_switch.button(1).click()
    assert (window.mode_switch.index(), window.sidebar_stack.currentWidget() is window.calendar) == (DATE_MODE, True)
    window.mode_switch.button(0).click()
    assert window.mode_switch.index() == STUDENT_MODE


def delete_from_card(window, index=0):
    window.student_list.setCurrentRow(0)
    window.student_view.stack.cards[index].context_menu().actions()[0].trigger()


def test_card_menu_deletes_the_record_after_confirming(qtbot, store, monkeypatch):
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_confirm_delete", lambda name, day: (name, day) == ("王小明", OCT_1))
    delete_from_card(window)
    assert store.records_for_student(student.id) == []
    assert window.student_view.stack.cards == []
    assert window.calendar.marked_dates() == set()


def test_declining_the_delete_prompt_keeps_the_record(qtbot, store, monkeypatch):
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_confirm_delete", lambda name, day: False)
    delete_from_card(window)
    assert len(store.records_for_student(student.id)) == 1
    assert len(window.student_view.stack.cards) == 1


def test_day_list_menu_deletes_the_record(qtbot, store, monkeypatch):
    wang = store.add_student("王小明")
    chen = store.add_student("陳美玲")
    store.add_record(wang.id, OCT_1, "A校", "王")
    store.add_record(chen.id, OCT_1, "B校", "陳")
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_confirm_delete", lambda name, day: True)
    window.set_mode(DATE_MODE)
    window.calendar.setSelectedDate(QDate(2026, 10, 1))
    rows = window.day_view.list
    rows.viewport().resize(400, 400)
    window.day_view.context_menu(rows.visualItemRect(rows.item(0)).center()).actions()[0].trigger()
    assert [r.student_id for r in store.records_on(OCT_1)] == [chen.id]
    assert rows.count() == 1


def test_day_list_has_no_menu_below_the_rows(qtbot, store):
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    window.set_mode(DATE_MODE)
    window.calendar.setSelectedDate(QDate(2026, 10, 1))
    rows = window.day_view.list
    below = rows.visualItemRect(rows.item(0)).bottomLeft() + QPoint(5, 200)
    assert window.day_view.context_menu(below) is None


def test_pencil_renames_the_student_everywhere(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小名")
    monkeypatch.setattr(window, "_ask_new_name", lambda current: "王小明")
    assert window.student_view.rename_btn.isVisible()
    window.student_view.rename_btn.click()
    assert student_names(window) == ["王小明"]
    assert window.current_student_id() == student_id
    assert window.student_view.title.text() == "王小明"


def test_empty_or_cancelled_rename_keeps_the_name(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    assert not window.rename_student(student_id, "  ")
    monkeypatch.setattr(window, "_ask_new_name", lambda current: "")
    assert not window.rename_student(student_id)
    assert store.get_student(student_id).name == "王小明"


def student_menu_action(window, text, row=0):
    rows = window.student_list
    rows.viewport().resize(300, 400)
    [action] = [a for a in window.student_menu(rows.visualItemRect(rows.item(row)).center()).actions()
                if a.text() == text]
    return action


def delete_from_student_list(window, row=0):
    student_menu_action(window, "刪除學生…", row).trigger()


def test_student_list_menu_deletes_the_student_and_records_after_warning(qtbot, store, monkeypatch):
    wang = store.add_student("王小明")
    store.add_student("陳美玲")
    store.add_record(wang.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_confirm_delete_student",
                        lambda name, count: (name, count) == ("王小明", 1))
    delete_from_student_list(window)
    assert student_names(window) == ["陳美玲"]
    assert store.records_on(OCT_1) == []
    assert window.calendar.marked_dates() == set()


def test_declining_the_student_delete_warning_keeps_the_student(qtbot, store, monkeypatch):
    wang = store.add_student("王小明")
    store.add_record(wang.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    monkeypatch.setattr(window, "_confirm_delete_student", lambda name, count: False)
    delete_from_student_list(window)
    assert student_names(window) == ["王小明"]
    assert len(store.records_for_student(wang.id)) == 1


def test_deleting_the_student_being_edited_closes_the_editor(qtbot, store, monkeypatch):
    wang = store.add_student("王小明")
    record = store.add_record(wang.id, OCT_1, "A校", "王")
    window = make_window(qtbot, store)
    window.open_record(record.id)
    monkeypatch.setattr(window, "_confirm_delete_student", lambda name, count: True)
    assert window.delete_student(wang.id)
    assert window.editor is None
    assert window.content.currentIndex() == main_window.PLACEHOLDER


def test_student_list_has_no_menu_below_the_rows(qtbot, store):
    store.add_student("王小明")
    window = make_window(qtbot, store)
    rows = window.student_list
    below = rows.visualItemRect(rows.item(0)).bottomLeft() + QPoint(5, 200)
    assert window.student_menu(below) is None


def test_profile_button_saves_the_edited_profile(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    asked = []
    monkeypatch.setattr(window, "_ask_profile",
                        lambda name, current: asked.append((name, current)) or StudentProfile(grade="3"))
    window.student_view.profile_btn.click()
    assert asked == [("王小明", StudentProfile())]
    assert store.get_profile(student_id) == StudentProfile(grade="3")


def test_cancelled_profile_dialog_keeps_the_profile(qtbot, store, monkeypatch):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    store.set_profile(student_id, StudentProfile(grade="3"))
    monkeypatch.setattr(window, "_ask_profile", lambda name, current: None)
    assert not window.edit_profile(student_id)
    assert store.get_profile(student_id) == StudentProfile(grade="3")


def test_moving_a_record_updates_the_calendar(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.new_record(student_id, OCT_1)
    window.editor.change_date(date(2026, 10, 3))
    window.calendar.setCurrentPage(2026, 10)
    assert date(2026, 10, 3) in window.calendar.marked_dates()
    assert OCT_1 not in window.calendar.marked_dates()


def location_names(window):
    return [window.location_list.item(i).text() for i in range(window.location_list.count())]


def test_location_mode_lists_places_and_their_records_newest_first(qtbot, store):
    amy = store.add_student("Amy")
    ming = store.add_student("王小明")
    store.add_record(amy.id, date(2026, 10, 1), "新竹國小", "一")
    store.add_record(ming.id, date(2026, 10, 8), "新竹國小", "二")
    store.add_record(ming.id, date(2026, 10, 9), "台北診所", "三")
    store.add_record(amy.id, date(2026, 10, 2), "", "四")
    window = make_window(qtbot, store)
    window.mode_switch.button(LOCATION_MODE).click()
    assert window.sidebar_stack.currentWidget() is window.location_list
    assert location_names(window) == ["台北診所", "新竹國小", "未填地點"]
    window.location_list.setCurrentRow(1)
    view = window.location_view
    assert window.content.currentWidget() is view
    assert (view.title.text(), view.count.text()) == ("新竹國小", "2 位學生")
    assert [view.students.item(i).text() for i in range(view.students.count())] == ["王小明", "Amy"]
    window.location_list.setCurrentRow(2)
    assert view.students.count() == 1


def test_location_mode_lists_a_student_located_there_before_their_first_visit(qtbot, store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(location="新竹國小"))
    window = make_window(qtbot, store)
    window.set_mode(LOCATION_MODE)
    view = window.location_view
    assert location_names(window) == ["新竹國小"]
    assert [view.students.item(i).text() for i in range(view.students.count())] == ["王小明"]


def test_location_mode_clicking_a_student_shows_all_their_records(qtbot, store):
    ming = store.add_student("王小明")
    store.add_record(ming.id, date(2026, 10, 1), "新竹國小", "一")
    store.add_record(ming.id, date(2026, 10, 8), "新竹國小", "二")
    store.add_record(ming.id, date(2026, 10, 9), "台北診所", "三")
    window = make_window(qtbot, store)
    window.set_mode(LOCATION_MODE)
    window.location_list.setCurrentRow(1)
    view = window.location_view
    assert view.back_btn.isHidden()
    view.students.itemClicked.emit(view.students.item(0))
    assert (view.pages.currentWidget() is view.list, view.title.text(), view.count.text()) == (
        True, "王小明", "3 份病歷（所有地點）")
    assert [(view.list.item(i).data(NAME_ROLE), view.list.item(i).data(PLACE_ROLE))
            for i in range(view.list.count())] == [
        ("2026-10-09  週五", "台北診所"), ("2026-10-08  週四", "新竹國小"), ("2026-10-01  週四", "新竹國小")]
    assert not view.back_btn.isHidden()
    view.list.itemClicked.emit(view.list.item(0))
    window.editor.close_editor()
    assert (window.content.currentWidget() is view, view.list.count()) == (True, 3)
    view.back_btn.click()
    assert (view.pages.currentWidget() is view.students, view.title.text()) == (True, "新竹國小")


def test_student_menu_makes_a_student_inactive_and_lists_them_last_in_grey(qtbot, store):
    store.add_student("Amy")
    store.add_student("王小明")
    window = make_window(qtbot, store)
    student_menu_action(window, "停用學生", row=0).trigger()
    assert student_names(window) == ["王小明", "Amy（停用）"]
    assert not store.students()[0].active


def test_student_menu_makes_an_inactive_student_active_again(qtbot, store):
    amy = store.add_student("Amy")
    store.set_active(amy.id, False)
    window = make_window(qtbot, store)
    student_menu_action(window, "啟用學生").trigger()
    assert student_names(window) == ["Amy"]


def timetable_names(window):
    return [b.text().split("\n")[0] for b in window.timetable_view.slot_buttons]


def test_timetable_mode_shows_active_students_by_session_time(qtbot, store):
    amy, ming = store.add_student("Amy"), store.add_student("王小明")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"),)))
    store.set_profile(ming.id, StudentProfile(sessions=(Session(0, "09:00", "09:30"),)))
    window = make_window(qtbot, store)
    window.set_mode(3)
    assert window.content.currentWidget() is window.timetable_view
    assert timetable_names(window) == ["王小明", "Amy"]


def test_an_inactive_student_leaves_the_timetable(qtbot, store):
    amy = store.add_student("Amy")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"),)))
    window = make_window(qtbot, store)
    window.set_mode(3)
    window.set_active(amy.id, False)
    assert timetable_names(window) == []


def test_clicking_a_student_in_the_timetable_shows_all_their_charts(qtbot, store):
    amy = store.add_student("Amy")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"),)))
    store.add_record(amy.id, OCT_1, "A校", "第一次")
    store.add_record(amy.id, date(2026, 10, 8), "A校", "第二次")
    window = make_window(qtbot, store)
    window.set_mode(3)
    window.timetable_view.slot_buttons[0].click()
    assert window.timetable_view.student_id == amy.id
    assert window.timetable_view.student_view.count.text() == "2 份病歷"


def test_a_chart_opened_from_the_timetable_returns_to_the_students_charts(qtbot, store):
    amy = store.add_student("Amy")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"),)))
    record = store.add_record(amy.id, OCT_1, "A校", "第一次")
    window = make_window(qtbot, store)
    window.set_mode(3)
    window.timetable_view.slot_buttons[0].click()
    window.timetable_view.open_record.emit(record.id)
    assert window.content.currentWidget() is window.editor
    window.editor.back_btn.click()
    assert window.content.currentWidget() is window.timetable_view
    assert window.timetable_view.student_id == amy.id


def test_changing_session_times_from_the_timetable_updates_it(qtbot, store, monkeypatch):
    amy = store.add_student("Amy")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"),)))
    window = make_window(qtbot, store)
    window.set_mode(3)
    window.timetable_view.slot_buttons[0].click()
    monkeypatch.setattr(window, "_ask_profile", lambda name, current: replace(
        current, sessions=(Session(1, "13:00", "13:30"),)))
    window.timetable_view.student_view.profile_btn.click()
    window.timetable_view.back_btn.click()
    assert [b.text() for b in window.timetable_view.slot_buttons] == ["Amy\n1:00 PM–1:30 PM"]


def test_timetable_sidebar_lists_active_students_without_a_session_time(qtbot, store):
    amy, _, lin = store.add_student("Amy"), store.add_student("王小明"), store.add_student("林曉華")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"),)))
    store.set_active(lin.id, False)
    window = make_window(qtbot, store)
    window.set_mode(3)
    assert [window.unscheduled_list.item(i).text() for i in range(window.unscheduled_list.count())] == ["王小明"]


def timetable_cells(window, kind):
    return [c for c in window.timetable_view.scroll.widget().findChildren(QFrame, "ttCell")
            if c.property("kind") == kind]


def test_timetable_frames_every_weekday_and_time_even_when_empty(qtbot, store):
    amy = store.add_student("Amy")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"), Session(0, "13:00", "13:30"))))
    window = make_window(qtbot, store)
    window.set_mode(3)
    assert (len(timetable_cells(window, "time")), len(timetable_cells(window, "plain")),
            len(timetable_cells(window, "band"))) == (2, 5, 5)


def test_timetable_shades_every_other_time_row(qtbot, store):
    amy = store.add_student("Amy")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(0, "09:00", "09:30"), Session(0, "13:00", "13:30"))))
    window = make_window(qtbot, store)
    window.set_mode(3)
    button = window.timetable_view.slot_buttons[1]  # the 13:00 row, the second one
    assert button.parent().property("kind") == "band"


def test_timetable_shows_the_classroom_to_fetch_the_student_from(qtbot, store):
    amy = store.add_student("Amy")
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:30", "301"),)))
    window = make_window(qtbot, store)
    window.set_mode(3)
    assert [b.text() for b in window.timetable_view.slot_buttons] == ["Amy\n10:00 AM–10:30 AM\n領取教室：301"]

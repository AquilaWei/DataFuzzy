from datetime import date, timedelta

import pytest

from datafuzzy.ot.db import RecordStore, Session, StudentProfile
from datafuzzy.ot.schedule import Slot
from datafuzzy.ot.ui.date_view import DayRecordsView
from datafuzzy.ot.ui.schedule_dialogs import (
    CancelDialog,
    ClashDialog,
    DayOffDialog,
    PostponeDialog,
)
from datafuzzy.ot.ui.timetable_view import TimetableView

KEY = bytes(range(32))
MONDAY = date(2026, 11, 23)


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


@pytest.fixture
def wang(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(location="新竹國小", sessions=(Session(0, "09:00", "09:30"),)))
    return student


def untick(dialog, row):
    dialog.rows.boxes[row].setChecked(False)


def test_day_off_dialog_starts_with_every_session_ticked(qtbot):
    slots = [("王小明", Slot(1, "09:00", "09:30")), ("陳美玲", Slot(2, "10:00", "10:30"))]
    dialog = DayOffDialog("Therapist Absent", 0, [MONDAY, date(2026, 11, 30)], slots)
    qtbot.addWidget(dialog)
    assert dialog.choice() == (MONDAY, [Slot(1, "09:00", "09:30"), Slot(2, "10:00", "10:30")])


def test_day_off_dialog_leaves_out_unticked_students(qtbot):
    slots = [("王小明", Slot(1, "09:00", "09:30")), ("陳美玲", Slot(2, "10:00", "10:30"))]
    dialog = DayOffDialog("Therapist Absent", 0, [MONDAY], slots)
    qtbot.addWidget(dialog)
    untick(dialog, 0)
    assert dialog.choice()[1] == [Slot(2, "10:00", "10:30")]


def test_day_off_dialog_cannot_go_on_with_no_one_ticked(qtbot):
    dialog = DayOffDialog("Therapist Absent", 0, [MONDAY], [("王小明", Slot(1, "09:00", "09:30"))])
    qtbot.addWidget(dialog)
    untick(dialog, 0)
    assert not dialog.ok_button.isEnabled()


def test_untick_all_leaves_no_row_ticked(qtbot):
    slots = [("王小明", Slot(1, "09:00", "09:30")), ("陳美玲", Slot(2, "10:00", "10:30"))]
    dialog = DayOffDialog("Therapist Absent", 0, [MONDAY], slots)
    qtbot.addWidget(dialog)
    dialog.rows.none_btn.click()
    assert dialog.choice()[1] == []


def test_tick_all_ticks_every_row_again(qtbot):
    slots = [("王小明", Slot(1, "09:00", "09:30")), ("陳美玲", Slot(2, "10:00", "10:30"))]
    dialog = DayOffDialog("Therapist Absent", 0, [MONDAY], slots)
    qtbot.addWidget(dialog)
    untick(dialog, 0)
    dialog.rows.all_btn.click()
    assert dialog.choice()[1] == [Slot(1, "09:00", "09:30"), Slot(2, "10:00", "10:30")]


def test_clash_dialog_can_go_on_with_none_ticked_to_replace_them_all(qtbot, store, wang):
    booked = store.add_record(wang.id, MONDAY)
    dialog = ClashDialog(MONDAY, [booked], {wang.id: wang.name})
    qtbot.addWidget(dialog)
    untick(dialog, 0)
    assert (dialog.ok_button.isEnabled(), dialog.choice()) == (True, [])


def test_postpone_dialog_defaults_to_one_week_and_every_booking(qtbot, store, wang):
    booked = store.add_record(wang.id, MONDAY)
    dialog = PostponeDialog([booked], {wang.id: wang.name})
    qtbot.addWidget(dialog)
    assert dialog.choice() == (1, [booked.id])


def test_cancel_dialog_replaces_unless_asked_to_postpone_first(qtbot, store, wang):
    booked = store.add_record(wang.id, MONDAY)
    dialog = CancelDialog([booked], {wang.id: wang.name})
    qtbot.addWidget(dialog)
    assert (dialog.choice(), dialog.weeks.isEnabled()) == (("School Not in Session", None, [booked.id]), False)


def test_cancel_dialog_gives_the_weeks_when_postponing_first(qtbot, store, wang):
    booked = store.add_record(wang.id, MONDAY)
    dialog = CancelDialog([booked], {wang.id: wang.name})
    qtbot.addWidget(dialog)
    dialog.move_first.setChecked(True)
    dialog.weeks.setCurrentIndex(2)
    dialog.reason.setCurrentIndex(2)
    assert dialog.choice() == ("Unavailable Student", 3, [booked.id])


def make_timetable(qtbot, store):
    view = TimetableView(store)
    qtbot.addWidget(view)
    return view


def test_timetable_weekday_menu_offers_the_three_reasons(qtbot, store, wang):
    view = make_timetable(qtbot, store)
    assert [a.text() for a in view.weekday_menu(0).actions()] == \
        ["School Not in Session", "Therapist Absent", "Unavailable Student"]


def test_timetable_weekday_menu_is_disabled_on_a_day_no_one_comes(qtbot, store, wang):
    view = make_timetable(qtbot, store)
    assert [a.isEnabled() for a in view.weekday_menu(1).actions()] == [False, False, False]


def test_timetable_offers_a_day_off_on_monday_to_friday_headings(qtbot, store, wang):
    view = make_timetable(qtbot, store)
    assert sorted(view.weekday_heads) == [0, 1, 2, 3, 4]


def test_timetable_day_off_adds_the_reason_charts(qtbot, store, wang, monkeypatch):
    view = make_timetable(qtbot, store)
    monkeypatch.setattr(view, "_ask_day_off", lambda *_: (MONDAY, [Slot(wang.id, "09:00", "09:30")]))
    with qtbot.waitSignal(view.records_changed):
        view.day_off(0, "School Not in Session")
    assert [(r.session_type, r.start_time) for r in store.records_on(MONDAY)] == [("School Not in Session", "09:00")]


def test_timetable_day_off_asks_about_charts_already_there(qtbot, store, wang, monkeypatch):
    booked = store.add_record(wang.id, MONDAY, zh_text="原本的")
    view = make_timetable(qtbot, store)
    monkeypatch.setattr(view, "_ask_day_off", lambda *_: (MONDAY, [Slot(wang.id, "09:00", "09:30")]))
    monkeypatch.setattr(view, "_ask_clashes", lambda day, records: [r.id for r in records])
    view.day_off(0, "Therapist Absent")
    assert store.get_record(booked.id).visit_date == date(2026, 11, 30)


def test_timetable_day_off_changes_nothing_when_the_clash_question_is_cancelled(qtbot, store, wang, monkeypatch):
    store.add_record(wang.id, MONDAY, zh_text="原本的")
    view = make_timetable(qtbot, store)
    monkeypatch.setattr(view, "_ask_day_off", lambda *_: (MONDAY, [Slot(wang.id, "09:00", "09:30")]))
    monkeypatch.setattr(view, "_ask_clashes", lambda *_: None)
    view.day_off(0, "Therapist Absent")
    assert [r.zh_text for r in store.records_on(MONDAY)] == ["原本的"]


def make_day_view(qtbot, store, day):
    view = DayRecordsView(store)
    qtbot.addWidget(view)
    view.show()
    view.show_day(day)
    return view


def test_day_view_offers_postpone_and_cancel_for_a_coming_day_with_bookings(qtbot, store, wang):
    day = date.today() + timedelta(days=3)
    store.add_record(wang.id, day)
    view = make_day_view(qtbot, store, day)
    assert (view.postpone_btn.isVisible(), view.cancel_btn.isVisible()) == (True, True)


def test_day_view_offers_neither_for_a_past_day(qtbot, store, wang):
    day = date.today() - timedelta(days=1)
    store.add_record(wang.id, day)
    view = make_day_view(qtbot, store, day)
    assert (view.postpone_btn.isVisible(), view.cancel_btn.isVisible()) == (False, False)


def test_day_view_offers_neither_for_a_coming_day_without_bookings(qtbot, store, wang):
    view = make_day_view(qtbot, store, date.today() + timedelta(days=3))
    assert (view.postpone_btn.isVisible(), view.cancel_btn.isVisible()) == (False, False)


def test_day_view_postpone_moves_the_picked_bookings(qtbot, store, wang, monkeypatch):
    day = date.today() + timedelta(days=3)
    booked = store.add_record(wang.id, day)
    view = make_day_view(qtbot, store, day)
    monkeypatch.setattr(view, "_ask_postpone", lambda records: (2, [booked.id]))
    with qtbot.waitSignal(view.records_changed):
        view.postpone_bookings()
    assert store.get_record(booked.id).visit_date == day + timedelta(weeks=2)


def test_day_view_cancel_replaces_the_picked_bookings(qtbot, store, wang, monkeypatch):
    day = date.today() + timedelta(days=3)
    booked = store.add_record(wang.id, day, zh_text="原本的")
    view = make_day_view(qtbot, store, day)
    monkeypatch.setattr(view, "_ask_cancel", lambda records: ("Therapist Absent", None, [booked.id]))
    view.cancel_bookings()
    assert [(r.session_type, r.zh_text) for r in store.records_on(day)] == [("Therapist Absent", "")]

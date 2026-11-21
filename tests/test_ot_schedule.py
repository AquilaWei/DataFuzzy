from datetime import date

import pytest

from datafuzzy.ot.db import RecordStore, Session, StudentProfile
from datafuzzy.ot.schedule import (
    Slot,
    cancel,
    cancel_day,
    clashes,
    postpone,
    weekday_dates,
    weekday_slots,
)

KEY = bytes(range(32))
MONDAY = date(2026, 11, 23)


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


def scheduled(store, name, *sessions, location="新竹國小"):
    student = store.add_student(name)
    store.set_profile(student.id, StudentProfile(location=location, sessions=tuple(sessions)))
    return student


def test_weekday_dates_are_the_coming_month_of_that_weekday():
    assert weekday_dates(0, date(2026, 11, 21)) == [date(2026, 11, 23), date(2026, 11, 30), date(2026, 12, 7),
                                                    date(2026, 12, 14), date(2026, 12, 21)]


def test_weekday_dates_start_today_when_today_is_that_weekday():
    assert weekday_dates(0, MONDAY)[0] == MONDAY


def test_weekday_dates_stay_within_31_days():
    assert weekday_dates(0, date(2026, 11, 25)) == [date(2026, 11, 30), date(2026, 12, 7), date(2026, 12, 14),
                                                    date(2026, 12, 21)]


def test_weekday_slots_are_the_active_students_sessions_of_that_weekday(store):
    wang = scheduled(store, "王小明", Session(0, "09:00", "09:30"), Session(2, "10:00", "10:30"))
    chen = scheduled(store, "陳美玲", Session(0, "08:00", "08:30"))
    away = scheduled(store, "林大同", Session(0, "11:00", "11:30"))
    store.set_active(away.id, False)
    assert weekday_slots(store, 0) == [("陳美玲", Slot(chen.id, "08:00", "08:30")),
                                       ("王小明", Slot(wang.id, "09:00", "09:30"))]


def test_cancel_day_gives_each_slot_a_chart_of_the_reason(store):
    wang = scheduled(store, "王小明", Session(0, "09:00", "09:30"))
    (made,) = cancel_day(store, MONDAY, "School Not in Session", [Slot(wang.id, "09:00", "09:30")])
    assert (made.visit_date, made.session_type, made.start_time, made.end_time, made.location) == \
        (MONDAY, "School Not in Session", "09:00", "09:30", "新竹國小")


def test_cancel_day_moves_a_ticked_clash_a_week_on(store):
    wang = scheduled(store, "王小明", Session(0, "09:00", "09:30"))
    booked = store.add_record(wang.id, MONDAY, zh_text="原本的")
    cancel_day(store, MONDAY, "Therapist Absent", [Slot(wang.id, "09:00", "09:30")], move_ids=[booked.id])
    assert store.get_record(booked.id).visit_date == date(2026, 11, 30)


def test_cancel_day_replaces_an_unticked_clash(store):
    wang = scheduled(store, "王小明", Session(0, "09:00", "09:30"))
    store.add_record(wang.id, MONDAY, zh_text="原本的")
    cancel_day(store, MONDAY, "Therapist Absent", [Slot(wang.id, "09:00", "09:30")])
    assert [r.session_type for r in store.records_on(MONDAY)] == ["Therapist Absent"]


def test_cancel_day_leaves_other_students_charts_alone(store):
    wang = scheduled(store, "王小明", Session(0, "09:00", "09:30"))
    chen = scheduled(store, "陳美玲", Session(0, "08:00", "08:30"))
    other = store.add_record(chen.id, MONDAY)
    cancel_day(store, MONDAY, "Therapist Absent", [Slot(wang.id, "09:00", "09:30")])
    assert store.get_record(other.id).visit_date == MONDAY


def test_cancel_day_refuses_another_reason_before_changing_anything(store):
    wang = scheduled(store, "王小明", Session(0, "09:00", "09:30"))
    store.add_record(wang.id, MONDAY)
    with pytest.raises(ValueError):
        cancel_day(store, MONDAY, "Direct Therapy Time", [Slot(wang.id, "09:00", "09:30")])
    assert len(store.records_on(MONDAY)) == 1


def test_clashes_are_the_students_records_of_the_day_by_start(store):
    wang = scheduled(store, "王小明")
    late = store.add_record(wang.id, MONDAY, start_time="13:00")
    early = store.add_record(wang.id, MONDAY, start_time="09:00")
    assert [r.id for r in clashes(store, MONDAY, {wang.id})] == [early.id, late.id]


def test_postpone_moves_records_by_whole_weeks_keeping_the_chart(store):
    wang = scheduled(store, "王小明")
    booked = store.add_record(wang.id, MONDAY, zh_text="原本的", start_time="09:00")
    postpone(store, [booked.id], 2)
    moved = store.get_record(booked.id)
    assert (moved.visit_date, moved.zh_text, moved.start_time) == (date(2026, 12, 7), "原本的", "09:00")


def test_cancel_without_weeks_replaces_the_booking(store):
    wang = scheduled(store, "王小明")
    booked = store.add_record(wang.id, MONDAY, "新竹國小", zh_text="原本的", start_time="09:00", end_time="09:30")
    (made,) = cancel(store, [booked.id], "Unavailable Student")
    assert [(r.id, r.session_type, r.zh_text, r.start_time, r.location) for r in store.records_on(MONDAY)] == \
        [(made.id, "Unavailable Student", "", "09:00", "新竹國小")]


def test_cancel_with_weeks_moves_the_booking_and_leaves_the_reason_on_the_day(store):
    wang = scheduled(store, "王小明")
    booked = store.add_record(wang.id, MONDAY, zh_text="原本的", start_time="09:00")
    cancel(store, [booked.id], "School Not in Session", weeks=1)
    assert (store.get_record(booked.id).visit_date, [r.session_type for r in store.records_on(MONDAY)]) == \
        (date(2026, 11, 30), ["School Not in Session"])


def test_cancel_keeps_a_group_booking_a_group_chart(store):
    wang = scheduled(store, "王小明")
    booked = store.add_record(wang.id, MONDAY, session_mode="group")
    (made,) = cancel(store, [booked.id], "Therapist Absent")
    assert made.session_mode == "group"

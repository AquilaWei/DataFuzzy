from datetime import date

import pytest
from PySide6.QtCore import QDate, Qt

from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.ui.date_view import (
    NAME_ROLE,
    PLACE_ROLE,
    PREVIEW_ROLE,
    TIME_ROLE,
    DayRecordDelegate,
    DayRecordsView,
    MarkedCalendar,
)

KEY = bytes(range(32))


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


@pytest.fixture
def seen(store):
    """Two children on Oct 1, one on Oct 8 and one in November."""
    wang = store.add_student("王小明")
    chen = store.add_student("陳美玲")
    store.add_record(wang.id, date(2026, 10, 1), "新竹國小", "王的第一次\n第二行")
    store.add_record(chen.id, date(2026, 10, 1), "台北診所", "陳的第一次")
    store.add_record(wang.id, date(2026, 10, 8), "新竹國小", "王的第二次")
    store.add_record(wang.id, date(2026, 11, 3), "新竹國小", "十一月")
    return store


def make_calendar(qtbot, store, month=(2026, 10)):
    calendar = MarkedCalendar(store)
    qtbot.addWidget(calendar)
    calendar.setCurrentPage(*month)
    return calendar


def make_day_view(qtbot, store, day):
    view = DayRecordsView(store)
    qtbot.addWidget(view)
    view.show()
    view.show_day(day)
    return view


def item_texts(view):
    return [view.list.item(i).text() for i in range(view.list.count())]


def test_calendar_marks_days_with_records_in_the_shown_month(qtbot, seen):
    calendar = make_calendar(qtbot, seen)
    assert {d for d in calendar.marked_dates() if d.month == 10} == {date(2026, 10, 1), date(2026, 10, 8)}


def test_calendar_moves_markers_when_the_page_changes(qtbot, seen):
    calendar = make_calendar(qtbot, seen)
    calendar.setCurrentPage(2026, 11)
    assert date(2026, 11, 3) in calendar.marked_dates()


def test_calendar_shows_no_marker_for_a_month_without_records(qtbot, seen):
    calendar = make_calendar(qtbot, seen, month=(2026, 3))
    assert calendar.marked_dates() == set()


def test_calendar_marks_a_day_after_a_record_is_added(qtbot, seen):
    calendar = make_calendar(qtbot, seen)
    student = seen.students()[0]
    seen.add_record(student.id, date(2026, 10, 20))
    calendar.refresh_markers()
    assert date(2026, 10, 20) in calendar.marked_dates()


def test_calendar_reports_the_selected_day(qtbot, seen):
    calendar = make_calendar(qtbot, seen)
    calendar.setSelectedDate(QDate(2026, 10, 8))
    assert calendar.selected() == date(2026, 10, 8)


def test_day_view_lists_children_with_a_record_sorted_by_name(qtbot, seen):
    view = make_day_view(qtbot, seen, date(2026, 10, 1))
    assert item_texts(view) == ["王小明\n新竹國小 · 王的第一次", "陳美玲\n台北診所 · 陳的第一次"]


def test_day_view_sorts_by_time_or_by_name(qtbot, store):
    names = ["陳美玲", "王小明", "Amy"]
    for name, start in zip(names, ["14:00", "", "09:30"]):
        record = store.add_record(store.add_student(name).id, date(2026, 10, 1))
        store.update_record(record.id, start_time=start)
    view = make_day_view(qtbot, store, date(2026, 10, 1))
    first_names = lambda: [t.split("\n")[0] for t in item_texts(view)]
    assert first_names() == ["Amy", "陳美玲", "王小明"]
    view.sort.button(1).click()
    assert first_names() == sorted(names, key=[s.name for s in store.students()].index)


def test_day_view_rows_keep_name_place_and_preview_apart(qtbot, seen):
    view = make_day_view(qtbot, seen, date(2026, 10, 1))
    item = view.list.item(0)
    assert [item.data(r) for r in (NAME_ROLE, PLACE_ROLE, PREVIEW_ROLE)] == ["王小明", "新竹國小", "王的第一次"]
    assert item.data(TIME_ROLE) == ("", "")
    assert isinstance(view.list.itemDelegate(), DayRecordDelegate)
    assert view.list.visualItemRect(item).height() > view.fontMetrics().height() * 2


def test_day_view_header_gives_date_and_count(qtbot, seen):
    view = make_day_view(qtbot, seen, date(2026, 10, 1))
    assert (view.title.text(), view.count.text()) == ("2026-10-01  週四", "2 位學生有病歷")


def test_day_view_leaves_out_children_seen_on_other_days(qtbot, seen):
    view = make_day_view(qtbot, seen, date(2026, 10, 8))
    assert item_texts(view) == ["王小明\n新竹國小 · 王的第二次"]


def test_day_view_without_records_shows_hint(qtbot, seen):
    view = make_day_view(qtbot, seen, date(2026, 10, 2))
    assert (view.empty.isVisible(), view.list.count()) == (True, 0)


def test_clicking_a_child_opens_that_record(qtbot, seen):
    view = make_day_view(qtbot, seen, date(2026, 10, 1))
    rect = view.list.visualItemRect(view.list.item(1))
    with qtbot.waitSignal(view.open_record, timeout=1000) as opened:
        qtbot.mouseClick(view.list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert opened.args == [2]


def test_day_view_refresh_shows_a_new_record(qtbot, seen):
    view = make_day_view(qtbot, seen, date(2026, 10, 8))
    third = seen.add_student("林曉華")
    seen.add_record(third.id, date(2026, 10, 8), "", "新增")
    view.refresh()
    assert view.list.count() == 2


def test_day_view_rows_carry_the_start_and_end_for_the_time_column(qtbot, store):
    record = store.add_record(store.add_student("王小明").id, date(2026, 10, 1), start_time="09:30", end_time="10:00")
    view = make_day_view(qtbot, store, record.visit_date)
    assert view.list.item(0).data(TIME_ROLE) == ("9:30 AM", "10:00 AM")

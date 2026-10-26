from datafuzzy.ot.db import Session, Student
from datafuzzy.ot.ui.timetable_view import timetable_grid

AMY, MING = Student(1, "Amy"), Student(2, "王小明")


def test_grid_has_monday_to_friday_without_weekend_sessions():
    weekdays, _, _ = timetable_grid([(Session(4, "10:00", "10:30"), AMY)])
    assert weekdays == [0, 1, 2, 3, 4]


def test_grid_adds_a_weekend_day_that_has_a_session():
    weekdays, _, _ = timetable_grid([(Session(5, "10:00", "10:30"), AMY)])
    assert weekdays == [0, 1, 2, 3, 4, 5]


def test_grid_rows_are_the_distinct_start_times():
    _, starts, _ = timetable_grid([(Session(0, "14:00", "14:30"), AMY), (Session(4, "09:00", "09:30"), MING),
                                   (Session(2, "14:00", "14:45"), MING)])
    assert starts == ["09:00", "14:00"]


def test_students_starting_together_share_a_cell():
    slots = [(Session(4, "10:00", "10:30"), AMY), (Session(4, "10:00", "10:45"), MING)]
    _, _, cells = timetable_grid(slots)
    assert cells == {(4, "10:00"): slots}

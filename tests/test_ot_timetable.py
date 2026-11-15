from datafuzzy.ot.db import Session, Student
from datafuzzy.ot.ui.timetable_view import cell_chips, timetable_grid

AMY, MING, LIN = Student(1, "Amy"), Student(2, "王小明"), Student(3, "林曉華")


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


def test_group_students_of_one_time_share_a_tile():
    slots = [(Session(4, "10:00", "10:30"), AMY), (Session(4, "10:00", "10:30"), MING)]
    assert cell_chips(slots, {1, 2}) == [slots]


def test_a_group_student_and_an_individual_one_of_one_time_keep_their_own_tiles():
    slots = [(Session(4, "10:00", "10:30"), AMY), (Session(4, "10:00", "10:30"), MING)]
    assert cell_chips(slots, {1}) == [[slots[0]], [slots[1]]]


def test_group_students_ending_at_different_times_keep_their_own_tiles():
    slots = [(Session(4, "10:00", "10:30"), AMY), (Session(4, "10:00", "10:45"), MING)]
    assert cell_chips(slots, {1, 2}) == [[slots[0]], [slots[1]]]


def test_a_lone_group_student_keeps_an_own_tile():
    slots = [(Session(4, "10:00", "10:30"), AMY)]
    assert cell_chips(slots, {1}) == [slots]


def test_a_group_tile_sits_where_its_first_student_is():
    slots = [(Session(4, "10:00", "10:30"), AMY), (Session(4, "10:00", "10:45"), LIN),
             (Session(4, "10:00", "10:30"), MING)]
    assert cell_chips(slots, {1, 2}) == [[slots[0], slots[2]], [slots[1]]]

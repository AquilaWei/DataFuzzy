from datetime import date

from PySide6.QtCore import QDate

from datafuzzy.ot.db import Session, StudentProfile
from datafuzzy.ot.ui.profile_dialog import ProfileSummary, StudentProfileDialog


def test_dialog_starts_from_the_saved_profile(qtbot):
    saved = StudentProfile(diagnosis="ADHD, ODD", age="8", grade="3", classroom="301",
                           case_manager="Ms. Lee", school_year="09/2025-06/2026", goals="Fine motor",
                           location="新竹國小")
    dialog = StudentProfileDialog("王小明", saved, today=date(2026, 10, 26))
    qtbot.addWidget(dialog)
    assert dialog.profile() == saved


def test_new_profile_starts_with_the_current_school_year(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 26))
    qtbot.addWidget(dialog)
    assert dialog.profile().school_year == "09/2026-06/2027"


def test_school_year_months_are_picked_by_month_and_year(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 26))
    qtbot.addWidget(dialog)
    dialog.year_from.setDate(QDate(2026, 8, 1))
    dialog.year_to.setDate(QDate(2027, 7, 1))
    assert dialog.profile().school_year == "08/2026-07/2027"


def test_location_drop_down_offers_the_known_locations(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 26),
                                  locations=["A校", "B校"])
    qtbot.addWidget(dialog)
    assert [dialog.location.itemText(i) for i in range(dialog.location.count())] == ["A校", "B校"]
    dialog.location.setEditText("C校")
    assert dialog.profile().location == "C校"


def test_session_times_can_be_added_as_many_as_needed(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    friday = dialog.sessions.add_row()
    friday.weekday.setCurrentIndex(4)
    friday.start.setEditText("10:00 AM")
    monday = dialog.sessions.add_row()
    monday.start.setEditText("2:00 PM")
    monday.end.setEditText("2:45 PM")
    assert dialog.profile().sessions == (Session(4, "10:00", "10:30"), Session(0, "14:00", "14:45"))


def test_a_session_ends_30_minutes_after_its_start_until_the_end_is_changed(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    row = dialog.sessions.add_row()
    row.start.setEditText("10:00 AM")
    assert row.end.currentText() == "10:30 AM"
    row.end.setEditText("11:00 AM")
    row.start.setEditText("10:15 AM")
    assert row.end.currentText() == "11:00 AM"


def test_a_session_time_can_be_removed(qtbot):
    profile = StudentProfile(sessions=(Session(4, "10:00", "10:30"), Session(0, "14:00", "14:30")))
    dialog = StudentProfileDialog("王小明", profile, today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    dialog.sessions.rows[0].remove_btn.click()
    assert dialog.profile().sessions == (Session(0, "14:00", "14:30"),)


def test_a_blank_session_row_is_left_out(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    dialog.sessions.add_row()
    assert dialog.profile().sessions == ()


def test_an_unreadable_session_time_keeps_the_dialog_open(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    dialog.sessions.add_row().start.setEditText("10點")
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert "9:30 AM" in dialog.problem.text()


def test_summary_lists_the_session_times(qtbot):
    summary = ProfileSummary()
    qtbot.addWidget(summary)
    summary.show_profile("王小明", StudentProfile(sessions=(Session(0, "14:00", "14:30"), Session(4, "10:00", "10:30"))))
    assert summary.values["sessions"].text() == "週一 2:00 PM–2:30 PM、週五 10:00 AM–10:30 AM"


def test_a_session_can_name_the_classroom_to_fetch_the_student_from(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1), classrooms=["301", "資源班"])
    qtbot.addWidget(dialog)
    row = dialog.sessions.add_row()
    row.start.setEditText("10:00 AM")
    assert [row.classroom.itemText(i) for i in range(row.classroom.count())] == ["301", "資源班"]
    row.classroom.setEditText("302")
    assert dialog.profile().sessions == (Session(0, "10:00", "10:30", "302"),)


def test_summary_shows_the_classroom_of_a_session(qtbot):
    summary = ProfileSummary()
    qtbot.addWidget(summary)
    summary.show_profile("王小明", StudentProfile(sessions=(Session(4, "10:00", "10:30", "301"),)))
    assert summary.values["sessions"].text() == "週五 10:00 AM–10:30 AM（教室：301）"

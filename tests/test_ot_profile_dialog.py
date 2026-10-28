from datetime import date

from PySide6.QtCore import QDate

from datafuzzy.ot.db import Plan, Session, StudentProfile
from datafuzzy.ot.ui.profile_dialog import ProfileSummary, StudentProfileDialog


def test_dialog_starts_from_the_saved_profile(qtbot):
    saved = StudentProfile(diagnosis="ADHD, ODD", age="8", grade="3", classroom="301",
                           case_manager="Ms. Lee", school_year="09/2025-06/2026", goals=("Fine motor", "Self-care"),
                           location="新竹國小", plan_504=True, plan_date="10/15/2026")
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
    assert summary.values["sessions"].text() == "週五 10:00 AM–10:30 AM（領取教室：301）"


def test_goals_can_be_added_as_many_as_needed(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    dialog.goals.add_row().edit.setPlainText("剪直線")
    dialog.goals.add_row().edit.setPlainText("扣釦子")
    assert dialog.profile().goals == ("剪直線", "扣釦子")


def test_removing_a_goal_renumbers_the_ones_after_it(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(goals=("a", "b", "c")), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    dialog.goals.rows[0].remove_btn.click()
    assert [row.label.text() for row in dialog.goals.rows] == ["Goal 1", "Goal 2"]
    assert dialog.profile().goals == ("b", "c")


def test_a_blank_goal_is_left_out(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    dialog.goals.add_row()
    assert dialog.profile().goals == ()


def test_a_new_profile_is_an_iep(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    assert not dialog.profile().plan_504


def test_ticking_504_makes_the_plan_a_504(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    dialog.plan_504.setChecked(True)
    dialog.plan_date.setText("03/02/2026")
    assert (dialog.profile().plan_504, dialog.profile().plan_date) == (True, "03/02/2026")


def test_summary_numbers_the_goals(qtbot):
    summary = ProfileSummary()
    qtbot.addWidget(summary)
    summary.show_profile("王小明", StudentProfile(goals=("剪直線", "扣釦子")))
    assert summary.values["goals"].text() == "1. 剪直線\n2. 扣釦子"


def test_summary_shows_which_plan_the_date_is_of(qtbot):
    summary = ProfileSummary()
    qtbot.addWidget(summary)
    summary.show_profile("王小明", StudentProfile(plan_504=True, plan_date="03/02/2026"))
    assert summary.values["plan"].text() == "504 03/02/2026"


OLD_PLAN = Plan(False, "10/29/2025", ("剪直線",))
NEW_PLAN = Plan(True, "10/29/2026", ("扣釦子", "寫名字"))


def plans_dialog(qtbot, *plans):
    dialog = StudentProfileDialog("王小明", StudentProfile().with_plans(plans), today=date(2026, 10, 1))
    qtbot.addWidget(dialog)
    return dialog


def test_dialog_shows_the_latest_plan(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN, NEW_PLAN)
    assert (dialog.plan_date.text(), dialog.goals.goals()) == ("10/29/2026", ("扣釦子", "寫名字"))


def test_an_old_plan_can_be_shown_again(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN, NEW_PLAN)
    dialog.plans.show_plan(1)
    assert (dialog.plan_date.text(), dialog.plan_504.isChecked(), dialog.goals.goals()) == (
        "10/29/2025", False, ("剪直線",))


def test_a_new_plan_starts_blank_and_keeps_the_old_one(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN)
    dialog.plans.add_plan()
    dialog.plan_date.setText("10/29/2026")
    dialog.goals.add_row("扣釦子")
    assert dialog.profile().plans == (OLD_PLAN, Plan(False, "10/29/2026", ("扣釦子",)))


def test_picker_shows_only_with_several_plans(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN)
    dialog.show()
    assert not dialog.plans.picker.isVisible()
    dialog.plans.add_plan()
    assert dialog.plans.picker.isVisible()


def test_picker_names_each_plan_newest_first(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN, NEW_PLAN)
    picker = dialog.plans.picker
    assert [picker.itemText(i) for i in range(picker.count())] == ["504 10/29/2026", "IEP 10/29/2025"]


def test_edits_of_an_old_plan_are_kept_after_switching(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN, NEW_PLAN)
    dialog.plans.show_plan(1)
    dialog.goals.add_row("寫名字")
    dialog.plans.show_plan(0)
    assert dialog.profile().past_plans == (Plan(False, "10/29/2025", ("剪直線", "寫名字")),)


def test_a_plan_can_be_deleted(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN, NEW_PLAN)
    dialog.plans.remove_plan(confirm=False)
    assert dialog.profile().plans == (OLD_PLAN,)


def test_an_unreadable_plan_date_keeps_the_dialog_open(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN)
    dialog.plan_date.setText("Oct 29")
    dialog.accept()
    assert dialog.problem.text() == "IEP/504 日期請填成 10/29/2026 這樣的格式"


def test_a_second_plan_needs_a_date(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN)
    dialog.plans.add_plan()
    dialog.accept()
    assert dialog.problem.text() == "有多份 IEP/504 計畫時，每份都要填日期"


def test_two_plans_cannot_share_a_date(qtbot):
    dialog = plans_dialog(qtbot, OLD_PLAN)
    dialog.plans.add_plan()
    dialog.plan_date.setText("10/29/25")
    dialog.accept()
    assert dialog.problem.text() == "兩份 IEP/504 計畫的日期不能相同"


def test_summary_shows_the_plan_in_effect_on_the_charts_day(qtbot):
    summary = ProfileSummary()
    qtbot.addWidget(summary)
    summary.show_profile("王小明", StudentProfile().with_plans([OLD_PLAN, NEW_PLAN]), date(2026, 3, 1))
    assert (summary.values["plan"].text(), summary.values["goals"].text()) == ("IEP 10/29/2025", "1. 剪直線")

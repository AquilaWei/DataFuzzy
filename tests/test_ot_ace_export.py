import json
from datetime import date
from pathlib import Path

import pytest

from datafuzzy.ot.ace_export import (
    KC_NO_START,
    MANUAL_TYPE,
    NO_ENGLISH,
    NO_GROUP,
    NO_TIMES,
    ace_cells,
    fill_issues,
    kc_visits,
    to_json,
)
from datafuzzy.ot.ace_mapping import AceRow
from datafuzzy.ot.db import Plan, RecordStore, StudentProfile

KEY = bytes(range(32))
NOV_9, NOV_10, NOV_15 = date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 15)
DOCUMENTATION = AceRow("indirect", "Documentation", 5)


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


def therapy(store, student_id, day=NOV_10, **fields):
    values = {"en_text": "Worked on grasp.", "en_followup": "Zippers.", "start_time": "13:30",
              "end_time": "14:00"} | fields
    return store.add_record(student_id, day, **values)


def week(store):
    return ace_cells(store, NOV_9, NOV_15)


def test_a_cell_is_found_by_first_and_last_name(store):
    therapy(store, store.add_student("Todd", "Lane").id)
    [cell] = week(store)
    assert (cell.first, cell.last, cell.date) == ("Todd", "Lane", "2026-11-10")


def test_two_charts_of_one_student_on_one_day_share_a_cell(store):
    todd = store.add_student("Todd", "Lane").id
    therapy(store, todd)
    therapy(store, todd, session_type="Scheduling", start_time="15:00", end_time="15:10")
    [cell] = week(store)
    assert [row.type for row in cell.rows] == ["Direct Therapy Time", "Documentation", "Scheduling"]


def test_two_therapy_charts_on_one_day_log_documentation_twice(store):
    todd = store.add_student("Todd", "Lane").id
    therapy(store, todd)
    therapy(store, todd, start_time="15:00", end_time="15:30")
    [cell] = week(store)
    assert [row.type for row in cell.rows].count("Documentation") == 2


def test_one_student_on_two_days_has_two_cells(store):
    todd = store.add_student("Todd", "Lane").id
    therapy(store, todd, day=NOV_9)
    therapy(store, todd, day=NOV_10)
    assert [cell.date for cell in week(store)] == ["2026-11-09", "2026-11-10"]


def test_charts_outside_the_range_are_left_out(store):
    therapy(store, store.add_student("Todd", "Lane").id, day=date(2026, 11, 16))
    assert week(store) == []


def test_group_charts_of_two_students_at_one_time_are_one_group(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_mode="group")
    therapy(store, store.add_student("Amy", "Chen").id, session_mode="group")
    assert [(c.rows[0].group, c.rows[0].group_size) for c in week(store)] == [("Group A", 2), ("Group A", 2)]


def test_a_student_billed_to_ma_gets_ma_access_billing(store):
    todd = store.add_student("Todd", "Lane").id
    store.set_profile(todd, StudentProfile(ma_billing=True))
    therapy(store, todd)
    [cell] = week(store)
    assert cell.rows[1:] == [DOCUMENTATION, AceRow("indirect", "MA ACCESS Billing", 5)]


def test_a_complete_therapy_chart_has_no_problems(store):
    therapy(store, store.add_student("Todd", "Lane").id)
    assert week(store)[0].problems == []


def test_a_consult_is_left_to_enter_by_hand(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_type="Consult")
    [cell] = week(store)
    assert (cell.rows, cell.problems) == ([], [MANUAL_TYPE])


def test_a_therapy_chart_without_its_english_follow_up_is_a_problem(store):
    therapy(store, store.add_student("Todd", "Lane").id, en_followup="")
    assert week(store)[0].problems == [NO_ENGLISH]


def test_an_evaluation_without_english_comments_is_a_problem(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_type="Evaluation", en_text="")
    assert week(store)[0].problems == [NO_ENGLISH]


def test_a_therapy_chart_without_times_is_a_problem(store):
    therapy(store, store.add_student("Todd", "Lane").id, start_time="", end_time="")
    assert week(store)[0].problems == [NO_TIMES]


def test_an_absence_needs_no_times(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_type="Absent Student", start_time="", end_time="")
    assert week(store)[0].problems == []


def test_a_no_show_without_times_is_a_problem(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_type="No-Show", start_time="", end_time="")
    assert week(store)[0].problems == [NO_TIMES]


def test_a_group_absence_without_a_start_time_has_no_group(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_type="Absent Student", session_mode="group",
            start_time="", end_time="")
    assert week(store)[0].problems == [NO_GROUP]


def test_the_file_names_its_format_and_week(store):
    data = json.loads(to_json([], NOV_9, NOV_15))
    assert (data["format"], data["week"]) == ("theranote-ace/2", ["2026-11-09", "2026-11-15"])


def test_the_file_holds_each_row_s_fields(store):
    therapy(store, store.add_student("Todd", "Lane").id)
    row = json.loads(to_json(week(store), NOV_9, NOV_15))["cells"][0]["rows"][0]
    assert row == {"section": "direct", "type": "Direct Therapy Time", "minutes": 30, "start": "1:30 PM",
                   "end": "2:00 PM", "comments_on_log": "Zippers.", "data_towards_goals": "Worked on grasp.",
                   "deficit": "Visual Motor Coordination", "group": "", "group_size": 0}


TUESDAY = date(2026, 11, 10)


def ace_dialog(qtbot, store, choose=lambda start: "", confirm=lambda path: True, said=None, start=None):
    from datafuzzy.ot.ui.exchange_dialogs import AceExportDialog

    said = [] if said is None else said
    dialog = AceExportDialog(store, today=TUESDAY, choose=choose, confirm=confirm, start=start,
                             notify=lambda saved, message: said.append((saved, message)))
    qtbot.addWidget(dialog)
    return dialog


def test_the_dialog_starts_at_this_week_monday_to_sunday(qtbot, store):
    dialog = ace_dialog(qtbot, store)
    assert (dialog.from_edit.date().toString("yyyy-MM-dd"), dialog.to_edit.date().toString("yyyy-MM-dd")) == (
        "2026-11-09", "2026-11-15")


def test_files_go_to_downloads_until_a_folder_is_picked(qtbot, store):
    assert ace_dialog(qtbot, store).folder() == Path.home() / "Downloads"


def test_a_picked_folder_is_remembered(qtbot, store, tmp_path):
    ace_dialog(qtbot, store, choose=lambda start: str(tmp_path)).choose_folder()
    assert ace_dialog(qtbot, store).folder() == tmp_path


def test_saving_writes_the_week_s_file_into_the_folder(qtbot, store, tmp_path):
    therapy(store, store.add_student("Todd", "Lane").id)
    store.set_ace_folder(str(tmp_path))
    ace_dialog(qtbot, store).save()
    assert json.loads((tmp_path / "TheraNote-ACE-2026-11-09.json").read_text())["cells"][0]["first"] == "Todd"


def test_a_file_already_there_is_kept_unless_replacing_is_confirmed(qtbot, store, tmp_path):
    therapy(store, store.add_student("Todd", "Lane").id)
    store.set_ace_folder(str(tmp_path))
    (tmp_path / "TheraNote-ACE-2026-11-09.json").write_text("old")
    ace_dialog(qtbot, store, confirm=lambda path: False).save()
    assert (tmp_path / "TheraNote-ACE-2026-11-09.json").read_text() == "old"


def test_a_group_plan_student_s_one_to_one_session_is_entered_as_a_group_of_one(store):
    todd = store.add_student("Todd", "Lane").id
    store.set_profile(todd, StudentProfile(group=True))
    therapy(store, todd)
    [cell] = week(store)
    assert (cell.rows[0].section, cell.rows[0].group, cell.rows[0].group_size) == ("group", "Group A", 1)


def test_the_group_plan_in_effect_on_the_chart_s_day_decides(store):
    todd = store.add_student("Todd", "Lane").id
    store.set_profile(todd, StudentProfile().with_plans([Plan(False, "01/01/2026", group=True),
                                                         Plan(False, "11/12/2026")]))
    therapy(store, todd, day=NOV_10)
    [cell] = week(store)
    assert cell.rows[0].section == "group"


def test_a_group_student_who_came_alone_is_noted_and_the_absent_one_joins_the_group(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_mode="group")
    amy = store.add_student("Amy", "Chen").id
    store.set_profile(amy, StudentProfile(group=True))
    therapy(store, amy, session_type="Unavailable Student", en_followup="")
    amy_cell, todd_cell = week(store)
    assert (todd_cell.rows[0].group, todd_cell.rows[0].group_size) == ("Group A", 1)
    assert todd_cell.rows[0].comments_on_log.startswith("No appropriate student to group with.\n")
    assert (amy_cell.rows[0].section, amy_cell.rows[0].type, amy_cell.rows[0].group) == (
        "group", "Unavailable Student", "Group A")


def test_saving_says_so(qtbot, store, tmp_path):
    therapy(store, store.add_student("Todd", "Lane").id)
    store.set_ace_folder(str(tmp_path))
    said = []
    dialog = ace_dialog(qtbot, store, said=said)
    dialog.save()
    assert [saved for saved, _ in said] == [True]
    assert dialog.result() == dialog.DialogCode.Accepted


def test_a_failed_write_leaves_the_dialog_open(qtbot, store, tmp_path):
    therapy(store, store.add_student("Todd", "Lane").id)
    (tmp_path / "file").write_text("")
    store.set_ace_folder(str(tmp_path / "file" / "below"))
    dialog = ace_dialog(qtbot, store)
    dialog.save()
    assert dialog.result() != dialog.DialogCode.Accepted


def test_a_failed_write_says_so(qtbot, store, tmp_path):
    therapy(store, store.add_student("Todd", "Lane").id)
    (tmp_path / "file").write_text("")
    store.set_ace_folder(str(tmp_path / "file" / "below"))
    said = []
    ace_dialog(qtbot, store, said=said).save()
    assert [saved for saved, _ in said] == [False]


def test_nothing_is_saved_while_a_chart_is_incomplete(qtbot, store, tmp_path):
    therapy(store, store.add_student("Todd", "Lane").id, en_followup="")
    therapy(store, store.add_student("Amy", "Chen").id)
    store.set_ace_folder(str(tmp_path))
    dialog = ace_dialog(qtbot, store)
    dialog.save()
    assert dialog.incomplete == (NOV_9, NOV_15)
    assert not (tmp_path / "TheraNote-ACE-2026-11-09.json").exists()


def test_the_dialog_can_come_back_to_the_same_range(qtbot, store):
    dialog = ace_dialog(qtbot, store, start=(NOV_10, NOV_15))
    assert (dialog.from_edit.date().toString("yyyy-MM-dd"), dialog.to_edit.date().toString("yyyy-MM-dd")) == (
        "2026-11-10", "2026-11-15")


def test_fill_issues_lists_each_incomplete_chart_and_what_to_fix(store):
    todd = therapy(store, store.add_student("Todd", "Lane").id, en_followup="")
    therapy(store, store.add_student("Amy", "Chen").id)
    assert [(i.record.id, i.student_name, i.problems) for i in fill_issues(store, NOV_9, NOV_15)] == [
        (todd.id, "Todd Lane", [NO_ENGLISH])]


def test_a_consult_does_not_keep_the_file_from_being_saved(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_type="Consult")
    assert fill_issues(store, NOV_9, NOV_15) == []


def test_a_pre_school_absence_without_a_start_time_must_be_fixed_for_keepcurrent(store):
    therapy(store, preschooler(store), session_type="Absent Student", start_time="", end_time="")
    [issue] = fill_issues(store, NOV_9, NOV_15)
    assert issue.problems == [KC_NO_START]


def test_the_incomplete_list_marks_charts_fixed_and_then_offers_to_export(qtbot, store):
    from datafuzzy.ot.ui.exchange_dialogs import IncompleteChartsDialog

    todd = therapy(store, store.add_student("Todd", "Lane").id, en_followup="")
    dialog = IncompleteChartsDialog(lambda: fill_issues(store, NOV_9, NOV_15), "ACE 填寫檔", "回到 ACE 填寫檔")
    qtbot.addWidget(dialog)
    assert dialog.list.item(0).text() == "2026-11-10  週二  1:30 PM  Todd Lane — 還沒有英文記錄或追蹤"
    assert not dialog.retry_btn.isEnabled()
    opened = []
    dialog.open_record.connect(opened.append)
    dialog.open_btn.click()
    assert opened == [todd.id]
    store.update_record(todd.id, en_followup="Zippers.")
    dialog.refresh()
    assert dialog.list.item(0).text().startswith("✓ 已補齊")
    assert dialog.retry_btn.isEnabled()
    retried = []
    dialog.retry.connect(lambda: retried.append(True))
    dialog.retry_btn.click()
    assert retried == [True]


# --- KeepCurrent (pre-school students) ------------------------------------------------------

def preschooler(store, given="Dree", family="Todd", goals=("Join group tasks", "Follow directions", "Ball skills")):
    sid = store.add_student(given, family).id
    store.set_profile(sid, StudentProfile(grade="Pre-School", goals=goals))
    return sid


def visits(store):
    return kc_visits(store, NOV_9, NOV_15)


def test_only_pre_school_students_charts_go_to_keepcurrent(store):
    therapy(store, preschooler(store))
    older = store.add_student("Amy", "Lin").id
    store.set_profile(older, StudentProfile(grade="K"))
    therapy(store, older)
    therapy(store, store.add_student("Bo", "Wu").id)  # no grade
    assert [(v.first, v.last) for v in visits(store)] == [("Dree", "Todd")]


def test_a_therapy_session_is_direct_with_its_minutes_comment_and_mode(store):
    therapy(store, preschooler(store), session_mode="group")
    [visit] = visits(store)
    assert (visit.date, visit.start, visit.minutes, visit.mode) == ("2026-11-10", "13:30", 30, "Group")
    assert (visit.application_type, visit.direct, visit.comment) == ("D - Direct", True, "Worked on grasp.")
    assert visit.problems == []


@pytest.mark.parametrize(("kind", "application_type", "direct"), [
    ("Direct Therapy Time", "D - Direct", True),
    ("Make-Up", "DM - Direct Session", True),
    ("Absent Student", "SA - Student Absent", False),
    ("No-Show", "SA - Student Absent", False),
    ("Therapist Absent", "PA - Provider Absent", False),
    ("School Not in Session", "School Closed", False),
    ("Unavailable Student", "SNA - Student Not Available", False),
])
def test_each_type_has_its_application_type(store, kind, application_type, direct):
    therapy(store, preschooler(store), session_type=kind)
    [visit] = visits(store)
    assert (visit.application_type, visit.direct) == (application_type, direct)


def test_a_session_called_off_takes_no_minutes_comment_or_goals(store):
    therapy(store, preschooler(store), session_type="Therapist Absent", goal_scores=("met",))
    [visit] = visits(store)
    assert (visit.minutes, visit.comment, visit.goals, visit.problems) == (0, "", [], [])


@pytest.mark.parametrize("kind", ["Collaboration", "Scheduling", "Consult", "Evaluation", "IEP Meeting/Meeting"])
def test_types_keepcurrent_does_not_take_are_left_out(store, kind):
    therapy(store, preschooler(store), session_type=kind)
    assert visits(store) == []


def test_only_goals_scored_met_or_not_met_are_ticked(store):
    therapy(store, preschooler(store), goal_scores=("met", "not addressed", "Not Met"))
    [visit] = visits(store)
    assert visit.goals == ["Join group tasks", "Ball skills"]


def test_the_goals_are_those_of_the_plan_on_the_chart_s_day(store):
    sid = store.add_student("Dree", "Todd").id
    store.set_profile(sid, StudentProfile(grade="Pre-School").with_plans([
        Plan(False, "01/01/2026", goals=("Old goal",)), Plan(False, "11/12/2026", goals=("New goal",))]))
    therapy(store, sid, goal_scores=("met",))
    therapy(store, sid, day=NOV_15, goal_scores=("met",))
    assert [v.goals for v in visits(store)] == [["Old goal"], ["New goal"]]


def test_a_direct_session_without_english_or_times_is_a_problem(store):
    therapy(store, preschooler(store), en_text="", end_time="")
    [visit] = visits(store)
    assert visit.problems == [NO_ENGLISH, NO_TIMES]


def test_visits_are_by_day_then_start_time(store):
    dree = preschooler(store)
    therapy(store, dree, start_time="10:00", end_time="10:30")
    therapy(store, dree, day=NOV_9, start_time="11:00", end_time="11:30")
    therapy(store, dree, start_time="08:30", end_time="09:00")
    assert [(v.date, v.start) for v in visits(store)] == [
        ("2026-11-09", "11:00"), ("2026-11-10", "08:30"), ("2026-11-10", "10:00")]


def test_the_file_has_the_visits_beside_the_cells(store):
    therapy(store, preschooler(store))
    data = json.loads(to_json(week(store), NOV_9, NOV_15, visits(store)))
    assert data["format"] == "theranote-ace/2"
    assert len(data["cells"]) == 1
    assert data["visits"][0]["application_type"] == "D - Direct"


def test_saving_also_writes_the_pre_school_charts_for_keepcurrent(qtbot, store, tmp_path):
    therapy(store, preschooler(store))
    store.set_ace_folder(str(tmp_path))
    said = []
    ace_dialog(qtbot, store, said=said).save()
    data = json.loads((tmp_path / "TheraNote-ACE-2026-11-09.json").read_text())
    assert [v["first"] for v in data["visits"]] == ["Dree"]
    assert "KeepCurrent" in said[0][1]

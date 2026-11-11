import json
from datetime import date
from pathlib import Path

import pytest

from datafuzzy.ot.ace_export import (
    MANUAL_TYPE,
    NO_ENGLISH,
    NO_GROUP,
    NO_TIMES,
    ace_cells,
    to_json,
)
from datafuzzy.ot.ace_mapping import AceRow
from datafuzzy.ot.db import RecordStore, StudentProfile

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
    assert [row.type for row in cell.rows] == ["Direct Therapy Time", "Documentation", "Scheduling", "Documentation"]


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


def test_a_group_absence_without_a_start_time_has_no_group(store):
    therapy(store, store.add_student("Todd", "Lane").id, session_type="Absent Student", session_mode="group",
            start_time="", end_time="")
    assert week(store)[0].problems == [NO_GROUP]


def test_the_file_names_its_format_and_week(store):
    data = json.loads(to_json([], NOV_9, NOV_15))
    assert (data["format"], data["week"]) == ("theranote-ace/1", ["2026-11-09", "2026-11-15"])


def test_the_file_holds_each_row_s_fields(store):
    therapy(store, store.add_student("Todd", "Lane").id)
    row = json.loads(to_json(week(store), NOV_9, NOV_15))["cells"][0]["rows"][0]
    assert row == {"section": "direct", "type": "Direct Therapy Time", "minutes": 30, "start": "1:30 PM",
                   "end": "2:00 PM", "comments_on_log": "Zippers.", "data_towards_goals": "Worked on grasp.",
                   "deficit": "Visual Motor Coordination", "group": "", "group_size": 0}


TUESDAY = date(2026, 11, 10)


def ace_dialog(qtbot, store, choose=lambda start: "", confirm=lambda path: True):
    from datafuzzy.ot.ui.exchange_dialogs import AceExportDialog

    dialog = AceExportDialog(store, today=TUESDAY, choose=choose, confirm=confirm)
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

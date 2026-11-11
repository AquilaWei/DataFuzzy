from datetime import date, datetime

from datafuzzy.ot.ace_mapping import AceRow, ace_rows, ace_time, group_names
from datafuzzy.ot.db import Record

OCT_1 = date(2026, 10, 1)
DOCUMENTATION = AceRow("indirect", "Documentation", 5)


def chart(record_id=1, session_type="Direct Therapy Time", mode="individual", start="13:30", end="14:00",
          day=OCT_1, **fields) -> Record:
    return Record(record_id, 1, day, "", "", fields.pop("en_text", "Comments."), datetime(2026, 10, 1),
                  start_time=start, end_time=end, session_type=session_type, session_mode=mode, **fields)


def test_ace_time_is_twelve_hour():
    assert [ace_time("13:30"), ace_time("09:05"), ace_time("12:00"), ace_time("00:15")] == [
        "1:30 PM", "9:05 AM", "12:00 PM", "12:15 AM"]


def test_direct_therapy_fills_direct_time_and_documentation():
    rows = ace_rows(chart(en_followup="Zippers."), ma_billing=False)
    assert rows == [AceRow("direct", "Direct Therapy Time", 30, "1:30 PM", "2:00 PM", comments_on_log="Zippers.",
                           data_towards_goals="Comments.", deficit="Visual Motor Coordination"), DOCUMENTATION]


def test_a_student_billed_to_ma_also_gets_ma_access_billing():
    rows = ace_rows(chart(), ma_billing=True)
    assert rows[1:] == [DOCUMENTATION, AceRow("indirect", "MA ACCESS Billing", 5)]


def test_a_group_make_up_fills_group_time_with_its_group():
    [main, _] = ace_rows(chart(session_type="Make-Up", mode="group"), ma_billing=False, group=("Group B", 3))
    assert (main.section, main.type, main.group, main.group_size) == ("group", "Make-Up", "Group B", 3)


def test_an_evaluation_logs_its_comments_and_minutes():
    rows = ace_rows(chart(session_type="Evaluation"), ma_billing=True)
    assert rows == [AceRow("direct", "Evaluation", 30, comments_on_log="Comments."), DOCUMENTATION]


def test_an_absence_takes_no_time():
    rows = ace_rows(chart(session_type="Absent Student"), ma_billing=False)
    assert rows == [AceRow("direct", "Absent Student"), DOCUMENTATION]


def test_an_annual_iep_report_takes_its_minutes():
    [main, _] = ace_rows(chart(session_type="Annual IEP Report"), ma_billing=False)
    assert (main.minutes, main.start) == (30, "")


def test_a_group_absence_goes_under_group_time():
    [main, _] = ace_rows(chart(session_type="Therapist Absent", mode="group"), ma_billing=False, group=("Group A", 2))
    assert (main.section, main.group) == ("group", "Group A")


def test_collaboration_is_indirect_with_its_comments():
    rows = ace_rows(chart(session_type="Collaboration", mode="group"), ma_billing=False)
    assert rows == [AceRow("indirect", "Collaboration", 30, comments_on_log="Comments.")]


def test_scheduling_is_indirect_without_comments():
    rows = ace_rows(chart(session_type="Scheduling", start="10:00", end="10:15"), ma_billing=False)
    assert rows == [AceRow("indirect", "Scheduling", 15)]


def test_home_program_takes_no_documentation():
    assert ace_rows(chart(session_type="Home Program"), ma_billing=True) == [AceRow("indirect", "Home Program", 30)]


def test_an_iep_meeting_takes_no_documentation():
    rows = ace_rows(chart(session_type="IEP Meeting/Meeting"), ma_billing=False)
    assert rows == [AceRow("indirect", "IEP Meeting/Meeting", 30)]


def test_a_progress_report_takes_no_documentation():
    rows = ace_rows(chart(session_type="Progress Report"), ma_billing=False)
    assert rows == [AceRow("indirect", "Progress Report", 30)]


def test_a_no_show_takes_its_minutes_and_documentation():
    rows = ace_rows(chart(session_type="No-Show"), ma_billing=True)
    assert rows == [AceRow("direct", "No Show", 30), DOCUMENTATION]  # as ACE spells it


def test_consult_is_left_to_be_entered_by_hand():
    assert ace_rows(chart(session_type="Consult"), ma_billing=False) is None


def test_missing_times_give_no_minutes():
    [main, _] = ace_rows(chart(session_type="Evaluation", end=""), ma_billing=False)
    assert main.minutes is None


def test_group_charts_starting_together_are_one_group():
    names = group_names([chart(1, mode="group"), chart(2, mode="group"), chart(3, mode="group", start="09:00")])
    assert names == {3: ("Group A", 1), 1: ("Group B", 2), 2: ("Group B", 2)}


def test_each_day_names_its_groups_from_a():
    names = group_names([chart(1, mode="group"), chart(2, mode="group", day=date(2026, 10, 2))])
    assert names == {1: ("Group A", 1), 2: ("Group A", 1)}


def test_individual_charts_form_no_group():
    assert group_names([chart(1), chart(2, mode="group", start="")]) == {}

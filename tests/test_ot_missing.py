from datetime import date, datetime

import pytest

from datafuzzy.ot.db import Plan, Record, RecordStore, StudentProfile
from datafuzzy.ot.ui.cards import RecordCard
from datafuzzy.ot.ui.date_view import MISSING_ROLE, DayRecordsView
from datafuzzy.ot.ui.editor import RecordEditor
from datafuzzy.ot.ui.session_fields import missing_parts, missing_text

KEY = bytes(range(32))
DAY = date(2026, 10, 1)
GOALS = ("Zip a coat", "Cut a circle")


def chart(session_type="Direct Therapy Time", **fields) -> Record:
    values = {"start_time": "13:30", "end_time": "14:00", "activity": "Scissors", "zh_text": "剪紙",
              "zh_followup": "拉鍊", "goal_scores": ("met", "not met")} | fields
    return Record(1, 1, DAY, "", values.pop("zh_text"), values.pop("en_text", ""), datetime(2026, 10, 1),
                  session_type=session_type, **values)


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


def test_a_filled_in_therapy_chart_misses_nothing():
    assert missing_parts(chart(), GOALS, today=DAY) == []


def test_an_empty_therapy_chart_misses_every_part():
    empty = chart(start_time="", end_time="", activity="", zh_text="", zh_followup="", goal_scores=())
    assert missing_parts(empty, GOALS, today=DAY) == ["times", "scores", "activity", "comments", "followup"]


def test_a_goal_left_unscored_is_missing():
    assert missing_parts(chart(goal_scores=("met", "")), GOALS, today=DAY) == ["scores"]


def test_english_alone_fills_the_comments_and_follow_up():
    filled = chart(zh_text="", zh_followup="", en_text="Cutting.", en_followup="Zippers.")
    assert missing_parts(filled, GOALS, today=DAY) == []


def test_a_booked_session_not_held_yet_misses_nothing():
    assert missing_parts(chart(start_time="", zh_text=""), GOALS, today=date(2026, 9, 30)) == []


def test_an_absence_needs_nothing():
    assert missing_parts(chart("Absent Student", start_time="", end_time="", zh_text="", zh_followup="",
                               activity="", goal_scores=()), GOALS, today=DAY) == []


def test_an_evaluation_needs_its_times_and_comments_only():
    assert missing_parts(chart("Evaluation", start_time="", zh_text="", zh_followup="", activity="",
                               goal_scores=()), GOALS, today=DAY) == ["times", "comments"]


def test_the_missing_parts_are_named():
    assert missing_text(["times", "followup"]) == "缺：時間、追蹤"
    assert missing_text([]) == ""


def empty_chart(store):
    student = store.add_student("王小明").id
    store.set_profile(student, StudentProfile().with_plans([Plan(False, "01/01/2026", goals=GOALS)]))
    return store.add_record(student, DAY, start_time="13:30", end_time="14:00")


def test_a_chart_opened_again_says_in_red_what_it_misses(qtbot, store):
    editor = RecordEditor(store, empty_chart(store).id)
    qtbot.addWidget(editor)
    assert editor.missing_label.text() == "這份病歷還缺：目標表現、活動、記錄、追蹤"
    assert "color" in editor.activity_label.styleSheet()


def test_a_fresh_chart_says_nothing_yet(qtbot, store):
    editor = RecordEditor(store, empty_chart(store).id, fresh=True)
    qtbot.addWidget(editor)
    assert editor.missing_label.isHidden()
    assert editor.activity_label.styleSheet() == ""


def test_a_warning_goes_once_its_part_is_filled_in(qtbot, store):
    editor = RecordEditor(store, empty_chart(store).id)
    qtbot.addWidget(editor)
    editor.activity_edit.setPlainText("Scissors")
    assert editor.missing_label.text() == "這份病歷還缺：目標表現、記錄、追蹤"
    assert editor.activity_label.styleSheet() == ""


def test_a_card_of_a_chart_missing_parts_says_which(qtbot, store):
    record = empty_chart(store)
    card = RecordCard(record, 0, goals=GOALS)
    qtbot.addWidget(card)
    assert (card.missing, card.missing_label.isHidden()) == ("缺：目標表現、活動、記錄、追蹤", False)


def test_the_day_list_marks_a_chart_missing_parts(qtbot, store):
    empty_chart(store)
    view = DayRecordsView(store)
    qtbot.addWidget(view)
    view.show_day(DAY)
    assert view.list.item(0).data(MISSING_ROLE) == "缺：目標表現、活動、記錄、追蹤"

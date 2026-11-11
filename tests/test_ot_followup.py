from datetime import date

import pytest

from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.followup import (
    excel_comment,
    followup_splits,
    join_chart,
    split_chart,
    split_followup,
)
from datafuzzy.ot.ui.followup_dialog import FollowupReviewDialog, offer_followup_review

KEY = bytes(range(32))
OCT_1 = date(2026, 10, 1)


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


def test_a_bold_bulleted_follow_up_label_splits_and_goes():
    assert split_followup("Did well.\n* **Follow-up:** Zippers next time.") == ("Did well.", "Zippers next time.")


def test_a_label_with_its_colon_outside_the_bold_splits():
    assert split_followup("Did well.\n**Follow up**: Zippers.") == ("Did well.", "Zippers.")


def test_f_u_splits():
    assert split_followup("Did well.\n- F/U: Zippers.") == ("Did well.", "Zippers.")


def test_fu_with_a_colon_splits():
    assert split_followup("Did well.\nFU: Zippers.") == ("Did well.", "Zippers.")


def test_the_chinese_label_splits():
    assert split_followup("表現很好。\n追蹤：練拉鍊") == ("表現很好。", "練拉鍊")


def test_plan_with_a_colon_splits():
    assert split_followup("Did well.\n**Plan:** Zippers.") == ("Did well.", "Zippers.")


def test_next_session_without_a_colon_stays_in_the_follow_up():
    assert split_followup("Did well.\nNext session we try zippers.") == ("Did well.", "Next session we try zippers.")


def test_xiaci_stays_in_the_follow_up():
    assert split_followup("表現很好。\n下次練拉鍊") == ("表現很好。", "下次練拉鍊")


def test_follow_up_in_the_middle_of_a_line_does_not_split():
    assert split_followup("We will follow up later.") is None


def test_plan_without_a_colon_does_not_split():
    assert split_followup("Did well.\nPlanning was hard.") is None


def test_a_label_with_nothing_after_it_does_not_split():
    assert split_followup("Did well.\n* **Follow-up:**") is None


def test_the_follow_up_can_run_over_several_lines():
    assert split_followup("Did well.\nFollow-up:\nZippers.\nButtons.") == ("Did well.", "Zippers.\nButtons.")


def test_join_puts_the_marker_between_comments_and_follow_up():
    assert join_chart("Notes", "Next") == "Notes\n--- FOLLOW-UP ---\nNext"


def test_join_keeps_the_marker_without_a_follow_up():
    assert join_chart("Notes", "") == "Notes\n--- FOLLOW-UP ---"


def test_split_chart_finds_a_marker_without_hyphen():
    assert split_chart("Notes\n--- FOLLOWUP ---\nNext") == ("Notes", "Next")


def test_split_chart_without_a_marker_is_none():
    assert split_chart("Notes only") is None


def test_the_excel_comment_restores_the_older_follow_up_label():
    original = "Did well.\n\n* **Follow-up:** Zippers next time."
    assert excel_comment(*split_followup(original)) == original


def test_charts_with_a_follow_up_already_are_not_offered(store):
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, en_text="Did well.\nFollow-up: Zippers.", en_followup="Buttons")
    assert followup_splits(store.records_between(OCT_1, OCT_1)) == []


def test_a_language_without_a_follow_up_keeps_its_comments(store):
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, zh_text="表現很好。", en_text="Did well.\nFollow-up: Zippers.")
    [split] = followup_splits(store.records_between(OCT_1, OCT_1))
    assert split.texts() == {"zh_text": "表現很好。", "zh_followup": "", "en_text": "Did well.",
                             "en_followup": "Zippers."}


def test_applying_the_review_moves_only_the_ticked_charts(qtbot, store):
    student = store.add_student("王小明")
    first = store.add_record(student.id, OCT_1, en_text="A\nFollow-up: one")
    second = store.add_record(student.id, OCT_1, en_text="B\nFollow-up: two")
    dialog = FollowupReviewDialog(store, followup_splits(store.records_between(OCT_1, OCT_1)))
    qtbot.addWidget(dialog)
    dialog.items.item(1).setCheckState(dialog.items.item(1).checkState().Unchecked)
    dialog.apply()
    assert (store.get_record(first.id).en_followup, store.get_record(second.id).en_text) == ("one", "B\nFollow-up: two")


def test_closing_the_review_marks_it_done(qtbot, store):
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, en_text="A\nFollow-up: one")
    dialog = FollowupReviewDialog(store, followup_splits(store.records_between(OCT_1, OCT_1)))
    qtbot.addWidget(dialog)
    dialog.reject()
    assert store.followups_reviewed()


def test_with_nothing_to_split_the_review_is_marked_done_without_asking(store):
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, en_text="Did well.")
    assert (offer_followup_review(store), store.followups_reviewed()) == (False, True)

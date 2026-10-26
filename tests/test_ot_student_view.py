from datetime import date

import pytest
from PySide6.QtCore import Qt

from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.ui.cards import date_label, preview_text
from datafuzzy.ot.ui.student_view import StudentRecordsView

KEY = bytes(range(32))


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


@pytest.fixture
def student(store):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 5), "新竹國小", "第二次\n練習剪紙")
    store.add_record(student.id, date(2026, 10, 1), "台北診所", "第一次")
    store.add_record(student.id, date(2026, 10, 9), "新竹國小", "第三次")
    return student


@pytest.fixture
def view(qtbot, store, student):
    view = StudentRecordsView(store)
    qtbot.addWidget(view)
    view.resize(600, 700)
    view.show_student(student.id)
    return view


def card_dates(view):
    return [card.date_label.text()[:10] for card in view.stack.cards]


def test_view_shows_one_card_per_record_newest_first(view):
    assert card_dates(view) == ["2026-10-09", "2026-10-05", "2026-10-01"]


def test_switching_sort_shows_oldest_first(view):
    view.sort.button(1).click()
    assert card_dates(view) == ["2026-10-01", "2026-10-05", "2026-10-09"]


def test_switching_sort_back_shows_newest_first(view):
    view.sort.button(1).click()
    view.sort.button(0).click()
    assert card_dates(view) == ["2026-10-09", "2026-10-05", "2026-10-01"]


def test_header_names_the_student_and_counts_records(view):
    assert (view.title.text(), view.count.text()) == ("王小明", "3 份病歷")


def test_card_shows_date_location_and_first_lines(view):
    card = view.stack.cards[1]
    assert (card.date_label.text(), card.location_label.text(), card.preview_label.text()) == (
        "2026-10-05  週一", "新竹國小", "第二次\n練習剪紙")


def test_clicking_a_card_opens_that_record(qtbot, view):
    with qtbot.waitSignal(view.open_record, timeout=1000) as opened:
        qtbot.mouseClick(view.stack.cards[2], Qt.MouseButton.LeftButton)
    assert opened.args == [2]  # the Oct 1 record was the second one created


def test_student_without_records_shows_hint_and_no_cards(qtbot, store):
    other = store.add_student("陳美玲")
    view = StudentRecordsView(store)
    qtbot.addWidget(view)
    view.show()
    view.show_student(other.id)
    assert (len(view.stack.cards), view.empty.isVisible()) == (0, True)


def test_no_student_selected_shows_nothing(qtbot, store):
    view = StudentRecordsView(store)
    qtbot.addWidget(view)
    assert (view.title.text(), len(view.stack.cards)) == ("", 0)


def test_refresh_picks_up_a_new_record(view, store, student):
    store.add_record(student.id, date(2026, 10, 20), "新竹國小", "新的")
    view.refresh()
    assert card_dates(view)[0] == "2026-10-20"


def test_cards_start_folded_each_one_step_below_the_previous(view):
    assert [card.y() for card in view.stack.cards] == [16, 72, 128]


def test_hovering_a_card_lifts_it_and_pushes_the_ones_below_down(qtbot, view):
    view.stack.set_hovered(0)
    qtbot.waitUntil(lambda: [c.y() for c in view.stack.cards] == [8, 164, 220], timeout=2000)


def test_leaving_the_stack_folds_the_cards_again(qtbot, view):
    view.stack.set_hovered(0)
    qtbot.waitUntil(lambda: view.stack.cards[1].y() == 164, timeout=2000)
    view.stack.set_hovered(None)
    qtbot.waitUntil(lambda: [c.y() for c in view.stack.cards] == [16, 72, 128], timeout=2000)


def test_hovering_the_next_card_hands_the_lift_over(qtbot, view):
    view.stack.set_hovered(0)
    qtbot.waitUntil(lambda: view.stack.cards[1].y() == 164, timeout=2000)
    view.stack.set_hovered(1)
    qtbot.waitUntil(lambda: [c.y() for c in view.stack.cards] == [16, 64, 220], timeout=2000)


def test_each_card_has_a_shadow_just_below_it_that_ignores_the_mouse(view):
    stack = view.stack
    children = stack.children()
    for card, shadow in zip(stack.cards, stack._shadows):
        assert children.index(shadow) == children.index(card) - 1
        assert shadow.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert shadow.geometry().contains(card.geometry())


def test_cards_have_no_graphics_effect_to_reblur_on_every_frame(view):
    assert [card.graphicsEffect() for card in view.stack.cards] == [None, None, None]


def test_date_label_includes_weekday():
    assert date_label(date(2026, 10, 1)) == "2026-10-01  週四"


def test_preview_keeps_first_three_lines():
    assert preview_text("一\n二\n\n三\n四", "") == "一\n二\n三"


def test_preview_falls_back_to_english_text():
    assert preview_text("", "English only") == "English only"


def test_preview_of_empty_record_says_so():
    assert preview_text("  ", "") == "（尚無內容）"


def test_preview_is_cut_with_ellipsis_when_long():
    assert preview_text("字" * 200, "") == "字" * 140 + "…"

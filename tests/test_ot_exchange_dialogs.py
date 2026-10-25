from datetime import date

import pytest
from PySide6.QtCore import QDate, Qt

from datafuzzy.core.pipeline import Pipeline
from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.exchange import export_range
from datafuzzy.ot.ui.exchange_dialogs import ExportDialog, ImportDialog

KEY = bytes(range(32))
FIRST = "=== REC-1 | [PERSON_A] | 2026-10-01 ===\n"
SECOND = "=== REC-2 | [PERSON_A] | 2026-10-08 ===\n"


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


@pytest.fixture
def charts(store):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1), "新竹國小", "王小明今天練習剪紙")
    store.add_record(student.id, date(2026, 10, 8), "新竹國小", "王小明今天練習畫畫")
    return store


def run_export(qtbot, store, from_day, to_day):
    dialog = ExportDialog(store, Pipeline(), today=date(2026, 10, 10))
    qtbot.addWidget(dialog)
    dialog.from_edit.setDate(QDate(*from_day))
    dialog.to_edit.setDate(QDate(*to_day))
    with qtbot.waitSignal(dialog.exported, timeout=10000):
        dialog.export_btn.click()
    return dialog


def make_import(qtbot, store, text, confirm=lambda count: True):
    dialog = ImportDialog(store, confirm=confirm)
    qtbot.addWidget(dialog)
    dialog.paste.setPlainText(text)
    dialog.preview_btn.click()
    return dialog


def test_export_dialog_defaults_to_the_last_seven_days(qtbot, store):
    dialog = ExportDialog(store, Pipeline(), today=date(2026, 10, 10))
    qtbot.addWidget(dialog)
    assert (dialog.from_edit.date(), dialog.to_edit.date()) == (QDate(2026, 10, 4), QDate(2026, 10, 10))


def test_export_dialog_shows_text_with_names_replaced_by_codes(qtbot, charts):
    dialog = run_export(qtbot, charts, (2026, 10, 1), (2026, 10, 1))
    assert dialog.text.toPlainText() == "=== REC-1 | [PERSON_A] | 2026-10-01 ===\n[PERSON_A]今天練習剪紙\n"


def test_export_dialog_reports_how_many_charts_were_exported(qtbot, charts):
    dialog = run_export(qtbot, charts, (2026, 10, 1), (2026, 10, 8))
    assert dialog.status.text().startswith("已匯出 2 份病歷")


def test_export_dialog_warns_when_no_model_is_installed(qtbot, charts):
    dialog = run_export(qtbot, charts, (2026, 10, 1), (2026, 10, 1))
    assert "偵測模型未安裝" in dialog.status.text()


def test_export_dialog_says_when_range_has_no_charts(qtbot, charts):
    dialog = run_export(qtbot, charts, (2026, 11, 1), (2026, 11, 30))
    assert (dialog.status.text(), dialog.copy_btn.isEnabled()) == ("這段期間沒有病歷。", False)


def test_export_dialog_rejects_reversed_range_without_exporting(qtbot, charts):
    dialog = ExportDialog(charts, Pipeline(), today=date(2026, 10, 10))
    qtbot.addWidget(dialog)
    dialog.from_edit.setDate(QDate(2026, 10, 9))
    dialog.to_edit.setDate(QDate(2026, 10, 1))
    dialog.export_btn.click()
    assert (dialog.status.text(), charts.batches()) == ("開始日期晚於結束日期。", [])


def test_copy_button_puts_the_exported_text_on_the_clipboard(qtbot, qapp, charts):
    dialog = run_export(qtbot, charts, (2026, 10, 1), (2026, 10, 1))
    dialog.copy_btn.click()
    assert qapp.clipboard().text() == "=== REC-1 | [PERSON_A] | 2026-10-01 ===\n[PERSON_A]今天練習剪紙\n"


def test_copy_button_confirms_it_copied(qtbot, charts):
    dialog = run_export(qtbot, charts, (2026, 10, 1), (2026, 10, 1))
    dialog.copy_btn.click()
    assert dialog.copy_btn.text() == "已複製 ✓"


def test_apply_is_disabled_before_anything_is_checked(qtbot, charts):
    dialog = ImportDialog(charts)
    qtbot.addWidget(dialog)
    assert dialog.apply_btn.isEnabled() is False


def test_import_dialog_lists_the_charts_found_in_pasted_text(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    dialog = make_import(qtbot, charts, FIRST + "[PERSON_A] cut paper.\n\n" + SECOND + "[PERSON_A] drew.\n")
    assert [dialog.items.item(i).text() for i in range(dialog.items.count())] == [
        "王小明 · 2026-10-01", "王小明 · 2026-10-08"]


def test_import_dialog_applies_restored_english_text(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    dialog = make_import(qtbot, charts, FIRST + "[PERSON_A] cut paper.\n")
    with qtbot.waitSignal(dialog.applied, timeout=1000) as applied:
        dialog.apply_btn.click()
    assert applied.args == [1]
    assert charts.get_record(1).en_text == "王小明 cut paper."


def test_import_dialog_does_not_write_when_preview_only(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    make_import(qtbot, charts, FIRST + "[PERSON_A] cut paper.\n")
    assert charts.get_record(1).en_text == ""


def test_import_dialog_asks_before_overwriting_and_writes_when_confirmed(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    charts.update_record(1, en_text="old version")
    asked = []
    dialog = make_import(qtbot, charts, FIRST + "new version\n", confirm=lambda count: asked.append(count) or True)
    dialog.apply_btn.click()
    assert asked == [1]
    assert charts.get_record(1).en_text == "new version"


def test_import_dialog_keeps_old_english_text_when_overwrite_is_declined(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    charts.update_record(1, en_text="old version")
    dialog = make_import(qtbot, charts, FIRST + "new version\n", confirm=lambda count: False)
    dialog.apply_btn.click()
    assert charts.get_record(1).en_text == "old version"


def test_import_dialog_marks_charts_that_would_overwrite(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    charts.update_record(1, en_text="old version")
    dialog = make_import(qtbot, charts, FIRST + "new version\n")
    assert dialog.items.item(0).text() == "王小明 · 2026-10-01　⚠ 會覆蓋既有英文版"


def test_import_dialog_does_not_ask_when_nothing_is_overwritten(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    asked = []
    dialog = make_import(qtbot, charts, FIRST + "text\n", confirm=lambda count: asked.append(count) or True)
    dialog.apply_btn.click()
    assert asked == []


def test_unchecked_chart_is_not_written(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    dialog = make_import(qtbot, charts, FIRST + "one\n\n" + SECOND + "two\n")
    dialog.items.item(0).setCheckState(Qt.CheckState.Unchecked)
    dialog.apply_btn.click()
    assert [charts.get_record(1).en_text, charts.get_record(2).en_text] == ["", "two"]


def test_import_dialog_lists_charts_not_pasted_back(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    dialog = make_import(qtbot, charts, FIRST + "one\n")
    assert dialog.notes.text() == "沒貼回：王小明 · 2026-10-08"


def test_import_dialog_lists_unrecognized_headers_with_reason(qtbot, charts):
    export_range(charts, date(2026, 10, 1), date(2026, 10, 8), Pipeline())
    dialog = make_import(qtbot, charts, FIRST + "one\n\n=== REC-99 | [PERSON_A] | 2026-10-05 ===\nstray\n" + SECOND + "two\n")
    assert dialog.notes.text() == "不認得的標頭（這份匯出沒有這筆病歷）：=== REC-99 | [PERSON_A] | 2026-10-05 ==="


def test_import_dialog_explains_text_that_matches_no_export(qtbot, charts):
    dialog = make_import(qtbot, charts, "沒有標頭的文字")
    assert dialog.status.text().startswith("無法對應到匯出")
    assert dialog.apply_btn.isEnabled() is False

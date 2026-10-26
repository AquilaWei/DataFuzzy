from datetime import date, datetime, timedelta

import pytest
from openpyxl import load_workbook
from PySide6.QtCore import QDate

from datafuzzy.ot.db import RecordStore, StudentProfile
from datafuzzy.ot.excel_export import (
    build_workbook,
    file_name,
    group_by_location,
    header_text,
    sheet_title,
    write_workbook,
)
from datafuzzy.ot.ui.exchange_dialogs import ExcelExportDialog

KEY = bytes(range(32))
TODAY = date(2026, 10, 25)


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


@pytest.fixture
def charts(store):
    ming = store.add_student("王小明")
    amy = store.add_student("Amy")
    store.add_record(ming.id, date(2026, 10, 8), "Lincoln", "中文", "Worked on cutting.", activity="剪紙")
    store.add_record(ming.id, date(2026, 10, 1), "Lincoln", "中文", "Drew circles.", activity="畫畫")
    store.add_record(amy.id, date(2026, 10, 2), "Lincoln", activity="鞦韆")
    store.add_record(amy.id, date(2026, 10, 3), "新竹國小", en_text="Balance.")
    store.add_record(amy.id, date(2026, 10, 4), "", en_text="No place.")
    return store


def test_file_name_is_the_student_and_the_exported_period():
    assert file_name("王小明", date(2026, 10, 1), date(2026, 10, 31)) == "王小明-2026-10-01至2026-10-31.xlsx"


def test_file_name_drops_characters_no_file_system_accepts():
    assert file_name("Amy/Lee: ?", date(2026, 10, 1), date(2026, 10, 31)) == "AmyLee-2026-10-01至2026-10-31.xlsx"


def test_file_name_can_lead_with_the_location():
    assert (file_name("Amy", date(2026, 10, 1), date(2026, 10, 31), "Lincoln")
            == "Lincoln-Amy-2026-10-01至2026-10-31.xlsx")


def test_sheet_titles_are_valid_and_unique():
    used: set[str] = set()
    assert sheet_title("Amy/Lee", used) == "AmyLee"
    assert sheet_title("amylee", used) == "amylee (2)"
    long = sheet_title("x" * 40, used)
    assert len(long) == 31
    assert sheet_title("x" * 40, used) == "x" * 27 + " (2)"


def test_records_are_grouped_by_location(charts):
    groups, unassigned = group_by_location(charts.records_between(date(2026, 10, 1), date(2026, 10, 31)))
    assert {k: len(v) for k, v in groups.items()} == {"Lincoln": 3, "新竹國小": 1}
    assert [r.en_text for r in unassigned] == ["No place."]


def test_workbook_has_a_sheet_per_student_filled_oldest_first(charts, tmp_path):
    groups, _ = group_by_location(charts.records_between(date(2026, 10, 1), date(2026, 10, 31)))
    path = tmp_path / "out.xlsx"
    write_workbook(charts, groups["Lincoln"], path)
    wb = load_workbook(path)
    assert wb.sheetnames == ["Amy", "王小明"]
    ws = wb["王小明"]
    assert ws["A1"].value.startswith("Name:")
    assert ws["A2"].value == "Goals:"
    assert (ws["A4"].value, ws["B4"].value, ws["D4"].value) == (datetime(2026, 10, 1), "畫畫", "Drew circles.")
    assert (ws["A7"].value, ws["B7"].value, ws["D7"].value) == (datetime(2026, 10, 8), "剪紙", "Worked on cutting.")
    assert ws["A10"].value is None
    assert {"A4:A6", "B4:C6", "D4:K6"} <= {str(r) for r in ws.merged_cells.ranges}
    assert (wb["Amy"]["B4"].value, wb["Amy"]["D4"].value) == ("鞦韆", None)


def test_header_lists_the_profile_and_school_year():
    profile = StudentProfile(diagnosis="ADHD, ODD", age="8", grade="3", classroom="301",
                             case_manager="Ms. Lee", school_year="09/2026-06/2027")
    assert header_text("王小明", profile, TODAY) == (
        "Name: 王小明 / Diagnosis: ADHD, ODD / Age: 8 / Grade: 3 / Classroom: 301 / "
        "Case manager: Ms. Lee\nSchool year: 09/2026-06/2027")


def test_header_without_a_school_year_uses_the_current_one():
    assert header_text("Amy", StudentProfile(), date(2027, 3, 1)).endswith("School year: 09/2026-06/2027")


def test_sheet_header_is_filled_from_the_students_profile(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(diagnosis="ADHD", goals="Fine motor\nSelf-care"))
    store.add_record(student.id, date(2026, 10, 1), "Lincoln", en_text="Drew.")
    ws = build_workbook(store, store.records_for_student(student.id), today=TODAY)["王小明"]
    assert ws["A1"].value.startswith("Name: 王小明 / Diagnosis: ADHD / ")
    assert ws["A2"].value == "Goals: Fine motor\nSelf-care"
    assert ws.row_dimensions[2].height == 32


def test_more_visits_than_the_template_has_slots(store, tmp_path):
    student = store.add_student("王小明")
    for i in range(12):
        store.add_record(student.id, date(2026, 10, 1) + timedelta(days=i), "Lincoln", en_text=f"day {i}")
    path = tmp_path / "out.xlsx"
    write_workbook(store, store.records_for_student(student.id), path)
    ws = load_workbook(path)["王小明"]
    assert ws["D34"].value == "day 10"
    assert ws["D37"].value == "day 11"
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert {"A37:A39", "B37:C39", "D37:K39"} <= merged
    assert ws["A39"].border.bottom.style == "thin"


def make_dialog(qtbot, store, confirm=lambda path: True, folder=""):
    dialog = ExcelExportDialog(store, today=TODAY, confirm=confirm, choose=lambda start: folder)
    qtbot.addWidget(dialog)
    dialog.from_edit.setDate(QDate(2026, 10, 1))
    dialog.to_edit.setDate(QDate(2026, 10, 31))
    return dialog


def pick(dialog, location, name):
    dialog.location_box.setCurrentText(location)
    dialog.student_box.setCurrentIndex(
        [dialog.student_box.itemText(i).split("（")[0] for i in range(dialog.student_box.count())].index(name))
    dialog.add_btn.click()


def table_rows(dialog):
    return [tuple(dialog.table.item(r, c).text() for c in range(3)) for r in range(dialog.table.rowCount())]


def test_location_drop_down_lists_locations_with_visits_in_the_period(qtbot, charts):
    dialog = make_dialog(qtbot, charts)
    assert dialog.locations() == ["Lincoln", "新竹國小"]
    assert "1 份病歷沒有填地點" in dialog.status.text()


def test_student_drop_down_lists_who_was_seen_at_the_location(qtbot, charts):
    dialog = make_dialog(qtbot, charts)
    dialog.location_box.setCurrentText("Lincoln")
    assert [dialog.student_box.itemText(i) for i in range(dialog.student_box.count())] == [
        "Amy（1 份）", "王小明（2 份）"]


def test_picked_students_are_added_to_the_list_once(qtbot, charts):
    dialog = make_dialog(qtbot, charts)
    pick(dialog, "Lincoln", "王小明")
    pick(dialog, "Lincoln", "王小明")
    pick(dialog, "新竹國小", "Amy")
    assert table_rows(dialog) == [("Lincoln", "王小明", "2"), ("新竹國小", "Amy", "1")]


def test_add_all_adds_everyone_seen_at_the_location(qtbot, charts):
    dialog = make_dialog(qtbot, charts)
    dialog.location_box.setCurrentText("Lincoln")
    dialog.add_all_btn.click()
    assert table_rows(dialog) == [("Lincoln", "Amy", "1"), ("Lincoln", "王小明", "2")]


def test_remove_takes_the_selected_row_off_the_list(qtbot, charts):
    dialog = make_dialog(qtbot, charts)
    pick(dialog, "Lincoln", "王小明")
    pick(dialog, "Lincoln", "Amy")
    dialog.table.selectRow(0)
    dialog.remove_btn.click()
    assert table_rows(dialog) == [("Lincoln", "Amy", "1")]


def test_export_needs_a_folder(qtbot, charts):
    dialog = make_dialog(qtbot, charts)
    pick(dialog, "Lincoln", "王小明")
    assert not dialog.export_btn.isEnabled()


def test_folder_is_remembered(qtbot, charts, tmp_path):
    dialog = make_dialog(qtbot, charts, folder=str(tmp_path))
    dialog.folder_btn.click()
    assert charts.excel_folder() == str(tmp_path)
    assert dialog.folder_label.text() == str(tmp_path)


def test_each_student_gets_a_file_with_only_that_locations_visits(qtbot, charts, tmp_path):
    charts.set_excel_folder(str(tmp_path))
    dialog = make_dialog(qtbot, charts)
    pick(dialog, "Lincoln", "王小明")
    pick(dialog, "新竹國小", "Amy")
    dialog.export_btn.click()
    ming = tmp_path / "王小明-2026-10-01至2026-10-31.xlsx"
    amy = tmp_path / "Amy-2026-10-01至2026-10-31.xlsx"
    assert dialog.written == [ming, amy]
    assert load_workbook(ming).sheetnames == ["王小明"]
    assert load_workbook(amy)["Amy"]["D4"].value == "Balance."
    assert load_workbook(amy)["Amy"]["A7"].value is None
    assert dialog.result() == dialog.DialogCode.Accepted


def test_one_student_at_two_locations_gets_the_location_in_front(qtbot, charts, tmp_path):
    charts.set_excel_folder(str(tmp_path))
    dialog = make_dialog(qtbot, charts)
    pick(dialog, "Lincoln", "Amy")
    pick(dialog, "新竹國小", "Amy")
    dialog.export_btn.click()
    assert [p.name for p in dialog.written] == [
        "Lincoln-Amy-2026-10-01至2026-10-31.xlsx", "新竹國小-Amy-2026-10-01至2026-10-31.xlsx"]


def test_dialog_asks_before_replacing_a_file(qtbot, charts, tmp_path):
    charts.set_excel_folder(str(tmp_path))
    old = tmp_path / "王小明-2026-10-01至2026-10-31.xlsx"
    old.write_bytes(b"old")
    asked = []
    dialog = make_dialog(qtbot, charts, confirm=lambda path: asked.append(path) or False)
    pick(dialog, "Lincoln", "王小明")
    dialog.export_btn.click()
    assert asked == [old]
    assert old.read_bytes() == b"old"
    assert dialog.written == []
    assert dialog.result() != dialog.DialogCode.Accepted

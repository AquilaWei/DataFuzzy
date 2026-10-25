from datetime import date, datetime, timedelta

import pytest
from openpyxl import load_workbook
from PySide6.QtCore import QDate

from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.excel_export import file_name, group_by_location, sheet_title, write_location
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


def test_file_name_uses_location_and_day():
    assert file_name("Lincoln", TODAY) == "Lincoln-2026-10-25.xlsx"
    assert file_name("A/B: school?", TODAY) == "AB school-2026-10-25.xlsx"


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
    write_location(charts, groups["Lincoln"], path)
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


def test_more_visits_than_the_template_has_slots(store, tmp_path):
    student = store.add_student("王小明")
    for i in range(12):
        store.add_record(student.id, date(2026, 10, 1) + timedelta(days=i), "Lincoln", en_text=f"day {i}")
    path = tmp_path / "out.xlsx"
    write_location(store, store.records_for_student(student.id), path)
    ws = load_workbook(path)["王小明"]
    assert ws["D34"].value == "day 10"
    assert ws["D37"].value == "day 11"
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert {"A37:A39", "B37:C39", "D37:K39"} <= merged
    assert ws["A39"].border.bottom.style == "thin"


def make_dialog(qtbot, store, confirm=lambda path: True, folder=""):
    dialog = ExcelExportDialog(store, today=TODAY, confirm=confirm, choose=lambda loc, start: folder)
    qtbot.addWidget(dialog)
    dialog.from_edit.setDate(QDate(2026, 10, 1))
    dialog.to_edit.setDate(QDate(2026, 10, 31))
    return dialog


def test_dialog_lists_locations_and_needs_a_folder(qtbot, charts):
    dialog = make_dialog(qtbot, charts)
    assert dialog.locations() == ["Lincoln", "新竹國小"]
    assert not dialog.export_btn.isEnabled()
    assert "1 份病歷沒有填地點" in dialog.status.text()


def test_dialog_remembers_folder_and_writes_one_file_per_location(qtbot, charts, tmp_path):
    dialog = make_dialog(qtbot, charts, folder=str(tmp_path / "lincoln"))
    dialog.choose_folder(0)
    assert charts.excel_folders() == {"Lincoln": str(tmp_path / "lincoln")}
    assert dialog.export_btn.isEnabled()
    dialog.export_btn.click()
    out = tmp_path / "lincoln" / "Lincoln-2026-10-25.xlsx"
    assert dialog.written == [out]
    assert load_workbook(out).sheetnames == ["Amy", "王小明"]
    assert "略過「新竹國小」" in dialog.status.text()


def test_dialog_asks_before_replacing_a_file(qtbot, charts, tmp_path):
    charts.set_excel_folder("Lincoln", str(tmp_path))
    old = tmp_path / "Lincoln-2026-10-25.xlsx"
    old.write_bytes(b"old")
    asked = []
    dialog = make_dialog(qtbot, charts, confirm=lambda path: asked.append(path) or False)
    dialog.export_btn.click()
    assert asked == [old]
    assert old.read_bytes() == b"old"
    assert dialog.written == []

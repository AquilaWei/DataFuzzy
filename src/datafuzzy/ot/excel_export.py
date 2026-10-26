"""Writing charts into the school's Excel form: one workbook per student and location, each
visit's date, activity and English chart in a slot of the template."""

from __future__ import annotations

import re
from collections.abc import Iterable
from copy import copy
from datetime import date
from importlib.resources import as_file, files
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment
from openpyxl.worksheet.worksheet import Worksheet

from .db import Record, RecordStore, Student, StudentProfile
from .school_year import default_school_year, format_school_year

TEMPLATE_SHEET = "blank"
FIRST_SLOT_ROW = 4
SLOT_ROWS = 3
TEMPLATE_SLOTS = 10
LAST_COLUMN = 11  # K
DATE_FORMAT = "yyyy-mm-dd"
HEADER_LINE_HEIGHT = 16  # points per line of the Goals row

_FILE_UNSAFE = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
_SHEET_UNSAFE = re.compile(r"[\[\]:*?/\\]")
SHEET_TITLE_MAX = 31


def group_by_location(records: Iterable[Record]) -> tuple[dict[str, list[Record]], list[Record]]:
    """Records per location, in the order given, and the records that have no location."""
    groups: dict[str, list[Record]] = {}
    unassigned: list[Record] = []
    for record in records:
        if record.location.strip():
            groups.setdefault(record.location.strip(), []).append(record)
        else:
            unassigned.append(record)
    return groups, unassigned


def _safe(text: str, fallback: str) -> str:
    return _FILE_UNSAFE.sub("", text).strip(" .") or fallback


def file_name(name: str, date_from: date, date_to: date, location: str | None = None) -> str:
    """`<name>-<from>至<to>.xlsx`, or `<location>-<name>-…` to tell apart two files of one name,
    with characters no file system accepts removed."""
    prefix = f"{_safe(location, 'location')}-" if location is not None else ""
    return f"{prefix}{_safe(name, 'student')}-{date_from.isoformat()}至{date_to.isoformat()}.xlsx"


def sheet_title(name: str, used: set[str]) -> str:
    """A valid, unused sheet title for `name`; adds it to `used` (compared case-insensitively,
    as Excel does)."""
    base = _SHEET_UNSAFE.sub("", name).strip("' ") or "student"
    title = base[:SHEET_TITLE_MAX]
    n = 2
    while title.lower() in used:
        suffix = f" ({n})"
        title = base[:SHEET_TITLE_MAX - len(suffix)] + suffix
        n += 1
    used.add(title.lower())
    return title


def header_text(name: str, profile: StudentProfile, today: date) -> str:
    """The form's first row: who the student is and the school year (this one when not set)."""
    school_year = profile.school_year or format_school_year(*default_school_year(today))
    return (f"Name: {name} / Diagnosis: {profile.diagnosis} / Age: {profile.age} / "
            f"Grade: {profile.grade} / Classroom: {profile.classroom} / "
            f"Case manager: {profile.case_manager}\nSchool year: {school_year}")


def _fill_header(ws: Worksheet, student: Student, profile: StudentProfile, today: date) -> None:
    ws["A1"] = header_text(student.name, profile, today)
    goals = ws["A2"]
    goals.value = f"Goals: {profile.goals}" if profile.goals else "Goals:"
    goals.alignment = Alignment(vertical="top", wrap_text=True)
    lines = goals.value.count("\n") + 1
    if lines > 1:
        ws.row_dimensions[2].height = HEADER_LINE_HEIGHT * lines


def _load_template() -> Workbook:
    with as_file(files("datafuzzy.ot").joinpath("excel_template.xlsx")) as path:
        return load_workbook(path)


def _copy_slot_style(ws: Worksheet, slot: int) -> None:
    """Give slot `slot` (0-based, past the template's ten) the look of the last template slot."""
    source = FIRST_SLOT_ROW + SLOT_ROWS * (TEMPLATE_SLOTS - 1)
    top = FIRST_SLOT_ROW + SLOT_ROWS * slot
    for offset in range(SLOT_ROWS):
        for col in range(1, LAST_COLUMN + 1):
            src = ws.cell(source + offset, col)
            dst = ws.cell(top + offset, col)
            dst._style = copy(src._style)
    _merge_slot(ws, top)


def _merge_slot(ws: Worksheet, top: int) -> None:
    bottom = top + SLOT_ROWS - 1
    for cells in (f"A{top}:A{bottom}", f"B{top}:C{bottom}", f"D{top}:K{bottom}"):
        if cells not in ws.merged_cells:
            ws.merge_cells(cells)


def _fill(ws: Worksheet, records: list[Record]) -> None:
    for slot, record in enumerate(records):
        if slot >= TEMPLATE_SLOTS:
            _copy_slot_style(ws, slot)
        top = FIRST_SLOT_ROW + SLOT_ROWS * slot
        cells = ((1, record.visit_date), (2, record.activity), (4, record.en_text))
        for col, value in cells:
            cell = ws.cell(top, col)
            cell.value = value if value != "" else None
            cell.alignment = Alignment(horizontal=cell.alignment.horizontal,
                                       vertical="top", wrap_text=True)
        ws.cell(top, 1).number_format = DATE_FORMAT


def build_workbook(store: RecordStore, records: Iterable[Record], today: date | None = None) -> Workbook:
    """One sheet per student (by name), visits oldest first, the header filled from the
    student's profile; the template sheet is dropped."""
    by_student: dict[int, list[Record]] = {}
    for record in records:
        by_student.setdefault(record.student_id, []).append(record)
    students = sorted((store.get_student(sid) for sid in by_student), key=lambda s: (s.name, s.id))
    wb = _load_template()
    template = wb[TEMPLATE_SHEET]
    used: set[str] = set()
    for student in students:
        ws = wb.copy_worksheet(template)
        ws.title = sheet_title(student.name, used)
        # copy_worksheet leaves out the print settings.
        ws.page_setup.orientation = template.page_setup.orientation
        ws.page_margins = copy(template.page_margins)
        ws.sheet_view.zoomScale = template.sheet_view.zoomScale
        _fill_header(ws, student, store.get_profile(student.id), today or date.today())
        _fill(ws, sorted(by_student[student.id], key=lambda r: (r.visit_date, r.id)))
    wb.remove(template)
    for i, ws in enumerate(wb.worksheets):
        ws.sheet_view.tabSelected = i == 0
    if wb.worksheets:
        wb.active = 0
    return wb


def write_workbook(store: RecordStore, records: Iterable[Record], path: Path) -> None:
    build_workbook(store, records).save(path)

"""The ACE fill-in file: a range of charts as the cells of ACE Portal's weekly time grid, each
with the rows ace_mapping says to fill, for the browser extension (chrome-extension/) to enter
one cell at a time while the user checks each before saving.

The file holds the students' names and English charts unencrypted, so it is written only where
the user picks and they are told to delete it once the week is entered."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date

from .ace_mapping import TIMED_WITHOUT_TIMES, AceRow, ace_rows, group_names
from .db import COMMENT_TYPES, FULL_TYPES, Record, RecordStore

FORMAT = "theranote-ace/1"  # bumped whenever the extension must read the file differently

# Why a cell is left for the user to enter by hand; the extension shows these and fills nothing.
MANUAL_TYPE = "manual_type"  # a type ACE has no place for (Consult)
NO_ENGLISH = "no_english"  # ACE asks for English text the chart does not have yet
NO_TIMES = "no_times"  # ACE asks for minutes or times the chart does not have
NO_GROUP = "no_group"  # a group chart without a start time, so no group to put it in


@dataclass
class AceCell:
    """One student on one day: a cell of ACE's weekly grid, found there by first and last name."""
    first: str
    last: str
    date: str  # "2026-11-10"
    rows: list[AceRow] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def chart_problems(record: Record, rows: list[AceRow] | None) -> list[str]:
    """What keeps `record` from being entered as its rows say (see the codes above)."""
    if rows is None:
        return [MANUAL_TYPE]
    main = rows[0]
    problems = []
    kind = record.session_type
    english = {"en_text": record.en_text.strip(), "en_followup": record.en_followup.strip()}
    needs_english = ("en_text", "en_followup") if kind in FULL_TYPES else ("en_text",) if kind in COMMENT_TYPES else ()
    if not all(english[part] for part in needs_english):
        problems.append(NO_ENGLISH)
    needs_minutes = (kind in FULL_TYPES or kind in COMMENT_TYPES or kind in TIMED_WITHOUT_TIMES
                     or main.section == "indirect")
    if needs_minutes and main.minutes is None:
        problems.append(NO_TIMES)
    if main.section == "group" and not main.group:
        problems.append(NO_GROUP)
    return problems


def ace_cells(store: RecordStore, date_from: date, date_to: date) -> list[AceCell]:
    """The cells for the charts from `date_from` to `date_to` (inclusive), by day, then name.

    Reads the charts in the range and, for their students only, the name and the profile's MA
    billing setting. Groups are counted over every student's charts in the range."""
    records = store.records_between(date_from, date_to)
    groups = group_names(records)
    students = {sid: store.get_student(sid) for sid in {r.student_id for r in records}}
    ma_billing = {sid: store.get_profile(sid).ma_billing for sid in students}
    cells: dict[tuple[date, int], AceCell] = {}
    for record in records:
        student = students[record.student_id]
        cell = cells.setdefault((record.visit_date, student.id), AceCell(
            student.given_name, student.family_name, record.visit_date.isoformat()))
        rows = ace_rows(record, ma_billing[student.id], groups.get(record.id, ("", 0)))
        cell.rows.extend(rows or [])
        cell.problems.extend(p for p in chart_problems(record, rows) if p not in cell.problems)
    return sorted(cells.values(), key=lambda c: (c.date, c.last.casefold(), c.first.casefold()))


def to_json(cells: list[AceCell], date_from: date, date_to: date) -> str:
    """The file's text; `date_from`..`date_to` is the week the extension checks the grid shows."""
    return json.dumps({"format": FORMAT, "week": [date_from.isoformat(), date_to.isoformat()],
                       "cells": [asdict(cell) for cell in cells]}, ensure_ascii=False, indent=1)

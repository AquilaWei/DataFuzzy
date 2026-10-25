"""Sending charts out for translation and taking the corrected English text back in.

`export_range` replaces people's names in the Chinese texts with codes (the student's own
name always, even with no model installed) and keeps the code mapping encrypted in the
database. The text that comes back has the same headers, so it can be split into charts
again and the codes turned back into names.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from . import APP_NAME
from ..core.mapping import PERSON, Session
from .db import RecordStore

if TYPE_CHECKING:
    from ..core.pipeline import Pipeline

HEADER_FORMAT = "=== REC-{record_id} | {code} | {visit_date} ==="


@dataclass(frozen=True)
class ExportResult:
    text: str                # headers and obfuscated Chinese texts, ready to copy
    batch_id: int | None     # the saved code mapping; None when the range had no records
    record_count: int


def export_range(store: RecordStore, date_from: date, date_to: date,
                 pipeline: Pipeline) -> ExportResult:
    """Export every record from `date_from` to `date_to` (inclusive), oldest first.

    Only people's names are coded ("names" scope). Every student's name is marked before any
    text is processed, so it is coded even where no model finds it, and also where another
    student's chart mentions them. One session covers the batch: the same person gets the
    same code in every chart. The mapping is saved encrypted; it may block while a model
    runs, so call it from a worker for a large range."""
    records = store.records_between(date_from, date_to)
    if not records:
        return ExportResult("", None, 0)
    names = {s.id: s.name for s in store.students()}
    session = Session(label=f"{APP_NAME} {date_from.isoformat()} ~ {date_to.isoformat()}")
    for record in records:
        session.mark(names[record.student_id], PERSON)
    blocks: list[str] = []
    entries: list[dict] = []
    for record in records:
        code = session.to_code[names[record.student_id]]
        body = pipeline.obfuscate(record.zh_text, session, scope="names").text
        header = HEADER_FORMAT.format(record_id=record.id, code=code, visit_date=record.visit_date.isoformat())
        blocks.append(f"{header}\n{body}\n")
        entries.append({"record_id": record.id, "code": code, "date": record.visit_date.isoformat()})
    batch_id = store.add_batch({
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "entries": entries,
        "session": session.to_dict(),
    })
    return ExportResult("\n".join(blocks), batch_id, len(records))

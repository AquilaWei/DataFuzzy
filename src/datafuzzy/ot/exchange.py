"""Sending charts out for translation and taking the corrected English text back in.

`export_range` replaces people's names in the Chinese texts with codes (the student's own
name always, even with no model installed) and keeps the code mapping encrypted in the
database. The text that comes back has the same headers, so it can be split into charts
again and the codes turned back into names.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from ..core.mapping import PERSON, Session
from . import APP_NAME
from .db import RecordStore, StoredBatch

if TYPE_CHECKING:
    from ..core.pipeline import Pipeline

HEADER_FORMAT = "=== REC-{record_id} | {code} | {visit_date} ==="
# Any line wrapped in "===": the strict form below is parsed from it, so a header the
# translator damaged is reported instead of being swallowed into the previous chart.
HEADER_LINE_RE = re.compile(r"^[ \t]*===.*===[ \t]*$", re.MULTILINE)
HEADER_RE = re.compile(r"^=== *REC-(\d+) *\| *(.+?) *\| *(\d{4}-\d{2}-\d{2}) *===$")


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


class ImportMismatch(Exception):
    """The pasted text cannot be matched to an export: no headers, or no saved batch
    they belong to."""


@dataclass(frozen=True)
class PastedBlock:
    header: str              # the header line as pasted
    record_id: int | None    # None when the header is damaged beyond reading
    code: str
    visit_date: str
    body: str


def parse_pasted(text: str) -> list[PastedBlock]:
    """Split pasted text at its `=== ... ===` header lines. Text before the first header
    is ignored."""
    lines = list(HEADER_LINE_RE.finditer(text))
    blocks: list[PastedBlock] = []
    for i, line in enumerate(lines):
        end = lines[i + 1].start() if i + 1 < len(lines) else len(text)
        header = line.group().strip()
        body = text[line.end():end].strip()
        parts = HEADER_RE.match(header)
        if parts:
            blocks.append(PastedBlock(header, int(parts[1]), parts[2], parts[3], body))
        else:
            blocks.append(PastedBlock(header, None, "", "", body))
    return blocks


@dataclass(frozen=True)
class BatchEntry:
    record_id: int
    code: str
    visit_date: str


@dataclass(frozen=True)
class ExportBatch:
    id: int
    created_at: datetime
    entries: dict[int, BatchEntry]    # record id -> what its header said
    session: Session

    @classmethod
    def from_stored(cls, stored: StoredBatch) -> ExportBatch:
        entries = [BatchEntry(e["record_id"], e["code"], e["date"]) for e in stored.data["entries"]]
        return cls(stored.id, stored.created_at, {e.record_id: e for e in entries},
                   Session.from_dict(stored.data["session"]))

    def header_matches(self, block: PastedBlock) -> bool:
        entry = self.entries.get(block.record_id)
        return entry is not None and (entry.code, entry.visit_date) == (block.code, block.visit_date)


def find_batch(store: RecordStore, text: str, blocks: list[PastedBlock]) -> ExportBatch | None:
    """The export the pasted text came from. Headers carry no batch id (the translator may
    drop any extra line), so each saved batch is scored by how many pasted headers match
    its record id, code and date, then by how many body codes it can restore; a tie goes
    to the newest batch. None if no header matches any batch."""
    best: tuple[tuple[int, int, int], ExportBatch] | None = None
    for stored in store.batches():
        batch = ExportBatch.from_stored(stored)
        score = (sum(batch.header_matches(b) for b in blocks), batch.session.match_count(text), batch.id)
        if score[0] and (best is None or score > best[0]):
            best = (score, batch)
    return best[1] if best else None


@dataclass(frozen=True)
class ImportItem:
    """One chart that can be written back."""
    record_id: int
    student_name: str         # the header's code turned back into a name
    visit_date: date
    en_text: str              # the pasted text with names restored
    overwrites: bool          # the record already has a different English text
    unknown_codes: list[str]  # codes in the text that this export never issued


@dataclass(frozen=True)
class MissingRecord:
    """Exported, but not found (or not readable) in the pasted text."""
    record_id: int
    student_name: str
    visit_date: date


@dataclass(frozen=True)
class UnrecognizedHeader:
    header: str
    # malformed: not "=== REC-<id> | <code> | <date> ==="; not_in_export: a record this
    # batch never contained; header_changed: code or date differs from the export;
    # duplicate: the record id appeared before.
    reason: Literal["malformed", "not_in_export", "header_changed", "duplicate"]


@dataclass(frozen=True)
class ImportPreview:
    """What pasting would do, so the user can confirm before anything is written."""
    batch_id: int
    items: list[ImportItem]
    missing: list[MissingRecord]
    unrecognized: list[UnrecognizedHeader]

    @property
    def overwriting(self) -> list[ImportItem]:
        """Items that would replace an English text already there; confirm these first."""
        return [i for i in self.items if i.overwrites]


def preview_import(store: RecordStore, text: str, batch_id: int | None = None) -> ImportPreview:
    """Match pasted text to its export and report what would be written; writes nothing.

    `batch_id` forces a batch; otherwise it is found from the headers. Raises ImportMismatch
    if there are no headers or no matching batch, NotFound for an unknown `batch_id`."""
    blocks = parse_pasted(text)
    if not blocks:
        raise ImportMismatch("no '=== REC-... ===' headers found in the pasted text")
    if batch_id is None:
        batch = find_batch(store, text, blocks)
        if batch is None:
            raise ImportMismatch("the pasted headers match none of the saved exports")
    else:
        batch = ExportBatch.from_stored(store.get_batch(batch_id))
    session = batch.session
    items: list[ImportItem] = []
    unrecognized: list[UnrecognizedHeader] = []
    seen: set[int] = set()
    for block in blocks:
        if block.record_id is None:
            unrecognized.append(UnrecognizedHeader(block.header, "malformed"))
        elif block.record_id not in batch.entries:
            unrecognized.append(UnrecognizedHeader(block.header, "not_in_export"))
        elif block.record_id in seen:
            unrecognized.append(UnrecognizedHeader(block.header, "duplicate"))
        elif not batch.header_matches(block):
            unrecognized.append(UnrecognizedHeader(block.header, "header_changed"))
        else:
            seen.add(block.record_id)
            record = store.get_record(block.record_id)
            restored = session.restore(block.body)
            items.append(ImportItem(
                block.record_id, session.restore(block.code).text, record.visit_date, restored.text,
                bool(record.en_text) and record.en_text != restored.text, restored.unknown))
    missing = [MissingRecord(e.record_id, session.restore(e.code).text, date.fromisoformat(e.visit_date))
               for e in batch.entries.values() if e.record_id not in seen]
    return ImportPreview(batch.id, items, missing, unrecognized)


def apply_import(store: RecordStore, preview: ImportPreview,
                 record_ids: Collection[int] | None = None) -> int:
    """Write the previewed English texts, all of them or only those in `record_ids`, in one
    transaction. Returns how many records were written. Raises NotFound if a record has
    disappeared since the preview, in which case nothing is written."""
    texts = {i.record_id: i.en_text for i in preview.items
             if record_ids is None or i.record_id in record_ids}
    store.set_en_texts(texts)
    return len(texts)

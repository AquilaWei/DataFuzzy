"""Booked sessions that will not happen: a whole weekday off (school closed, the therapist away,
students unavailable), or single bookings moved to a later week or cancelled.

A cancelled session still gets a chart, of the reason's service type, because ACE asks for one;
it takes the session's student, times and location. These are the rules; the dialogs that ask
for the choices live in ui/schedule_dialogs.py."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from .db import Record, RecordStore

# The reasons a session is called off, as ACE names their service types.
CANCEL_REASONS = ("School Not in Session", "Therapist Absent", "Unavailable Student")
POSTPONE_WEEKS = range(1, 9)  # how many weeks a booking can be put off by
LOOKAHEAD_DAYS = 31  # how far ahead a weekday off can be picked: a month


@dataclass(frozen=True)
class Slot:
    """A session to mark as cancelled: whose, and when on the day."""
    student_id: int
    start: str  # "HH:MM", or "" when not known
    end: str


def weekday_dates(weekday: int, today: date, days: int = LOOKAHEAD_DAYS) -> list[date]:
    """The dates that fall on `weekday` (Monday 0) from `today` on, for `days` days: about the
    next four or five of them. Today counts when it is that weekday."""
    first = today + timedelta(days=(weekday - today.weekday()) % 7)
    return [first + timedelta(weeks=n) for n in range((days - 1 - (first - today).days) // 7 + 1)]


def weekday_slots(store: RecordStore, weekday: int) -> list[tuple[str, Slot]]:
    """(student name, slot) for each weekly session of the active students on `weekday`, by
    start time then name, as the timetable shows them."""
    return [(student.name, Slot(student.id, session.start, session.end))
            for session, student in store.timetable() if session.weekday == weekday]


def clashes(store: RecordStore, day: date, student_ids: Iterable[int]) -> list[Record]:
    """The records of `student_ids` already on `day`, which a weekday off would replace."""
    wanted = set(student_ids)
    return sorted((r for r in store.records_on(day) if r.student_id in wanted),
                  key=lambda r: (r.start_time or "99:99", r.id))


def cancel_day(store: RecordStore, day: date, reason: str, slots: Iterable[Slot],
               move_ids: Iterable[int] = ()) -> list[Record]:
    """Mark the `slots` of `day` as called off for `reason`: each gets a chart of that type. The
    slots' students' records already on that day are moved a week on when in `move_ids` and
    deleted otherwise (the new chart takes their place). Returns the new charts. Raises
    ValueError for a reason not in CANCEL_REASONS, before anything is changed."""
    _check_reason(reason)
    slots = list(slots)
    move = set(move_ids)
    for record in clashes(store, day, {slot.student_id for slot in slots}):
        if record.id in move:
            store.move_record(record.id, day + timedelta(weeks=1))
        else:
            store.delete_record(record.id)
    return [store.add_record(slot.student_id, day, store.student_location(slot.student_id),
                             start_time=slot.start, end_time=slot.end, session_type=reason)
            for slot in slots]


def postpone(store: RecordStore, record_ids: Iterable[int], weeks: int) -> list[Record]:
    """Move each record `weeks` weeks later, keeping everything else. Raises NotFound for an
    unknown record (those before it are moved already)."""
    return [store.move_record(rid, store.get_record(rid).visit_date + timedelta(weeks=weeks))
            for rid in record_ids]


def cancel(store: RecordStore, record_ids: Iterable[int], reason: str,
           weeks: int | None = None) -> list[Record]:
    """Call off the bookings `record_ids` for `reason`: in their place, a chart of that type
    with the same student, day, times, location and mode. With `weeks`, each booking is first
    moved that many weeks on; without, it is deleted, chart and all. Returns the new charts.
    Raises ValueError for a reason not in CANCEL_REASONS, before anything is changed."""
    _check_reason(reason)
    made = []
    for rid in record_ids:
        record = store.get_record(rid)
        if weeks:
            store.move_record(rid, record.visit_date + timedelta(weeks=weeks))
        else:
            store.delete_record(rid)
        made.append(store.add_record(record.student_id, record.visit_date, record.location,
                                     start_time=record.start_time, end_time=record.end_time,
                                     session_type=reason, session_mode=record.session_mode))
    return made


def _check_reason(reason: str) -> None:
    if reason not in CANCEL_REASONS:
        raise ValueError(f"not a reason to cancel: {reason!r}")

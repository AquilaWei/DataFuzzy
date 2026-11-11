"""How a chart is entered in ACE Portal's time entry: which rows of its Direct, Group and Indirect
Time it fills, and with what. The ACE browser extension (not written yet) is meant to fill the
page from these rows, so the rules live here, where they can be tested."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from string import ascii_uppercase
from typing import Literal

from .db import COMMENT_TYPES, FULL_TYPES, NO_SHOW, Record

DOCUMENTATION_MINUTES = 5  # every chart's Documentation (Indirect Time), save the Indirect-only types
MA_BILLING_MINUTES = 5  # a therapy session's MA ACCESS Billing, for a student billed to MA
# Types ACE keeps under Indirect Time only, whichever the mode; they take no Documentation.
INDIRECT_TYPES = frozenset({"Collaboration", "Home Program", "IEP Meeting/Meeting", "Progress Report", "Scheduling"})
# Types with no ACE counterpart: left for the user to enter by hand.
UNMAPPED_TYPES = frozenset({"Consult"})
# TheraNote's names that ACE's drop-down spells otherwise.
ACE_NAMES = {NO_SHOW: "No Show"}
# Of the types ACE asks no time for, those that still take minutes.
TIMED_WITHOUT_TIMES = frozenset({"Annual IEP Report", NO_SHOW})


@dataclass(frozen=True)
class AceRow:
    section: Literal["direct", "group", "indirect"]
    type: str                       # as ACE's drop-down names it
    minutes: int | None = None      # None: ACE asks for none
    start: str = ""                 # "1:30 PM", for a therapy session
    end: str = ""
    comments_on_log: str = ""
    data_towards_goals: str = ""
    deficit: str = ""               # Underlying Deficits Addressed, for a therapy session
    group: str = ""                 # "Group A", for Group Time
    group_size: int = 0


def minutes_between(start: str, end: str) -> int | None:
    """Minutes from "HH:MM" to "HH:MM"; None if either is missing or the end is not later."""
    if not start or not end:
        return None
    (sh, sm), (eh, em) = ((int(p) for p in t.split(":")) for t in (start, end))
    minutes = (eh * 60 + em) - (sh * 60 + sm)
    return minutes if minutes > 0 else None


def ace_time(hhmm: str) -> str:
    """"13:30" as ACE's time drop-downs write it: "1:30 PM" ("" for "")."""
    if not hhmm:
        return ""
    hour, minute = (int(p) for p in hhmm.split(":"))
    return f"{(hour - 1) % 12 + 1}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def group_names(records: Iterable[Record]) -> dict[int, tuple[str, int]]:
    """Record id -> (group name, group size) for the group charts among `records`. A group is the
    group charts of one day that start at the same time, whoever the students; each day's groups
    are named Group A, Group B, … from the earliest. Charts without a start time form no group."""
    groups: dict[tuple, list[int]] = {}
    for record in records:
        if record.session_mode == "group" and record.start_time:
            groups.setdefault((record.visit_date, record.start_time), []).append(record.id)
    names: dict[int, tuple[str, int]] = {}
    letter: dict = {}
    for (day, _start), ids in sorted(groups.items()):
        index = letter[day] = letter.get(day, -1) + 1
        for record_id in ids:
            names[record_id] = (f"Group {ascii_uppercase[index % 26]}", len(ids))
    return names


def ace_rows(record: Record, ma_billing: bool, group: tuple[str, int] = ("", 0)) -> list[AceRow] | None:
    """The ACE rows for one chart, the Indirect ones last; None for a type ACE has no place
    for (see UNMAPPED_TYPES), to be entered by hand. `ma_billing` is the student's profile
    setting; `group` comes from group_names."""
    kind = record.session_type
    if kind in UNMAPPED_TYPES:
        return None
    minutes = minutes_between(record.start_time, record.end_time)
    documentation = AceRow("indirect", "Documentation", DOCUMENTATION_MINUTES)
    if kind in INDIRECT_TYPES:
        comments = record.en_text if kind in COMMENT_TYPES else ""
        return [AceRow("indirect", kind, minutes, comments_on_log=comments)]
    section = "group" if record.session_mode == "group" else "direct"
    name, size = group if section == "group" else ("", 0)
    if kind in FULL_TYPES:
        main = AceRow(section, kind, minutes, ace_time(record.start_time), ace_time(record.end_time),
                      comments_on_log=record.en_followup, data_towards_goals=record.en_text,
                      deficit=record.deficit, group=name, group_size=size)
        billing = [AceRow("indirect", "MA ACCESS Billing", MA_BILLING_MINUTES)] if ma_billing else []
        return [main, documentation, *billing]
    if kind in COMMENT_TYPES:
        main = AceRow(section, kind, minutes, comments_on_log=record.en_text, group=name, group_size=size)
    else:  # Absent Student, School Not in Session, …: no time, save for the minutes of TIMED_WITHOUT_TIMES
        main = AceRow(section, ACE_NAMES.get(kind, kind), minutes if kind in TIMED_WITHOUT_TIMES else None,
                      group=name, group_size=size)
    return [main, documentation]

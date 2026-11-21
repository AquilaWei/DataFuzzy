"""How a chart is entered in ACE Portal's time entry: which rows of its Direct, Group and Indirect
Time it fills, and with what. The ACE browser extension fills the page from these rows, so the
rules live here, where they can be tested."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from string import ascii_uppercase
from typing import Literal, NamedTuple

from .db import COMMENT_TYPES, DIRECT_THERAPY, FULL_TYPES, NO_SHOW, Record

DOCUMENTATION_MINUTES = 5  # a chart's Documentation (Indirect Time), save for INDIRECT_TYPES and UNDOCUMENTED_TYPES
MA_BILLING_MINUTES = 5  # a therapy session's MA ACCESS Billing, for a student billed to MA
# Types ACE keeps under Indirect Time only, whichever the mode; they take no Documentation.
INDIRECT_TYPES = frozenset({"Collaboration", "Home Program", "IEP Meeting/Meeting", "Progress Report", "Scheduling"})
# Of the other types, those that take no Documentation either.
UNDOCUMENTED_TYPES = frozenset({"Annual IEP Report", "Evaluation", "Re-Evaluation", "Screen", "Student Observation",
                                NO_SHOW})
# Types with no ACE counterpart: left for the user to enter by hand.
UNMAPPED_TYPES = frozenset({"Consult"})
# TheraNote's names that ACE's drop-down spells otherwise.
ACE_NAMES = {NO_SHOW: "No Show"}
# Of the types ACE asks no time for, those that still take minutes.
TIMED_WITHOUT_TIMES = frozenset({"Annual IEP Report", NO_SHOW})
# The types ACE's Group Time takes; a group student's chart of another type goes under Direct Time.
GROUP_TIME_TYPES = frozenset({"Absent Student", DIRECT_THERAPY, "Make-Up", "School Not in Session",
                              "Therapist Absent", "Unavailable Student"})
# The first line of the comments of a group student's therapy session held with no other student.
NO_GROUP_NOTE = "No appropriate student to group with."


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


class AceGroup(NamedTuple):
    """Where a chart goes in Group Time: its group ("Group A"), the group's size and whether the
    chart is a therapy session held alone (see NO_GROUP_NOTE)."""
    name: str = ""
    size: int = 0
    alone: bool = False


EMPTY_GROUP = AceGroup()  # for a chart outside Group Time, or one in it without a start time


def in_group_time(record: Record, plan_group: bool) -> bool:
    """Whether `record` goes under Group Time: a group chart, or a chart of a student whose plan
    in effect (`plan_group`) is for groups, of a type Group Time takes."""
    return record.session_type in GROUP_TIME_TYPES and (record.session_mode == "group" or plan_group)


def group_names(records: Iterable[Record], plan_group: Mapping[int, bool] | None = None) -> dict[int, AceGroup]:
    """Record id -> AceGroup for the charts among `records` that go under Group Time
    (`plan_group`: record id -> whether the student's plan on its day is for groups).

    A group is those charts of one day that start at the same time, whoever the students; a
    group student's one-to-one therapy session is a group of its own. Each day's groups are named
    Group A, Group B, … from the earliest. A group's size is how many therapy sessions it has (at
    least 1, for a group whose students were all away); its only therapy session, when it has
    one, was held alone. Charts without a start time form no group."""
    plan_group = plan_group or {}
    groups: dict[tuple, list[Record]] = {}
    for record in records:
        if not record.start_time or not in_group_time(record, plan_group.get(record.id, False)):
            continue
        own = record.session_mode != "group" and record.session_type in FULL_TYPES
        groups.setdefault((record.visit_date, record.start_time, record.id if own else 0), []).append(record)
    names: dict[int, AceGroup] = {}
    letter: dict = {}
    for (day, _start, _own), members in sorted(groups.items()):
        index = letter[day] = letter.get(day, -1) + 1
        held = sum(m.session_type in FULL_TYPES for m in members)
        for m in members:
            names[m.id] = AceGroup(f"Group {ascii_uppercase[index % 26]}", max(held, 1),
                                   m.session_type in FULL_TYPES and held == 1)
    return names


def ace_rows(record: Record, ma_billing: bool, group: AceGroup = EMPTY_GROUP,
             plan_group: bool = False) -> list[AceRow] | None:
    """The ACE rows for one chart, the Indirect ones last; None for a type ACE has no place
    for (see UNMAPPED_TYPES), to be entered by hand. `ma_billing` is the student's profile
    setting; `group` comes from group_names; `plan_group` says the student's plan on the
    chart's day is for groups. A therapy session held alone in Group Time gets NO_GROUP_NOTE
    before its follow-up and no MA ACCESS Billing."""
    kind = record.session_type
    if kind in UNMAPPED_TYPES:
        return None
    minutes = minutes_between(record.start_time, record.end_time)
    documentation = AceRow("indirect", "Documentation", DOCUMENTATION_MINUTES)
    if kind in INDIRECT_TYPES:
        comments = record.en_text if kind in COMMENT_TYPES else ""
        return [AceRow("indirect", kind, minutes, comments_on_log=comments)]
    section = "group" if in_group_time(record, plan_group) else "direct"
    name, size, alone = group if section == "group" else EMPTY_GROUP
    if kind in FULL_TYPES:
        comments = f"{NO_GROUP_NOTE}\n{record.en_followup}" if alone else record.en_followup
        main = AceRow(section, kind, minutes, ace_time(record.start_time), ace_time(record.end_time),
                      comments_on_log=comments, data_towards_goals=record.en_text,
                      deficit=record.deficit, group=name, group_size=size)
        billing = [AceRow("indirect", "MA ACCESS Billing", MA_BILLING_MINUTES)] if ma_billing and not alone else []
        return [main, documentation, *billing]
    if kind in COMMENT_TYPES:
        main = AceRow(section, kind, minutes, comments_on_log=record.en_text, group=name, group_size=size)
    else:  # Absent Student, School Not in Session, …: no time, save for the minutes of TIMED_WITHOUT_TIMES
        main = AceRow(section, ACE_NAMES.get(kind, kind), minutes if kind in TIMED_WITHOUT_TIMES else None,
                      group=name, group_size=size)
    return [main] if kind in UNDOCUMENTED_TYPES else [main, documentation]

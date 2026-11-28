"""The ACE fill-in file: a range of charts as the cells of ACE Portal's weekly time grid, each
with the rows ace_mapping says to fill, for the browser extension (chrome-extension/) to enter
one cell at a time while the user checks each before saving.

The file holds the students' names and English charts unencrypted, so it is written only where
the user picks and they are told to delete it once the week is entered."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date

from .ace_mapping import (
    DIRECT_KC,
    EMPTY_GROUP,
    KC_GOAL_SCORES,
    KC_TYPES,
    TIMED_WITHOUT_TIMES,
    AceRow,
    ace_rows,
    group_names,
    minutes_between,
)
from .db import COMMENT_TYPES, FULL_TYPES, PRESCHOOL, Record, RecordStore

# Bumped whenever the extension must read the file differently: 2 added "visits", for KeepCurrent.
FORMAT = "theranote-ace/2"

# Why a cell is left for the user to enter by hand; the extension shows these and fills nothing.
MANUAL_TYPE = "manual_type"  # a type ACE has no place for (Consult)
NO_ENGLISH = "no_english"  # ACE asks for English text the chart does not have yet
NO_TIMES = "no_times"  # ACE asks for minutes or times the chart does not have
NO_GROUP = "no_group"  # a group chart without a start time, so no group to put it in
KC_NO_START = "kc_no_start"  # a pre-school student's chart KeepCurrent asks a start time for
# What no edit of the chart can fix: the cell is left for entering by hand, and the file is
# saved all the same. Any other problem keeps the file from being saved until it is fixed.
UNFIXABLE = frozenset({MANUAL_TYPE})


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


@dataclass
class KcVisit:
    """One chart of a pre-school student as KeepCurrent's Create Service History form takes it.
    The student's page is found by first and last name on the KeepCurrent dashboard."""
    first: str
    last: str
    date: str  # "2026-11-10"
    start: str  # "HH:MM", or ""
    minutes: int  # Direct Time: the session's for a direct one, 0 otherwise
    mode: str  # "Individual" or "Group"
    application_type: str  # as KeepCurrent's drop-down begins it (see KC_TYPES)
    direct: bool  # D or DM: the session note below the routines is filled in
    comment: str = ""  # the English comments, for a direct one
    goals: list[str] = field(default_factory=list)  # the plan's goals scored met or not met
    problems: list[str] = field(default_factory=list)


def kc_visit(record: Record, first: str, last: str, plan_goals: tuple[str, ...]) -> KcVisit | None:
    """`record` for KeepCurrent, or None for a type it does not take (see KC_TYPES).
    `plan_goals` are the goals of the plan in effect on the chart's day."""
    kind = record.session_type
    if kind not in KC_TYPES:
        return None
    direct = kind in DIRECT_KC
    minutes = minutes_between(record.start_time, record.end_time) if direct else 0
    problems = []
    if direct and not record.en_text.strip():
        problems.append(NO_ENGLISH)
    if direct and minutes is None:
        problems.append(NO_TIMES)
    elif not direct and not record.start_time:
        problems.append(KC_NO_START)
    goals = [goal for goal, score in zip(plan_goals, record.goal_scores)
             if goal.strip() and score.strip().casefold() in KC_GOAL_SCORES] if direct else []
    return KcVisit(first, last, record.visit_date.isoformat(), record.start_time, minutes or 0,
                   record.session_mode.capitalize(), KC_TYPES[kind], direct,
                   record.en_text.strip() if direct else "", goals, problems)


def _kc_pairs(store: RecordStore, date_from: date, date_to: date) -> list[tuple[Record, str, KcVisit]]:
    """(record, student name, visit) for the pre-school students' charts KeepCurrent takes.
    Reads the profiles of the charts' students only."""
    records = store.records_between(date_from, date_to)
    students = {sid: store.get_student(sid) for sid in {r.student_id for r in records}}
    profiles = {sid: store.get_profile(sid) for sid in students}
    pairs = []
    for record in records:
        profile = profiles[record.student_id]
        if profile.grade != PRESCHOOL:
            continue
        student = students[record.student_id]
        visit = kc_visit(record, student.given_name, student.family_name, profile.plan_on(record.visit_date).goals)
        if visit:
            pairs.append((record, student.name, visit))
    return pairs


def kc_visits(store: RecordStore, date_from: date, date_to: date) -> list[KcVisit]:
    """The charts from `date_from` to `date_to` (inclusive) of the pre-school students, for
    KeepCurrent, by day, start time and name."""
    visits = [visit for _, _, visit in _kc_pairs(store, date_from, date_to)]
    return sorted(visits, key=lambda v: (v.date, v.start or "99:99", v.last.casefold(), v.first.casefold()))


def fill_issues(store: RecordStore, date_from: date, date_to: date) -> list[ChartIssue]:
    """The charts from `date_from` to `date_to` (inclusive) that keep the fill-in file from
    being saved: what ACE or, for a pre-school student, KeepCurrent asks of them and they lack
    (see UNFIXABLE for what does not count), by day, start time and name."""
    found: dict[int, ChartIssue] = {}
    for issue in ace_week(store, date_from, date_to)[1]:
        problems = [p for p in issue.problems if p not in UNFIXABLE]
        if problems:
            found[issue.record.id] = ChartIssue(issue.record, issue.student_name, problems)
    for record, name, visit in _kc_pairs(store, date_from, date_to):
        if not visit.problems:
            continue
        issue = found.setdefault(record.id, ChartIssue(record, name, []))
        issue.problems.extend(p for p in visit.problems if p not in issue.problems)
    return sorted(found.values(), key=lambda i: (i.record.visit_date, i.record.start_time or "99:99",
                                                 i.student_name.casefold()))


@dataclass
class ChartIssue:
    """A chart that keeps its cell from being filled in (see chart_problems), to be fixed."""
    record: Record
    student_name: str
    problems: list[str]


def ace_cells(store: RecordStore, date_from: date, date_to: date) -> list[AceCell]:
    """The cells for the charts from `date_from` to `date_to` (inclusive); see ace_week."""
    return ace_week(store, date_from, date_to)[0]


def ace_week(store: RecordStore, date_from: date, date_to: date) -> tuple[list[AceCell], list[ChartIssue]]:
    """The cells for the charts from `date_from` to `date_to` (inclusive), by day, then name,
    and the charts with problems, by day and start time.

    Reads the charts in the range and, for their students only, the name and from the profile
    the MA billing setting and whether the plan on each chart's day is for groups. Groups are
    counted over every student's charts in the range."""
    records = store.records_between(date_from, date_to)
    students = {sid: store.get_student(sid) for sid in {r.student_id for r in records}}
    profiles = {sid: store.get_profile(sid) for sid in students}
    ma_billing = {sid: profile.ma_billing for sid, profile in profiles.items()}
    plan_group = {r.id: profiles[r.student_id].plan_on(r.visit_date).group for r in records}
    groups = group_names(records, plan_group)
    cells: dict[tuple[date, int], AceCell] = {}
    issues: list[ChartIssue] = []
    for record in records:
        student = students[record.student_id]
        cell = cells.setdefault((record.visit_date, student.id), AceCell(
            student.given_name, student.family_name, record.visit_date.isoformat()))
        rows = ace_rows(record, ma_billing[student.id], groups.get(record.id, EMPTY_GROUP), plan_group[record.id])
        cell.rows.extend(rows or [])
        problems = chart_problems(record, rows)
        cell.problems.extend(p for p in problems if p not in cell.problems)
        if problems:
            issues.append(ChartIssue(record, student.name, problems))
    issues.sort(key=lambda i: (i.record.visit_date, i.record.start_time or "99:99", i.student_name.casefold()))
    return sorted(cells.values(), key=lambda c: (c.date, c.last.casefold(), c.first.casefold())), issues


def to_json(cells: list[AceCell], date_from: date, date_to: date, visits: list[KcVisit] = ()) -> str:
    """The file's text; `date_from`..`date_to` is the week the extension checks ACE's grid
    shows. `visits` are the pre-school charts for KeepCurrent (see kc_visits)."""
    return json.dumps({"format": FORMAT, "week": [date_from.isoformat(), date_to.isoformat()],
                       "cells": [asdict(cell) for cell in cells],
                       "visits": [asdict(visit) for visit in visits]}, ensure_ascii=False, indent=1)

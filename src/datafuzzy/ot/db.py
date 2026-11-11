"""The chart database: students, their visit records and the export batches.

Names, student profiles, locations, both chart texts and their follow-ups, the activities and the export
mappings are encrypted column by column;
only dates and ids stay readable so records can be found by date without the key.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Self

from platformdirs import user_data_dir

from . import APP_NAME
from .crypto import Cipher

# Overrides the database location (tests, or a chart book kept elsewhere).
DB_ENV = f"{APP_NAME.upper()}_DB"
KEY_CHECK_TEXT = "key-check"

# A student may have several records a day (a morning and an afternoon session).
RECORD_TABLE = """
CREATE TABLE IF NOT EXISTS {name} (
    id         INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES student(id) ON DELETE CASCADE,
    visit_date TEXT NOT NULL,
    location   BLOB NOT NULL,
    zh_text    BLOB NOT NULL,
    en_text    BLOB NOT NULL,
    updated_at TEXT NOT NULL,
    activity   BLOB,  -- NULL in records made before the column existed
    start_time TEXT,  -- "HH:MM", or NULL when not filled in
    end_time   TEXT,  -- "HH:MM", or NULL when not filled in
    session_type TEXT,  -- one of types_for(session_mode); NULL in records made before it, read as the default
    goal_scores  BLOB,  -- JSON list, one score per profile goal; NULL when none filled in
    session_mode TEXT,  -- one of SESSION_MODES; NULL in records made before it, read as individual
    zh_followup  BLOB,  -- the follow-up part of the comments; NULL in records made before it
    en_followup  BLOB,  -- likewise in English
    deficit      TEXT   -- one of DEFICITS; NULL in records made before it, read as the default
);
"""
RECORD_COLUMNS = ("id, student_id, visit_date, location, zh_text, en_text, updated_at,"
                  " activity, start_time, end_time, session_type, goal_scores,"
                  " session_mode, zh_followup, en_followup, deficit")
STUDENT_COLUMNS = "id, name, active, family_name"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS student (
    id      INTEGER PRIMARY KEY,
    name    BLOB NOT NULL,  -- the given name
    family_name BLOB,  -- optional; NULL for none
    profile BLOB,  -- StudentProfile as JSON; NULL until first filled in
    active  INTEGER NOT NULL DEFAULT 1  -- 0 once their plan is done; they leave the timetable
);
CREATE TABLE IF NOT EXISTS export_batch (
    id         INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    payload    BLOB NOT NULL
);
""" + RECORD_TABLE.format(name="record") + """
CREATE INDEX IF NOT EXISTS record_by_date ON record(visit_date);
"""


def default_db_path() -> Path:
    """`$THERANOTE_DB` if set, else the per-user data folder."""
    override = os.environ.get(DB_ENV)
    if override:
        return Path(override)
    return Path(user_data_dir(APP_NAME)) / f"{APP_NAME.lower()}.db"


def connect(path: Path, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open (creating if needed) the database file, readable by this user only."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=check_same_thread)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    student_columns = {row[1] for row in db.execute("PRAGMA table_info(student)")}
    if "profile" not in student_columns:
        db.execute("ALTER TABLE student ADD COLUMN profile BLOB")  # from before profiles
    if "active" not in student_columns:  # from before students could be made inactive
        db.execute("ALTER TABLE student ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "family_name" not in student_columns:  # from before family names were kept apart
        db.execute("ALTER TABLE student ADD COLUMN family_name BLOB")
    columns = {row[1] for row in db.execute("PRAGMA table_info(record)")}
    if "activity" not in columns:  # a chart book from before activities
        db.execute("ALTER TABLE record ADD COLUMN activity BLOB")
    if "start_time" not in columns:  # a chart book from before session times
        db.execute("ALTER TABLE record ADD COLUMN start_time TEXT")
    if "end_time" not in columns:  # a chart book from before end times
        db.execute("ALTER TABLE record ADD COLUMN end_time TEXT")
    if "session_type" not in columns:  # a chart book from before session types
        db.execute("ALTER TABLE record ADD COLUMN session_type TEXT")
    if "goal_scores" not in columns:  # a chart book from before goal scores
        db.execute("ALTER TABLE record ADD COLUMN goal_scores BLOB")
    for column, kind in (("session_mode", "TEXT"), ("zh_followup", "BLOB"), ("en_followup", "BLOB"),
                         ("deficit", "TEXT")):
        if column not in columns:  # a chart book from before ACE modes, service types and follow-ups
            db.execute(f"ALTER TABLE record ADD COLUMN {column} {kind}")
    if db.execute("PRAGMA user_version").fetchone()[0] < 1:
        fill_end_times(db)
        db.execute("PRAGMA user_version = 1")
    if db.execute("PRAGMA user_version").fetchone()[0] < 2:
        allow_several_records_a_day(db)
        db.execute("PRAGMA user_version = 2")
    if db.execute("PRAGMA user_version").fetchone()[0] < 3:
        convert_session_types(db)
        db.execute("PRAGMA user_version = 3")
    db.commit()
    path.chmod(0o600)
    return db


def allow_several_records_a_day(db: sqlite3.Connection) -> None:
    """Rebuild a record table from when a student could have only one record a day, without
    that rule. SQLite cannot drop a constraint, so the rows are copied to a new table as they
    are: no key is needed and nothing is decrypted. Runs once per database (see connect)."""
    (sql,) = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'record'").fetchone()
    if "UNIQUE" not in sql:
        return
    db.commit()
    db.execute("BEGIN")
    db.execute("DROP TABLE IF EXISTS record_new")
    db.execute(RECORD_TABLE.format(name="record_new"))
    db.execute(f"INSERT INTO record_new({RECORD_COLUMNS}) SELECT {RECORD_COLUMNS} FROM record")
    db.execute("DROP TABLE record")  # its indexes go with it
    db.execute("ALTER TABLE record_new RENAME TO record")
    db.execute("CREATE INDEX record_by_date ON record(visit_date)")
    db.commit()


# The session types from before ACE service types, as (mode, service type).
OLD_SESSION_TYPES = {
    "individual": ("individual", "Direct Therapy Time"),
    "group": ("group", "Direct Therapy Time"),
    "consult": ("individual", "Consult"),
    "collaboration": ("individual", "Collaboration"),
    "make up": ("individual", "Make-Up"),
}


def convert_session_types(db: sqlite3.Connection) -> None:
    """Turn the five session types from before ACE service types into a mode and a service
    type (see OLD_SESSION_TYPES); a record with none becomes individual Direct Therapy Time.
    Runs once per database (see connect). Only the plaintext types are touched: no key is
    needed and no chart is decrypted."""
    rows = db.execute("SELECT id, session_type FROM record").fetchall()
    db.executemany("UPDATE record SET session_mode = ?, session_type = ? WHERE id = ?",
                   [(*OLD_SESSION_TYPES.get(old or "individual", ("individual", "Direct Therapy Time")), record_id)
                    for record_id, old in rows])


def fill_end_times(db: sqlite3.Connection) -> None:
    """Give charts from before end times one SESSION_MINUTES after their start. Runs once per
    database (see connect), so an end time later cleared by hand stays cleared. Only the
    plaintext times are touched: no key is needed and no chart is decrypted."""
    rows = db.execute("SELECT id, start_time FROM record"
                      " WHERE start_time IS NOT NULL AND start_time != '' AND end_time IS NULL").fetchall()
    db.executemany("UPDATE record SET end_time = ? WHERE id = ?",
                   [(default_end_time(start), record_id) for record_id, start in rows])


def read_meta(path: Path, name: str) -> bytes | None:
    """A plaintext setting that must be readable before the key is known (e.g. the password
    salt). None if the database or the setting does not exist yet."""
    if not path.exists():
        return None
    db = connect(path)
    try:
        row = db.execute("SELECT value FROM meta WHERE key = ?", (name,)).fetchone()
    finally:
        db.close()
    return row[0] if row else None


def write_meta(path: Path, name: str, value: bytes) -> None:
    db = connect(path)
    try:
        with db:
            db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (name, value))
    finally:
        db.close()


CJK_CHAR_RE = re.compile(r"[㐀-鿿]")


@dataclass(frozen=True)
class Student:
    """`given_name` is what charts call the student and the only part a translation export
    codes; `family_name` is optional and only tells two students of one given name apart."""
    id: int
    given_name: str
    active: bool = True  # False once their plan is done
    family_name: str = ""

    @property
    def name(self) -> str:
        """The full name to show: "Emma Wang", or "王小明" (family name first, no space) when
        both parts are Chinese; just the given name without a family name."""
        if not self.family_name:
            return self.given_name
        if CJK_CHAR_RE.match(self.family_name[-1]) and CJK_CHAR_RE.match(self.given_name[0]):
            return self.family_name + self.given_name
        return f"{self.given_name} {self.family_name}"


@dataclass(frozen=True)
class Session:
    """A weekly session time of a student, e.g. Fridays 10:00–10:30, fetching them from 301."""
    weekday: int  # Monday 0 … Sunday 6
    start: str  # "HH:MM"
    end: str  # "HH:MM"
    classroom: str = ""  # the 領取教室: where to find the child for the session; "" if not set


_PLAN_DATE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\s*$")


def parse_plan_date(text: str) -> date | None:
    """"10/29/2026" or "10/29/26" (month first, as the form writes it) as a date; None for
    blank text or text that does not read so."""
    m = _PLAN_DATE.match(text)
    if not m:
        return None
    month, day, year = (int(g) for g in m.groups())
    try:
        return date(year + 2000 if year < 100 else year, month, day)
    except ValueError:
        return None


@dataclass(frozen=True)
class Plan:
    """An IEP or 504 plan: its date and the goals set with it. A new plan replaces the goals
    from its date on; charts before it keep the goals they were scored on."""
    plan_504: bool = False  # a 504 plan; an IEP otherwise
    plan_date: str = ""  # as typed, "MM/DD/YYYY"
    goals: tuple[str, ...] = ()  # Goal 1, Goal 2, …: as many as the student has
    frequency: int = 0  # therapy minutes a month, a multiple of FREQUENCY_STEP; 0 if not set

    @property
    def frequency_text(self) -> str:
        """"30 mins/month", as the form writes it; "" when not set."""
        return f"{self.frequency} mins/month" if self.frequency else ""

    @property
    def label(self) -> str:
        """"IEP Date" or "504 Date", as the form names the plan's date."""
        return "504 Date" if self.plan_504 else "IEP Date"

    @property
    def kind(self) -> str:
        return "504" if self.plan_504 else "IEP"

    @property
    def starts(self) -> date:
        """The plan's date; date.min when blank or unreadable, so such a plan counts as the earliest."""
        return parse_plan_date(self.plan_date) or date.min


FREQUENCY_STEP = 30  # a plan's minutes a month come in steps of this
FREQUENCY_MAX = 600


def sort_plans(plans: Iterable[Plan]) -> list[Plan]:
    return sorted(plans, key=lambda p: p.starts)


@dataclass(frozen=True)
class StudentProfile:
    """What the school form's header asks about a student, besides the name, and where they
    are seen (one place per student; new records take it). Free text except where noted;
    `school_year` reads like "09/2026-06/2027"."""
    diagnosis: str = ""
    age: str = ""
    grade: str = ""
    classroom: str = ""
    case_manager: str = ""
    ma_billing: bool = False  # the student's sessions are billed to Medical Assistance
    school_year: str = ""
    goals: tuple[str, ...] = ()  # Goal 1, Goal 2, …: as many as the student has
    location: str = ""
    sessions: tuple[Session, ...] = ()  # as many as the student has, by weekday then start
    # The latest plan is plan_504, plan_date, frequency and goals; the plans it replaced, oldest first,
    # are kept with their goals for the charts scored on them.
    plan_504: bool = False  # the plan is a 504 plan; an IEP otherwise
    plan_date: str = ""  # the date of that IEP or 504 plan
    frequency: int = 0  # its therapy minutes a month (see Plan)
    past_plans: tuple[Plan, ...] = ()

    @property
    def plan_label(self) -> str:
        """"IEP Date" or "504 Date", as the form names the plan's date."""
        return self.plan.label

    @property
    def plan(self) -> Plan:
        """The latest plan."""
        return Plan(self.plan_504, self.plan_date, self.goals, self.frequency)

    @property
    def plans(self) -> tuple[Plan, ...]:
        """Every plan, oldest first, the latest last."""
        return (*self.past_plans, self.plan)

    def plan_on(self, day: date) -> Plan:
        """The plan in effect on `day`: the last one dated on or before it, or the earliest
        when `day` comes before all of them."""
        plans = self.plans
        return next((p for p in reversed(plans) if p.starts <= day), plans[0])

    def with_plans(self, plans: Iterable[Plan]) -> StudentProfile:
        """This profile with `plans` (in any order; at least one), sorted by date, the latest
        becoming the current plan."""
        *past, latest = sort_plans(plans)
        return replace(self, plan_504=latest.plan_504, plan_date=latest.plan_date, frequency=latest.frequency,
                       goals=latest.goals, past_plans=tuple(past))


# "1. … 2. …" (also "1、", "1)" or "Goal 1:"); not a number inside another ("10.", "1.5").
_GOAL_NUMBER = re.compile(r"(?<![A-Za-z])goal\s*(\d{1,2})\s*[.:：、．)]?\s*|(?<![\d.])(\d{1,2})\s*[.、．)](?!\d)\s*",
                          re.IGNORECASE)
_GOALS_HEADING = re.compile(r"^\s*goals?\s*[:：]", re.IGNORECASE)


def split_goals(text: str) -> tuple[str, ...]:
    """The goals of a profile from before goals were kept one by one, when they were one text:
    split where it numbers them 1, 2, 3, … in turn (a number out of turn, like the 3 in
    "1. a 3. b", stays part of the goal), without the numbers, so goal n stays Goal n. Words
    before "1." (but a "Goals:" heading) go with goal 1, so nothing is lost. Text without
    numbers is one goal; blank text is none."""
    cuts = []  # (where the number starts, where its goal starts)
    for match in _GOAL_NUMBER.finditer(text):
        if int(match.group(1) or match.group(2)) == len(cuts) + 1:
            cuts.append((match.start(), match.end()))
    if not cuts:
        goals = [text]
    else:
        ends = [start for start, _ in cuts[1:]] + [len(text)]
        goals = [text[begin:end] for (_, begin), end in zip(cuts, ends)]
        intro = _GOALS_HEADING.sub("", text[:cuts[0][0]]).strip()
        if intro:
            goals[0] = f"{intro} {goals[0].strip()}"
    return tuple(g.strip() for g in goals if g.strip())


SESSION_MINUTES = 30  # a new session's default length
# A chart is an individual session (ACE's Direct Time) or a group one (its Group Time), and of
# one service type, named as ACE names it. Some types are for individual sessions only.
SESSION_MODES = ("individual", "group")
DEFAULT_SESSION_MODE = "individual"
DIRECT_THERAPY = "Direct Therapy Time"
COMMON_TYPES = ("Absent Student", DIRECT_THERAPY, "Make-Up", "School Not in Session", "Therapist Absent",
                "Unavailable Student", "Consult", "Collaboration", "Home Program", "IEP Meeting/Meeting",
                "Progress Report", "Scheduling")
INDIVIDUAL_ONLY_TYPES = ("Annual IEP Report", "Evaluation", "Re-Evaluation", "Screen", "Student Observation")
DEFAULT_SESSION_TYPE = DIRECT_THERAPY
# What the chart asks for below the times: everything (goal scores, activities, comments and a
# follow-up, the deficit) for a therapy session; only the comments for these; nothing otherwise.
FULL_TYPES = frozenset({DIRECT_THERAPY, "Make-Up"})
COMMENT_TYPES = frozenset({"Evaluation", "Re-Evaluation", "Screen", "Student Observation",
                           "Unavailable Student", "Collaboration"})
# The underlying deficits a therapy session can address, as ACE names them.
DEFICITS = ("Visual Motor Coordination", "Sensory Processing")
DEFAULT_DEFICIT = DEFICITS[0]


def types_for(mode: str) -> tuple[str, ...]:
    """The service types a chart of `mode` can have. Raises ValueError for an unknown mode."""
    if mode not in SESSION_MODES:
        raise ValueError(f"unknown session mode {mode!r}")
    return COMMON_TYPES + INDIVIDUAL_ONLY_TYPES if mode == "individual" else COMMON_TYPES


def session_label(mode: str, session_type: str) -> str:
    """"Individual - Direct Therapy Time": the mode and the service type, for a list or a sheet."""
    return f"{mode.capitalize()} - {session_type}"


def default_end_time(start_time: str) -> str:
    """SESSION_MINUTES after "HH:MM" ("" for ""), kept within the same day."""
    if not start_time:
        return ""
    hour, minute = (int(part) for part in start_time.split(":"))
    end = min(hour * 60 + minute + SESSION_MINUTES, 23 * 60 + 59)
    return f"{end // 60:02d}:{end % 60:02d}"


@dataclass(frozen=True)
class Record:
    id: int
    student_id: int
    visit_date: date
    location: str
    zh_text: str
    en_text: str
    updated_at: datetime
    activity: str = ""  # the day's therapy activities; never in a translation export
    start_time: str = ""  # when the session began, "HH:MM", or "" if not filled in; never in a translation export
    end_time: str = ""  # when it ended, likewise
    session_type: str = DEFAULT_SESSION_TYPE  # one of types_for(session_mode)
    goal_scores: tuple[str, ...] = ()  # how the student did on Goal 1, 2, …: "75%", "not met", "" for none
    session_mode: str = DEFAULT_SESSION_MODE  # one of SESSION_MODES
    zh_followup: str = ""  # the follow-up part of the comments (zh_text being the rest)
    en_followup: str = ""  # likewise in English
    deficit: str = DEFAULT_DEFICIT  # the underlying deficit the session addressed, one of DEFICITS


# The texts of a chart that set_chart_texts writes: the comments and the follow-up, both languages.
CHART_TEXT_FIELDS = ("zh_text", "zh_followup", "en_text", "en_followup")


def _check_session(mode: str, session_type: str, deficit: str) -> None:
    if session_type not in types_for(mode):
        raise ValueError(f"service type {session_type!r} is not for a {mode} session")
    if deficit not in DEFICITS:
        raise ValueError(f"unknown deficit {deficit!r}")


@dataclass(frozen=True)
class StoredBatch:
    id: int
    created_at: datetime
    data: dict


class NotFound(LookupError):
    """No student, record or batch with that id."""


class RecordStore:
    """Encrypted chart book. Safe to use from worker threads (calls are serialised).

    Opening checks the key against a stored marker and raises `DecryptionError` for a wrong
    one, so a bad key never silently produces garbage or a second, unreadable data set.
    """

    def __init__(self, path: Path, key: bytes, now: Callable[[], datetime] = datetime.now) -> None:
        self.path = Path(path)
        self._cipher = Cipher(key)
        self._now = now
        self._lock = threading.RLock()
        self._db = connect(self.path, check_same_thread=False)
        try:
            self._check_key()
        except Exception:
            self._db.close()
            raise

    def _check_key(self) -> None:
        context = "meta.key_check"
        row = self._db.execute("SELECT value FROM meta WHERE key = 'key_check'").fetchone()
        if row is None:
            with self._db:
                self._db.execute("INSERT INTO meta(key, value) VALUES ('key_check', ?)",
                                 (self._cipher.encrypt(KEY_CHECK_TEXT, context),))
        else:
            self._cipher.decrypt(row[0], context)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _enc(self, text: str, column: str) -> bytes:
        return self._cipher.encrypt(text, column)

    def _dec(self, blob: bytes, column: str) -> str:
        return self._cipher.decrypt(blob, column)

    # --- students -------------------------------------------------------------------

    def _name_blobs(self, given_name: str, family_name: str) -> tuple[bytes, bytes | None]:
        """Both names encrypted, trimmed; the family name None when blank. Raises ValueError
        for a blank given name."""
        given_name, family_name = given_name.strip(), family_name.strip()
        if not given_name:
            raise ValueError("student name is empty")
        family = self._enc(family_name, "student.family_name") if family_name else None
        return self._enc(given_name, "student.name"), family

    def add_student(self, given_name: str, family_name: str = "") -> Student:
        """Two students may share a name (it is encrypted, so it cannot be UNIQUE)."""
        blobs = self._name_blobs(given_name, family_name)
        with self._lock, self._db:
            cur = self._db.execute("INSERT INTO student(name, family_name) VALUES (?, ?)", blobs)
        return Student(cur.lastrowid, given_name.strip(), family_name=family_name.strip())

    def get_student(self, student_id: int) -> Student:
        with self._lock:
            row = self._db.execute(f"SELECT {STUDENT_COLUMNS} FROM student WHERE id = ?",
                                   (student_id,)).fetchone()
        if row is None:
            raise NotFound(f"student {student_id}")
        return self._student(row)

    def rename_student(self, student_id: int, given_name: str, family_name: str = "") -> Student:
        """Set both names; a blank `family_name` removes it."""
        blobs = self._name_blobs(given_name, family_name)
        with self._lock, self._db:
            cur = self._db.execute("UPDATE student SET name = ?, family_name = ? WHERE id = ?",
                                   (*blobs, student_id))
        if cur.rowcount == 0:
            raise NotFound(f"student {student_id}")
        return self.get_student(student_id)

    def set_active(self, student_id: int, active: bool) -> None:
        """Make a student active (on the timetable) or inactive (their plan is done). Their
        records stay either way. Raises NotFound for an unknown student."""
        with self._lock, self._db:
            cur = self._db.execute("UPDATE student SET active = ? WHERE id = ?", (int(active), student_id))
        if cur.rowcount == 0:
            raise NotFound(f"student {student_id}")

    def delete_student(self, student_id: int) -> None:
        """Remove a student and, through ON DELETE CASCADE, all of their records, for good.
        Raises NotFound for an unknown student."""
        with self._lock, self._db:
            cur = self._db.execute("DELETE FROM student WHERE id = ?", (student_id,))
        if cur.rowcount == 0:
            raise NotFound(f"student {student_id}")

    def get_profile(self, student_id: int) -> StudentProfile:
        """The student's profile; an empty one if never filled in. Raises NotFound for an
        unknown student."""
        with self._lock:
            row = self._db.execute("SELECT profile FROM student WHERE id = ?",
                                   (student_id,)).fetchone()
        if row is None:
            raise NotFound(f"student {student_id}")
        if row[0] is None:
            return StudentProfile()
        fields = json.loads(self._dec(row[0], "student.profile"))
        sessions = tuple(Session(**s) for s in fields.pop("sessions", []))  # none before session times
        goals = fields.pop("goals", [])
        # One text before goals were kept one by one; saving the profile again stores the list.
        goals = split_goals(goals) if isinstance(goals, str) else tuple(goals)
        past = tuple(Plan(p["plan_504"], p["plan_date"], tuple(p["goals"]), p.get("frequency", 0))
                     for p in fields.pop("past_plans", []))  # none before plans were kept; no frequency before it was asked
        return StudentProfile(**fields, goals=goals, sessions=sessions, past_plans=past)

    def set_profile(self, student_id: int, profile: StudentProfile) -> None:
        """Replace the student's profile, with surrounding spaces trimmed from each field, blank
        goals left out, the sessions sorted by weekday and start and the plans by date (the
        latest becoming the current one)."""
        plans = [Plan(p.plan_504, p.plan_date.strip(), tuple(g.strip() for g in p.goals if g.strip()), p.frequency)
                 for p in profile.plans]
        profile = profile.with_plans(plans)
        trimmed = {k: v.strip() if isinstance(v, str) else v for k, v in asdict(profile).items()}
        trimmed["goals"] = list(profile.goals)
        trimmed["past_plans"] = [asdict(p) for p in profile.past_plans]
        trimmed["sessions"] = [asdict(replace(s, classroom=s.classroom.strip()))
                               for s in sorted(profile.sessions, key=lambda s: (s.weekday, s.start))]
        blob = self._enc(json.dumps(trimmed, ensure_ascii=False), "student.profile")
        with self._lock, self._db:
            cur = self._db.execute("UPDATE student SET profile = ? WHERE id = ?", (blob, student_id))
        if cur.rowcount == 0:
            raise NotFound(f"student {student_id}")

    def students(self) -> list[Student]:
        """Everyone, sorted by name."""
        with self._lock:
            rows = self._db.execute(f"SELECT {STUDENT_COLUMNS} FROM student").fetchall()
        return sorted((self._student(r) for r in rows), key=lambda s: (s.name.casefold(), s.id))

    def _student(self, row: tuple) -> Student:
        family = self._dec(row[3], "student.family_name") if row[3] is not None else ""
        return Student(row[0], self._dec(row[1], "student.name"), bool(row[2]), family)

    # --- records --------------------------------------------------------------------

    def add_record(self, student_id: int, visit_date: date, location: str = "",
                   zh_text: str = "", en_text: str = "", activity: str = "",
                   start_time: str = "", end_time: str = "",
                   session_type: str = DEFAULT_SESSION_TYPE, goal_scores: tuple[str, ...] = (),
                   session_mode: str = DEFAULT_SESSION_MODE, zh_followup: str = "",
                   en_followup: str = "", deficit: str = DEFAULT_DEFICIT) -> Record:
        """Raises NotFound for an unknown student, ValueError for a service type that is not
        for `session_mode` (see types_for) or a deficit not in DEFICITS. The student may
        already have records that day."""
        _check_session(session_mode, session_type, deficit)
        self.get_student(student_id)
        with self._lock:
            updated_at = self._now()
            with self._db:
                # The row first, for its id; the texts are written (encrypted) in the same transaction.
                cur = self._db.execute(
                    "INSERT INTO record(student_id, visit_date, location, zh_text, en_text, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (student_id, visit_date.isoformat(), b"", b"", b"", updated_at.isoformat()))
                record = Record(cur.lastrowid, student_id, visit_date, location, zh_text, en_text, updated_at,
                                activity, start_time, end_time, session_type, tuple(goal_scores),
                                session_mode, zh_followup, en_followup, deficit)
                self._write_texts(record)
        return record

    def update_record(self, record_id: int, *, location: str | None = None,
                      zh_text: str | None = None, en_text: str | None = None,
                      activity: str | None = None, start_time: str | None = None,
                      end_time: str | None = None, session_type: str | None = None,
                      goal_scores: tuple[str, ...] | None = None, session_mode: str | None = None,
                      zh_followup: str | None = None, en_followup: str | None = None,
                      deficit: str | None = None) -> Record:
        """Change only the fields given (None leaves one alone), for autosave. The English
        text is overwritten, not versioned. Raises NotFound for an unknown record, ValueError
        if the mode and service type it ends up with do not go together (see types_for) or
        for a deficit not in DEFICITS."""
        given = {"location": location, "zh_text": zh_text, "en_text": en_text, "activity": activity,
                 "start_time": start_time, "end_time": end_time, "session_type": session_type,
                 "goal_scores": None if goal_scores is None else tuple(goal_scores),
                 "session_mode": session_mode, "zh_followup": zh_followup, "en_followup": en_followup,
                 "deficit": deficit}
        with self._lock:
            record = self.get_record(record_id)
            new = replace(record, updated_at=self._now(),
                          **{field: value for field, value in given.items() if value is not None})
            _check_session(new.session_mode, new.session_type, new.deficit)
            with self._db:
                self._write_texts(new)
        return new

    def move_record(self, record_id: int, visit_date: date) -> Record:
        """Correct the day of a record. Raises NotFound for an unknown record."""
        with self._lock:
            record = self.get_record(record_id)
            new = replace(record, visit_date=visit_date, updated_at=self._now())
            with self._db:
                self._db.execute("UPDATE record SET visit_date = ?, updated_at = ? WHERE id = ?",
                                 (visit_date.isoformat(), new.updated_at.isoformat(), record_id))
        return new

    def set_chart_texts(self, texts: dict[int, dict[str, str]]) -> None:
        """Replace chart texts of several records in one transaction: either all are written
        or, if one id is unknown (NotFound), none. Each record's dict holds the fields to
        change, out of CHART_TEXT_FIELDS (ValueError for any other)."""
        with self._lock, self._db:
            for record_id, fields in texts.items():
                unknown = set(fields) - set(CHART_TEXT_FIELDS)
                if unknown:
                    raise ValueError(f"not chart texts: {sorted(unknown)}")
                record = self.get_record(record_id)
                self._write_texts(replace(record, **fields, updated_at=self._now()))

    def _write_texts(self, r: Record) -> None:
        followups = [None if not text else self._enc(text, f"record.{column}")
                     for column, text in (("zh_followup", r.zh_followup), ("en_followup", r.en_followup))]
        self._db.execute(
            "UPDATE record SET location = ?, zh_text = ?, en_text = ?, updated_at = ?,"
            " activity = ?, start_time = ?, end_time = ?, session_type = ?, goal_scores = ?,"
            " session_mode = ?, zh_followup = ?, en_followup = ?, deficit = ?"
            " WHERE id = ?",
            (self._enc(r.location, "record.location"), self._enc(r.zh_text, "record.zh_text"),
             self._enc(r.en_text, "record.en_text"), r.updated_at.isoformat(),
             self._enc(r.activity, "record.activity"), r.start_time or None,
             r.end_time or None, r.session_type, self._enc_scores(r.goal_scores),
             r.session_mode, *followups, r.deficit, r.id))

    def _enc_scores(self, scores: tuple[str, ...]) -> bytes | None:
        """Scores are about the student's progress, so they are encrypted like the charts."""
        if not any(s.strip() for s in scores):
            return None
        return self._enc(json.dumps([s.strip() for s in scores], ensure_ascii=False), "record.goal_scores")

    def delete_record(self, record_id: int) -> None:
        """Remove a record for good. Raises NotFound for an unknown record."""
        with self._lock, self._db:
            cur = self._db.execute("DELETE FROM record WHERE id = ?", (record_id,))
        if cur.rowcount == 0:
            raise NotFound(f"record {record_id}")

    def get_record(self, record_id: int) -> Record:
        with self._lock:
            row = self._db.execute(f"SELECT {RECORD_COLUMNS} FROM record WHERE id = ?",
                                   (record_id,)).fetchone()
        if row is None:
            raise NotFound(f"record {record_id}")
        return self._record(row)

    def student_records_on(self, student_id: int, day: date) -> list[Record]:
        """The student's records of one day, by start time (those without one first)."""
        return self._records("student_id = ? AND visit_date = ?", (student_id, day.isoformat()),
                             "start_time, id")

    def book_next_visit(self, record_id: int, days: int = 7) -> Record:
        """A record for the next session, `days` after this one: the same student, start and end
        time, mode and service type, at the student's location now. If the student already has a
        record then that starts at the same time, it is returned instead, so booking twice makes
        one. Raises NotFound for an unknown record."""
        with self._lock:
            record = self.get_record(record_id)
            day = record.visit_date + timedelta(days=days)
            for booked in self.student_records_on(record.student_id, day):
                if booked.start_time == record.start_time:
                    return booked
            return self.add_record(record.student_id, day, self.student_location(record.student_id),
                                   start_time=record.start_time, end_time=record.end_time,
                                   session_type=record.session_type, session_mode=record.session_mode)

    def _record(self, row: tuple) -> Record:
        return Record(row[0], row[1], date.fromisoformat(row[2]),
                      self._dec(row[3], "record.location"), self._dec(row[4], "record.zh_text"),
                      self._dec(row[5], "record.en_text"), datetime.fromisoformat(row[6]),
                      "" if row[7] is None else self._dec(row[7], "record.activity"), row[8] or "",
                      row[9] or "", row[10] or DEFAULT_SESSION_TYPE,
                      () if row[11] is None else tuple(json.loads(self._dec(row[11], "record.goal_scores"))),
                      row[12] or DEFAULT_SESSION_MODE,
                      "" if row[13] is None else self._dec(row[13], "record.zh_followup"),
                      "" if row[14] is None else self._dec(row[14], "record.en_followup"),
                      row[15] or DEFAULT_DEFICIT)

    def _records(self, where: str, args: tuple, order: str) -> list[Record]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {RECORD_COLUMNS} FROM record WHERE {where} ORDER BY {order}",
                args).fetchall()
        return [self._record(r) for r in rows]

    # --- queries --------------------------------------------------------------------

    def records_for_student(self, student_id: int, newest_first: bool = True) -> list[Record]:
        direction = "DESC" if newest_first else "ASC"
        return self._records("student_id = ?", (student_id,), f"visit_date {direction}, start_time {direction}, id {direction}")

    def records_on(self, day: date) -> list[Record]:
        """The records of one day, in the order they were created."""
        return self._records("visit_date = ?", (day.isoformat(),), "id")

    def students_on(self, day: date) -> list[Student]:
        """Students with a record on `day`, sorted by name."""
        ids = {r.student_id for r in self.records_on(day)}
        return [s for s in self.students() if s.id in ids]

    def records_between(self, date_from: date, date_to: date) -> list[Record]:
        """Records with date_from <= visit_date <= date_to, oldest first."""
        return self._records("visit_date BETWEEN ? AND ?",
                             (date_from.isoformat(), date_to.isoformat()), "visit_date, id")

    def dates_with_records(self, date_from: date | None = None,
                           date_to: date | None = None) -> set[date]:
        """Days that have at least one record, optionally within a range (e.g. the month
        the calendar is showing)."""
        low = (date_from or date.min).isoformat()
        high = (date_to or date.max).isoformat()
        with self._lock:
            rows = self._db.execute(
                "SELECT DISTINCT visit_date FROM record WHERE visit_date BETWEEN ? AND ?",
                (low, high)).fetchall()
        return {date.fromisoformat(r[0]) for r in rows}

    # --- locations ------------------------------------------------------------------

    def student_default_location(self, student_id: int) -> str:
        """The location of the student's latest visit that has one, "" for a new student.
        "Latest" is by visit date, not by when the record was typed in."""
        for record in self.records_for_student(student_id, newest_first=True):
            if record.location:
                return record.location
        return ""

    def student_location(self, student_id: int) -> str:
        """Where the student is seen now: the profile's location, or for a student whose
        profile has none yet (one from before profiles had it), their latest visit's."""
        return self.get_profile(student_id).location or self.student_default_location(student_id)

    def student_default_start_time(self, student_id: int) -> str:
        """The start time of the student's latest visit that has one, "" if none does."""
        for record in self.records_for_student(student_id, newest_first=True):
            if record.start_time:
                return record.start_time
        return ""

    def session_classrooms(self) -> list[str]:
        """Every 領取教室 given in a session time, sorted, for the profile's drop-downs."""
        return sorted({session.classroom for student in self.students()
                       for session in self.get_profile(student.id).sessions if session.classroom})

    def timetable(self) -> list[tuple[Session, Student]]:
        """Every weekly session time of the active students, by weekday, start and name."""
        slots = [(session, student) for student in self.students() if student.active
                 for session in self.get_profile(student.id).sessions]
        return sorted(slots, key=lambda slot: (slot[0].weekday, slot[0].start, slot[1].name.casefold()))

    def student_default_slot(self, student_id: int, day: date) -> tuple[str, str]:
        """(start, end) for a new visit on `day`: the student's session time on that weekday from
        the profile (the earliest, if there are several); failing that, the times of the latest
        visit on the same weekday that has a start time (its end, or SESSION_MINUTES later if it
        has none); failing that, the latest visit's start time and SESSION_MINUTES later; ("", "")
        for none. Sessions tend to repeat weekly, so the same weekday is the better guess."""
        for session in self.get_profile(student_id).sessions:  # kept sorted by set_profile
            if session.weekday == day.weekday():
                return session.start, session.end or default_end_time(session.start)
        for record in self.records_for_student(student_id, newest_first=True):
            if record.start_time and record.visit_date.weekday() == day.weekday():
                return record.start_time, record.end_time or default_end_time(record.start_time)
        start = self.student_default_start_time(student_id)
        return start, default_end_time(start)

    def records_at(self, location: str) -> list[Record]:
        """Records at `location` ("" for those with none), newest first. Locations are
        encrypted, so this reads every record."""
        records = self._records("1 = 1", (), "visit_date DESC, start_time DESC, id DESC")
        return [r for r in records if r.location.strip() == location]

    def all_locations(self) -> list[str]:
        """Every location used so far, most recently visited first, then those only set in a
        profile (by name), for a drop-down."""
        with self._lock:
            rows = self._db.execute(
                "SELECT location FROM record ORDER BY visit_date DESC, id DESC").fetchall()
        seen: dict[str, None] = {}
        for (blob,) in rows:
            location = self._dec(blob, "record.location")
            if location:
                seen.setdefault(location)
        profiled = {self.get_profile(s.id).location for s in self.students()} - set(seen) - {""}
        return list(seen) + sorted(profiled)

    def students_at(self, location: str) -> list[int]:
        """Ids of the students seen at `location` ("" for none), most recently first, then
        those whose location it is now but who have no record there yet, by name."""
        seen = list(dict.fromkeys(r.student_id for r in self.records_at(location)))
        current = [s.id for s in self.students()
                   if s.id not in seen and location and self.student_location(s.id) == location]
        return seen + current

    # --- Excel export folder ----------------------------------------------------------

    def excel_folder(self) -> str:
        """The folder the last Excel export went to, "" before the first. Kept encrypted, since
        a path can name a school or a student."""
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key = 'excel_folder'").fetchone()
        return self._dec(row[0], "meta.excel_folder") if row else ""

    def set_excel_folder(self, folder: str) -> None:
        blob = self._enc(folder, "meta.excel_folder")
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('excel_folder', ?)",
                             (blob,))

    # --- follow-ups moved out of older comments ---------------------------------------

    def followups_reviewed(self) -> bool:
        """Whether the user has been through the follow-ups found in comments from before they
        had a box of their own (see followup.py), so the review is not offered again."""
        with self._lock:
            return self._db.execute("SELECT 1 FROM meta WHERE key = 'followups_reviewed'").fetchone() is not None

    def set_followups_reviewed(self) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('followups_reviewed', ?)", (b"1",))

    # --- export batches -------------------------------------------------------------

    def add_batch(self, data: dict) -> int:
        """Keep an export's code mapping (JSON-able `data`) encrypted so a corrected text
        can be restored later, also after a restart."""
        payload = self._enc(json.dumps(data, ensure_ascii=False), "export_batch.payload")
        with self._lock, self._db:
            cur = self._db.execute("INSERT INTO export_batch(created_at, payload) VALUES (?, ?)",
                                   (self._now().isoformat(), payload))
        return cur.lastrowid

    def batches(self) -> list[StoredBatch]:
        """All export batches, oldest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, created_at, payload FROM export_batch ORDER BY id").fetchall()
        return [self._batch(r) for r in rows]

    def get_batch(self, batch_id: int) -> StoredBatch:
        with self._lock:
            row = self._db.execute(
                "SELECT id, created_at, payload FROM export_batch WHERE id = ?",
                (batch_id,)).fetchone()
        if row is None:
            raise NotFound(f"export batch {batch_id}")
        return self._batch(row)

    def _batch(self, row: tuple) -> StoredBatch:
        data = json.loads(self._dec(row[2], "export_batch.payload"))
        return StoredBatch(row[0], datetime.fromisoformat(row[1]), data)

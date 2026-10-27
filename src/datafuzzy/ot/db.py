"""The chart database: students, their visit records and the export batches.

Names, student profiles, locations, both chart texts, the activities and the export mappings are encrypted
column by column;
only dates and ids stay readable so records can be found by date without the key.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Self

from platformdirs import user_data_dir

from . import APP_NAME
from .crypto import Cipher

# Overrides the database location (tests, or a chart book kept elsewhere).
DB_ENV = f"{APP_NAME.upper()}_DB"
KEY_CHECK_TEXT = "key-check"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS student (
    id      INTEGER PRIMARY KEY,
    name    BLOB NOT NULL,
    profile BLOB,  -- StudentProfile as JSON; NULL until first filled in
    active  INTEGER NOT NULL DEFAULT 1  -- 0 once their plan is done; they leave the timetable
);
CREATE TABLE IF NOT EXISTS record (
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
    UNIQUE (student_id, visit_date)
);
CREATE INDEX IF NOT EXISTS record_by_date ON record(visit_date);
CREATE TABLE IF NOT EXISTS export_batch (
    id         INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    payload    BLOB NOT NULL
);
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
    columns = {row[1] for row in db.execute("PRAGMA table_info(record)")}
    if "activity" not in columns:  # a chart book from before activities
        db.execute("ALTER TABLE record ADD COLUMN activity BLOB")
    if "start_time" not in columns:  # a chart book from before session times
        db.execute("ALTER TABLE record ADD COLUMN start_time TEXT")
    if "end_time" not in columns:  # a chart book from before end times
        db.execute("ALTER TABLE record ADD COLUMN end_time TEXT")
    if db.execute("PRAGMA user_version").fetchone()[0] < 1:
        fill_end_times(db)
        db.execute("PRAGMA user_version = 1")
    db.commit()
    path.chmod(0o600)
    return db


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


@dataclass(frozen=True)
class Student:
    id: int
    name: str
    active: bool = True  # False once their plan is done


@dataclass(frozen=True)
class Session:
    """A weekly session time of a student, e.g. Fridays 10:00–10:30, fetching them from 301."""
    weekday: int  # Monday 0 … Sunday 6
    start: str  # "HH:MM"
    end: str  # "HH:MM"
    classroom: str = ""  # the 學生教室: the room to fetch the student from; "" if not set


@dataclass(frozen=True)
class StudentProfile:
    """What the school form's header asks about a student, besides the name, and where they
    are seen (one place per student; new records take it). All free text; `school_year` reads
    like "09/2026-06/2027"."""
    diagnosis: str = ""
    age: str = ""
    grade: str = ""
    classroom: str = ""
    case_manager: str = ""
    school_year: str = ""
    goals: str = ""
    location: str = ""
    sessions: tuple[Session, ...] = ()  # as many as the student has, by weekday then start


SESSION_MINUTES = 30  # a new session's default length


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
    activity: str = ""  # the day's therapy activities; never exported
    start_time: str = ""  # when the session began, "HH:MM", or "" if not filled in; never exported
    end_time: str = ""  # when it ended, likewise


@dataclass(frozen=True)
class StoredBatch:
    id: int
    created_at: datetime
    data: dict


class NotFound(LookupError):
    """No student, record or batch with that id."""


class DuplicateRecord(Exception):
    """The student already has a record on that date. `record_id` is the existing one, so
    the caller can offer to open it instead."""

    def __init__(self, student_id: int, visit_date: date, record_id: int) -> None:
        super().__init__(f"student {student_id} already has record {record_id} on {visit_date}")
        self.student_id = student_id
        self.visit_date = visit_date
        self.record_id = record_id


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

    def add_student(self, name: str) -> Student:
        """Two students may share a name (it is encrypted, so it cannot be UNIQUE)."""
        name = name.strip()
        if not name:
            raise ValueError("student name is empty")
        with self._lock, self._db:
            cur = self._db.execute("INSERT INTO student(name) VALUES (?)",
                                   (self._enc(name, "student.name"),))
        return Student(cur.lastrowid, name)

    def get_student(self, student_id: int) -> Student:
        with self._lock:
            row = self._db.execute("SELECT id, name, active FROM student WHERE id = ?",
                                   (student_id,)).fetchone()
        if row is None:
            raise NotFound(f"student {student_id}")
        return self._student(row)

    def rename_student(self, student_id: int, name: str) -> Student:
        name = name.strip()
        if not name:
            raise ValueError("student name is empty")
        with self._lock, self._db:
            cur = self._db.execute("UPDATE student SET name = ? WHERE id = ?",
                                   (self._enc(name, "student.name"), student_id))
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
        return StudentProfile(**fields, sessions=sessions)

    def set_profile(self, student_id: int, profile: StudentProfile) -> None:
        """Replace the student's profile, with surrounding spaces trimmed from each field and the
        sessions sorted by weekday and start."""
        trimmed = {k: v.strip() for k, v in asdict(profile).items() if k != "sessions"}
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
            rows = self._db.execute("SELECT id, name, active FROM student").fetchall()
        return sorted((self._student(r) for r in rows), key=lambda s: (s.name.casefold(), s.id))

    def _student(self, row: tuple) -> Student:
        return Student(row[0], self._dec(row[1], "student.name"), bool(row[2]))

    # --- records --------------------------------------------------------------------

    def add_record(self, student_id: int, visit_date: date, location: str = "",
                   zh_text: str = "", en_text: str = "", activity: str = "",
                   start_time: str = "", end_time: str = "") -> Record:
        """Raises DuplicateRecord if the student already has a record that day, NotFound
        for an unknown student."""
        self.get_student(student_id)
        with self._lock:
            existing = self.find_record(student_id, visit_date)
            if existing:
                raise DuplicateRecord(student_id, visit_date, existing.id)
            updated_at = self._now()
            with self._db:
                cur = self._db.execute(
                    "INSERT INTO record(student_id, visit_date, location, zh_text, en_text,"
                    " updated_at, activity, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (student_id, visit_date.isoformat(), self._enc(location, "record.location"),
                     self._enc(zh_text, "record.zh_text"), self._enc(en_text, "record.en_text"),
                     updated_at.isoformat(), self._enc(activity, "record.activity"),
                     start_time or None, end_time or None))
        return Record(cur.lastrowid, student_id, visit_date, location, zh_text, en_text, updated_at,
                      activity, start_time, end_time)

    def update_record(self, record_id: int, *, location: str | None = None,
                      zh_text: str | None = None, en_text: str | None = None,
                      activity: str | None = None, start_time: str | None = None,
                      end_time: str | None = None) -> Record:
        """Change only the fields given (None leaves one alone), for autosave. The English
        text is overwritten, not versioned. Raises NotFound for an unknown record."""
        given = {"location": location, "zh_text": zh_text, "en_text": en_text, "activity": activity,
                 "start_time": start_time, "end_time": end_time}
        with self._lock:
            record = self.get_record(record_id)
            new = replace(record, updated_at=self._now(),
                          **{field: value for field, value in given.items() if value is not None})
            with self._db:
                self._write_texts(new)
        return new

    def move_record(self, record_id: int, visit_date: date) -> Record:
        """Correct the day of a record. Raises DuplicateRecord if the student already has
        another record that day, NotFound for an unknown record."""
        with self._lock:
            record = self.get_record(record_id)
            existing = self.find_record(record.student_id, visit_date)
            if existing and existing.id != record_id:
                raise DuplicateRecord(record.student_id, visit_date, existing.id)
            new = replace(record, visit_date=visit_date, updated_at=self._now())
            with self._db:
                self._db.execute("UPDATE record SET visit_date = ?, updated_at = ? WHERE id = ?",
                                 (visit_date.isoformat(), new.updated_at.isoformat(), record_id))
        return new

    def set_en_texts(self, texts: dict[int, str]) -> None:
        """Replace the English text of several records in one transaction: either all are
        written or, if one id is unknown (NotFound), none."""
        with self._lock, self._db:
            for record_id, en_text in texts.items():
                record = self.get_record(record_id)
                self._write_texts(replace(record, en_text=en_text, updated_at=self._now()))

    def _write_texts(self, r: Record) -> None:
        self._db.execute(
            "UPDATE record SET location = ?, zh_text = ?, en_text = ?, updated_at = ?,"
            " activity = ?, start_time = ?, end_time = ? WHERE id = ?",
            (self._enc(r.location, "record.location"), self._enc(r.zh_text, "record.zh_text"),
             self._enc(r.en_text, "record.en_text"), r.updated_at.isoformat(),
             self._enc(r.activity, "record.activity"), r.start_time or None,
             r.end_time or None, r.id))

    def delete_record(self, record_id: int) -> None:
        """Remove a record for good. Raises NotFound for an unknown record."""
        with self._lock, self._db:
            cur = self._db.execute("DELETE FROM record WHERE id = ?", (record_id,))
        if cur.rowcount == 0:
            raise NotFound(f"record {record_id}")

    _RECORD_COLUMNS = ("id, student_id, visit_date, location, zh_text, en_text, updated_at,"
                       " activity, start_time, end_time")

    def get_record(self, record_id: int) -> Record:
        with self._lock:
            row = self._db.execute(f"SELECT {self._RECORD_COLUMNS} FROM record WHERE id = ?",
                                   (record_id,)).fetchone()
        if row is None:
            raise NotFound(f"record {record_id}")
        return self._record(row)

    def find_record(self, student_id: int, visit_date: date) -> Record | None:
        with self._lock:
            row = self._db.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM record WHERE student_id = ? AND visit_date = ?",
                (student_id, visit_date.isoformat())).fetchone()
        return self._record(row) if row else None

    def _record(self, row: tuple) -> Record:
        return Record(row[0], row[1], date.fromisoformat(row[2]),
                      self._dec(row[3], "record.location"), self._dec(row[4], "record.zh_text"),
                      self._dec(row[5], "record.en_text"), datetime.fromisoformat(row[6]),
                      "" if row[7] is None else self._dec(row[7], "record.activity"), row[8] or "",
                      row[9] or "")

    def _records(self, where: str, args: tuple, order: str) -> list[Record]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {self._RECORD_COLUMNS} FROM record WHERE {where} ORDER BY {order}",
                args).fetchall()
        return [self._record(r) for r in rows]

    # --- queries --------------------------------------------------------------------

    def records_for_student(self, student_id: int, newest_first: bool = True) -> list[Record]:
        direction = "DESC" if newest_first else "ASC"
        return self._records("student_id = ?", (student_id,), f"visit_date {direction}, id {direction}")

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
        """Every 學生教室 given in a session time, sorted, for the profile's drop-downs."""
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

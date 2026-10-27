"""A student's profile: the details the school form's header asks for and where they are
seen. Edited in a dialog, shown read-only above each chart."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..db import Session, StudentProfile, default_end_time
from ..school_year import default_school_year, format_school_year, parse_school_year
from .cards import TIME_CHOICES, normal_time, session_label, time_label, weekday_label
from .i18n import language, tr

MONTH_FORMAT = "MM/yyyy"


def session_text(session: Session) -> str:
    """"週五 10:00 AM–10:30 AM（教室：301）", the room left out when not set."""
    text = f"{weekday_label(session.weekday)} {session_label(session.start, session.end)}"
    return text + tr("（教室：{room}）", room=session.classroom) if session.classroom else text


def sessions_text(sessions: tuple[Session, ...]) -> str:
    """Every session time for the summary, e.g. "週五 10:00 AM–10:30 AM（教室：301）、週一 …"."""
    return (", " if language() == "en" else "、").join(session_text(s) for s in sessions)


class SessionRow(QWidget):
    """One weekly session time: weekday, start, end and the 學生教室 (the room to fetch the
    student from; `classrooms` fills its drop-down, any other can be typed). The end keeps to
    SESSION_MINUTES after the start until it is changed by hand, as in the chart editor."""

    removed = Signal(object)  # this row

    def __init__(self, session: Session | None = None, classrooms: list[str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.weekday = QComboBox()
        for day in range(7):
            self.weekday.addItem(weekday_label(day), day)
        self.start = self._time_box(tr("例如 10:00 AM"))
        self.end = self._time_box(tr("例如 10:30 AM"))
        self.classroom = QComboBox()
        self.classroom.setEditable(True)
        self.classroom.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.classroom.addItems(classrooms or [])
        self.classroom.setEditText("")
        self.classroom.lineEdit().setPlaceholderText(tr("學生教室"))
        self.classroom.setToolTip(tr("到哪個教室接學生"))
        self.classroom.setMinimumContentsLength(6)
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setObjectName("flat")
        self.remove_btn.setToolTip(tr("移除這個時段"))
        if session is not None:
            self.weekday.setCurrentIndex(session.weekday)
            self.start.setEditText(time_label(session.start))
            self.end.setEditText(time_label(session.end))
            self.classroom.setEditText(session.classroom)
        self._end_follows = session is None or session.end == default_end_time(session.start)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.weekday)
        row.addWidget(self.start)
        row.addWidget(QLabel("–"))
        row.addWidget(self.end)
        row.addWidget(self.classroom)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        self.start.editTextChanged.connect(self._start_changed)
        self.end.editTextChanged.connect(self._end_changed)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))

    @staticmethod
    def _time_box(placeholder: str) -> QComboBox:
        box = QComboBox()
        box.setObjectName("time")
        box.setEditable(True)
        box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        box.addItems(TIME_CHOICES)
        box.setEditText("")
        box.lineEdit().setPlaceholderText(placeholder)
        box.setMinimumContentsLength(8)
        return box

    def _start_changed(self) -> None:
        start = normal_time(self.start.currentText())
        if self._end_follows and start:
            self.end.blockSignals(True)  # not a hand edit: keep following
            self.end.setEditText(time_label(default_end_time(start)))
            self.end.blockSignals(False)

    def _end_changed(self) -> None:
        self._end_follows = False

    def session(self) -> Session | None:
        """The session, or None while the start is blank. Raises ValueError for a time that
        cannot be read."""
        start, end = normal_time(self.start.currentText()), normal_time(self.end.currentText())
        if start is None or end is None:
            raise ValueError("not a time")
        if not start:
            return None
        return Session(self.weekday.currentData(), start, end or default_end_time(start),
                       self.classroom.currentText().strip())


class SessionsEditor(QWidget):
    """The student's weekly session times, as many as needed."""

    def __init__(self, sessions: tuple[Session, ...] = (), classrooms: list[str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.classrooms = classrooms or []
        self.rows: list[SessionRow] = []
        self.add_btn = QPushButton(tr("＋ 新增時段"))
        self.add_btn.setObjectName("flat")
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._rows)
        layout.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignLeft)
        for session in sessions:
            self.add_row(session)
        self.add_btn.clicked.connect(lambda: self.add_row())

    def add_row(self, session: Session | None = None) -> SessionRow:
        row = SessionRow(session, self.classrooms)
        row.removed.connect(self.remove_row)
        self.rows.append(row)
        self._rows.addWidget(row)
        return row

    def remove_row(self, row: SessionRow) -> None:
        self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def sessions(self) -> tuple[Session, ...]:
        """The filled-in rows (blank ones are left out). Raises ValueError for a time that
        cannot be read."""
        return tuple(s for s in (row.session() for row in self.rows) if s is not None)


class StudentProfileDialog(QDialog):
    """Location, diagnosis, age, grade, classroom, case manager, school year and goals of one
    student, and their weekly session times. `locations` and `classrooms` fill the drop-downs
    of the location and of each session's 學生教室; any other can be typed."""

    def __init__(self, name: str, profile: StudentProfile, today: date | None = None,
                 parent: QWidget | None = None, locations: list[str] | None = None,
                 classrooms: list[str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("{name} 的基本資訊", name=name))
        self.resize(640, 480)
        self.location = QComboBox()
        self.location.setObjectName("place")
        self.location.setEditable(True)
        self.location.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.location.lineEdit().setPlaceholderText(tr("學校或診所；新病歷會帶入"))
        self.location.addItems(locations or [])
        self.location.setEditText(profile.location)
        self.diagnosis = QLineEdit(profile.diagnosis)
        self.diagnosis.setPlaceholderText("ADHD, ODD")
        self.age = QLineEdit(profile.age)
        self.grade = QLineEdit(profile.grade)
        self.classroom = QLineEdit(profile.classroom)
        self.case_manager = QLineEdit(profile.case_manager)
        start, end = parse_school_year(profile.school_year) or default_school_year(today or date.today())
        self.year_from = self._month_edit(start)
        self.year_to = self._month_edit(end)
        self.goals = QPlainTextEdit(profile.goals)
        self.sessions = SessionsEditor(profile.sessions, classrooms)
        self.problem = QLabel("")
        self.problem.setStyleSheet("color: #ff453a;")  # as in the unlock prompt

        school_year = QHBoxLayout()
        school_year.addWidget(self.year_from)
        school_year.addWidget(QLabel(tr("到")))
        school_year.addWidget(self.year_to)
        school_year.addStretch(1)
        form = QFormLayout()
        form.addRow("Name", QLabel(name))
        form.addRow(tr("地點"), self.location)
        form.addRow("Diagnosis", self.diagnosis)
        form.addRow("Age", self.age)
        form.addRow("Grade", self.grade)
        form.addRow("Classroom", self.classroom)
        form.addRow("Case manager", self.case_manager)
        form.addRow("School year", school_year)
        form.addRow(tr("看診時段"), self.sessions)
        form.addRow("Goals", self.goals)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form, 1)
        layout.addWidget(self.problem)
        layout.addWidget(buttons)

    def accept(self) -> None:
        """Close only when every session time can be read; otherwise say so and stay open."""
        try:
            self.sessions.sessions()
        except ValueError:
            self.problem.setText(tr("時間請填成 9:30 AM 這樣的格式"))
            return
        super().accept()

    @staticmethod
    def _month_edit(day: date) -> QDateEdit:
        edit = QDateEdit(QDate(day.year, day.month, 1))
        edit.setDisplayFormat(MONTH_FORMAT)
        return edit

    def profile(self) -> StudentProfile:
        start, end = (e.date() for e in (self.year_from, self.year_to))
        return StudentProfile(
            diagnosis=self.diagnosis.text(), age=self.age.text(), grade=self.grade.text(),
            classroom=self.classroom.text(), case_manager=self.case_manager.text(),
            school_year=format_school_year(date(start.year(), start.month(), 1),
                                           date(end.year(), end.month(), 1)),
            goals=self.goals.toPlainText(), location=self.location.currentText(),
            sessions=self.sessions.sessions())


class ProfileSummary(QFrame):
    """The profile, read-only, at the top of a chart; its button asks for the edit dialog."""

    edit_requested = Signal()
    FIELDS = (("地點", "location"), ("Diagnosis", "diagnosis"), ("Age", "age"),
              ("Grade", "grade"), ("Classroom", "classroom"), ("Case manager", "case_manager"))
    PER_ROW = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("profile")
        self.name = QLabel("")
        self.name.setObjectName("title")
        self.edit_btn = QPushButton(tr("編輯基本資訊"))
        self.edit_btn.setObjectName("flat")
        self.values: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        wide = (("看診時段", "sessions"), ("School year", "school_year"), ("Goals", "goals"))
        for i, (label, field) in enumerate(self.FIELDS + wide):
            row, col = divmod(i, self.PER_ROW) if i < len(self.FIELDS) else (i - len(self.FIELDS) + 2, 0)
            caption = QLabel(tr(label))
            caption.setObjectName("subtle")
            caption.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            value = QLabel("")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.values[field] = value
            span = 1 if i < len(self.FIELDS) else 2 * self.PER_ROW - 1
            grid.addWidget(caption, row, 2 * col)
            grid.addWidget(value, row, 2 * col + 1, 1, span)
        for col in range(self.PER_ROW):
            grid.setColumnStretch(2 * col + 1, 1)
        head = QHBoxLayout()
        head.addWidget(self.name)
        head.addStretch(1)
        head.addWidget(self.edit_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(head)
        layout.addLayout(grid)
        self.edit_btn.clicked.connect(self.edit_requested)

    def show_profile(self, name: str, profile: StudentProfile) -> None:
        self.name.setText(name)
        for field, label in self.values.items():
            value = sessions_text(profile.sessions) if field == "sessions" else getattr(profile, field)
            label.setText(value.strip() or "—")

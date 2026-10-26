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

from ..db import StudentProfile
from ..school_year import default_school_year, format_school_year, parse_school_year

MONTH_FORMAT = "MM/yyyy"


class StudentProfileDialog(QDialog):
    """Location, diagnosis, age, grade, classroom, case manager, school year and goals of one
    student. `locations` fills the location drop-down; any other place can be typed."""

    def __init__(self, name: str, profile: StudentProfile, today: date | None = None,
                 parent: QWidget | None = None, locations: list[str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{name} 的基本資訊")
        self.resize(460, 440)
        self.location = QComboBox()
        self.location.setObjectName("place")
        self.location.setEditable(True)
        self.location.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.location.lineEdit().setPlaceholderText("學校或診所；新病歷會帶入")
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

        school_year = QHBoxLayout()
        school_year.addWidget(self.year_from)
        school_year.addWidget(QLabel("到"))
        school_year.addWidget(self.year_to)
        school_year.addStretch(1)
        form = QFormLayout()
        form.addRow("Name", QLabel(name))
        form.addRow("地點", self.location)
        form.addRow("Diagnosis", self.diagnosis)
        form.addRow("Age", self.age)
        form.addRow("Grade", self.grade)
        form.addRow("Classroom", self.classroom)
        form.addRow("Case manager", self.case_manager)
        form.addRow("School year", school_year)
        form.addRow("Goals", self.goals)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form, 1)
        layout.addWidget(buttons)

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
            goals=self.goals.toPlainText(), location=self.location.currentText())


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
        self.edit_btn = QPushButton("編輯基本資訊")
        self.edit_btn.setObjectName("flat")
        self.values: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        for i, (label, field) in enumerate(self.FIELDS + (("School year", "school_year"), ("Goals", "goals"))):
            row, col = divmod(i, self.PER_ROW) if i < len(self.FIELDS) else (i - len(self.FIELDS) + 2, 0)
            caption = QLabel(label)
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
            label.setText(getattr(profile, field).strip() or "—")

"""Editing a student's profile: the details the school form's header asks for."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..db import StudentProfile
from ..school_year import default_school_year, format_school_year, parse_school_year

MONTH_FORMAT = "MM/yyyy"


class StudentProfileDialog(QDialog):
    """Diagnosis, age, grade, classroom, case manager, school year and goals of one student."""

    def __init__(self, name: str, profile: StudentProfile, today: date | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{name} 的基本資訊")
        self.resize(460, 440)
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
            goals=self.goals.toPlainText())

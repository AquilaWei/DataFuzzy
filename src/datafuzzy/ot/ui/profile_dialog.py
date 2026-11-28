"""A student's profile: the details the school form's header asks for and where they are
seen. Edited in a dialog, shown read-only above each chart."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
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
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..db import (
    FREQUENCY_MAX,
    FREQUENCY_STEP,
    GRADES,
    PRESCHOOL,
    Plan,
    Session,
    StudentProfile,
    default_end_time,
    parse_plan_date,
)
from ..school_year import default_school_year, format_school_year, parse_school_year
from .cards import TIME_CHOICES, normal_time, session_label, time_label, weekday_label
from .i18n import language, tr
from .widgets import GrowingTextEdit

MONTH_FORMAT = "MM/yyyy"


def session_text(session: Session) -> str:
    """"週五 10:00 AM–10:30 AM（領取教室：301）", the room left out when not set."""
    text = f"{weekday_label(session.weekday)} {session_label(session.start, session.end)}"
    return text + tr("（領取教室：{room}）", room=session.classroom) if session.classroom else text


def sessions_text(sessions: tuple[Session, ...]) -> str:
    """Every session time for the summary, e.g. "週五 10:00 AM–10:30 AM（領取教室：301）、週一 …"."""
    return (", " if language() == "en" else "、").join(session_text(s) for s in sessions)


class SessionRow(QWidget):
    """One weekly session time: weekday, start, end and the 領取教室 (where to find the child
    for the session; `classrooms` fills its drop-down, any other can be typed). The end keeps
    to SESSION_MINUTES after the start until it is changed by hand, as in the chart editor."""

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
        self.classroom.lineEdit().setPlaceholderText(tr("領取教室"))
        self.classroom.setToolTip(tr("去哪裡找這個孩子"))
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

    changed = Signal()  # a row added, taken out or edited

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
        row.start.editTextChanged.connect(self.changed)
        row.end.editTextChanged.connect(self.changed)
        self.rows.append(row)
        self._rows.addWidget(row)
        self.changed.emit()
        return row

    def remove_row(self, row: SessionRow) -> None:
        self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self.changed.emit()

    def sessions(self) -> tuple[Session, ...]:
        """The filled-in rows (blank ones are left out). Raises ValueError for a time that
        cannot be read."""
        return tuple(s for s in (row.session() for row in self.rows) if s is not None)


class GoalRow(QWidget):
    """One goal: "Goal n", its text and a button to take it out."""

    removed = Signal(object)  # this row

    def __init__(self, number: int, goal: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QLabel("")
        self.edit = GrowingTextEdit(goal, min_lines=1)
        self.edit.setPlaceholderText(tr("例如 能獨立扣好三顆釦子"))
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setObjectName("flat")
        self.remove_btn.setToolTip(tr("移除這個目標"))
        self.number(number)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.label, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.edit, 1)
        row.addWidget(self.remove_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))

    def number(self, number: int) -> None:
        self.label.setText(f"Goal {number}")


class GoalsEditor(QWidget):
    """The student's goals, as many as they have. Their order is their number on the form,
    Goal 1 first; taking one out renumbers those after it."""

    changed = Signal()  # a goal added, taken out or edited

    def __init__(self, goals: tuple[str, ...] = (), parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows: list[GoalRow] = []
        self.add_btn = QPushButton(tr("＋ 新增目標"))
        self.add_btn.setObjectName("flat")
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._rows)
        layout.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)  # the dialog's spare height goes below the goals, not between them
        self.set_goals(goals)
        self.add_btn.clicked.connect(lambda: self.add_row())

    def set_goals(self, goals: tuple[str, ...]) -> None:
        """Show `goals` in place of the rows there are, e.g. for another plan."""
        for row in self.rows:
            row.setParent(None)
            row.deleteLater()
        self.rows = []
        for goal in goals:
            self.add_row(goal)

    def add_row(self, goal: str = "") -> GoalRow:
        row = GoalRow(len(self.rows) + 1, goal)
        row.removed.connect(self.remove_row)
        row.edit.textChanged.connect(self.changed)
        self.rows.append(row)
        self._rows.addWidget(row)
        self.changed.emit()
        return row

    def remove_row(self, row: GoalRow) -> None:
        self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        for number, other in enumerate(self.rows, start=1):
            other.number(number)
        self.changed.emit()

    def goals(self) -> tuple[str, ...]:
        """The filled-in goals in order (blank ones are left out)."""
        return tuple(g for g in (row.edit.toPlainText().strip() for row in self.rows) if g)


def plan_text(plan: Plan) -> str:
    """"IEP 10/29/2026", or "IEP（未填日期）" for a plan without a date."""
    return f"{plan.kind} {plan.plan_date.strip() or tr('（未填日期）')}"


class PlanDateEdit(QDateEdit):
    """A plan's date, picked from a calendar. BLANK, the earliest date it takes, stands for no
    date yet and shows as 未填; value() is the date as the form writes it, "MM/DD/YYYY"."""

    BLANK = QDate(2000, 1, 1)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat("MM/dd/yyyy")
        self.setMinimumDate(self.BLANK)
        self.setSpecialValueText(tr("未填"))
        self.setDate(self.BLANK)

    def value(self) -> str:
        return "" if self.date() == self.BLANK else self.date().toString("MM/dd/yyyy")

    def set_value(self, text: str) -> None:
        """Show `text`; blank, or a date that cannot be read (from before dates were picked), as 未填."""
        day = parse_plan_date(text)
        self.setDate(QDate(day.year, day.month, day.day) if day else self.BLANK)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if self.date() == self.BLANK:  # open the calendar at this month, not at BLANK's
            today = QDate.currentDate()
            QTimer.singleShot(0, lambda: self.calendarWidget().setCurrentPage(today.year(), today.month()))


def count_box(choices: range | tuple[int, ...]) -> QComboBox:
    """A drop-down of whole numbers that takes any other typed in; "—" for none."""
    box = QComboBox()
    box.setEditable(True)
    box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    box.setValidator(QIntValidator(0, 999, box))
    box.addItems(["—", *(str(n) for n in choices)])
    box.setMinimumContentsLength(3)
    return box


def count_of(box: QComboBox) -> int:
    text = box.currentText().strip()
    return int(text) if text.isdigit() else 0


def set_count(box: QComboBox, count: int) -> None:
    box.setEditText(str(count) if count else "—")


class PlanEditor(QWidget):
    """The student's IEP and 504 plans, one shown at a time. This widget is the picker of the
    plans, newest first, with the buttons to add and delete one; the shown plan's type
    (`plan_iep`/`plan_504` in `plan_type`), `plan_date`, `service_type`, frequency (in
    `frequency_stack`: minutes a month, or for a pre-school student visits, days and units)
    and `goals` are laid out by the dialog, a row each. A new plan starts blank and the old
    ones are kept."""

    def __init__(self, plans: tuple[Plan, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plans = list(reversed(plans))  # as the picker lists them, newest first
        self._shown = 0
        self.picker = QComboBox()
        self.picker.setToolTip(tr("切換顯示其他 IEP/504 計畫和它的目標"))
        self.add_btn = QPushButton(tr("＋ 新的計畫"))
        self.add_btn.setObjectName("flat")
        self.add_btn.setToolTip(tr("IEP/504 快到期時，填入新的日期和目標；舊的會保留"))
        self.remove_btn = QPushButton(tr("刪除這份計畫"))
        self.remove_btn.setObjectName("flat")
        self.plan_iep = QRadioButton("IEP")
        self.plan_504 = QRadioButton("504")
        kinds = QButtonGroup(self)  # one or the other
        kinds.addButton(self.plan_iep)
        kinds.addButton(self.plan_504)
        self.plan_type = QWidget()
        kind_row = QHBoxLayout(self.plan_type)
        kind_row.setContentsMargins(0, 0, 0, 0)
        kind_row.addWidget(self.plan_iep)
        kind_row.addWidget(self.plan_504)
        kind_row.addStretch(1)
        self.plan_date = PlanDateEdit()
        self.service_type = QComboBox()
        self.service_type.addItem("Individual", False)
        self.service_type.addItem("Group", True)
        self.frequency = QComboBox()  # a list, so the minutes stay a multiple of FREQUENCY_STEP
        self.frequency.setToolTip(tr("每個月的治療分鐘數"))
        self.frequency.addItem("—", 0)
        for minutes in range(FREQUENCY_STEP, FREQUENCY_MAX + 1, FREQUENCY_STEP):
            self.frequency.addItem(f"{minutes} mins/month", minutes)
        self.visits, self.days, self.units = count_box(range(1, 8)), count_box((7, 14, 30)), count_box(range(1, 9))
        visits = QWidget()
        visit_row = QHBoxLayout(visits)
        visit_row.setContentsMargins(0, 0, 0, 0)
        for part in (self.visits, QLabel("times per"), self.days, QLabel("days,"), self.units, QLabel("units")):
            visit_row.addWidget(part)
        visit_row.addStretch(1)
        minutes = QWidget()
        minute_row = QHBoxLayout(minutes)
        minute_row.setContentsMargins(0, 0, 0, 0)
        minute_row.addWidget(self.frequency)
        minute_row.addStretch(1)
        self.frequency_stack = QStackedWidget()  # page 0 minutes a month, page 1 a pre-school student's visits
        self.frequency_stack.addWidget(minutes)
        self.frequency_stack.addWidget(visits)
        self.goals = GoalsEditor()
        pick = QHBoxLayout(self)
        pick.setContentsMargins(0, 0, 0, 0)
        pick.addWidget(self.picker, 1)
        pick.addWidget(self.add_btn)
        pick.addWidget(self.remove_btn)
        self._list()
        self._load()
        self.picker.currentIndexChanged.connect(self._pick)
        self.add_btn.clicked.connect(self.add_plan)
        self.remove_btn.clicked.connect(lambda: self.remove_plan())
        self.plan_date.dateChanged.connect(self._relabel)
        self.plan_504.toggled.connect(self._relabel)

    def set_preschool(self, preschool: bool) -> None:
        """Ask for the frequency as a pre-school student's visits, or as minutes a month."""
        self.frequency_stack.setCurrentIndex(1 if preschool else 0)

    def _list(self) -> None:
        self.picker.blockSignals(True)  # rebuilding the list is not picking a plan
        self.picker.clear()
        self.picker.addItems([plan_text(p) for p in self._plans])
        self.picker.setCurrentIndex(self._shown)
        self.picker.blockSignals(False)
        several = len(self._plans) > 1
        self.picker.setVisible(several)
        self.remove_btn.setVisible(several)

    def _load(self) -> None:
        plan = self._plans[self._shown]
        for edit, set_value in (
                (self.plan_date, lambda: self.plan_date.set_value(plan.plan_date)),
                (self.plan_504, lambda: (self.plan_504 if plan.plan_504 else self.plan_iep).setChecked(True)),
                (self.service_type, lambda: self.service_type.setCurrentIndex(1 if plan.group else 0)),
                (self.frequency, lambda: self.set_frequency(plan.frequency)),
                (self.visits, lambda: set_count(self.visits, plan.visits)),
                (self.days, lambda: set_count(self.days, plan.days)),
                (self.units, lambda: set_count(self.units, plan.units))):
            edit.blockSignals(True)
            set_value()
            edit.blockSignals(False)
        self.goals.set_goals(plan.goals)

    def _shown_plan(self, goals: tuple[str, ...]) -> Plan:
        return Plan(self.plan_504.isChecked(), self.plan_date.value(), goals, self.frequency.currentData(),
                    self.service_type.currentData(), count_of(self.visits), count_of(self.days),
                    count_of(self.units))

    def _keep(self) -> None:
        """Take the shown plan's edits into the list."""
        self._plans[self._shown] = self._shown_plan(self.goals.goals())

    def set_frequency(self, minutes: int) -> None:
        """Pick `minutes` a month; one not in the list (from an older version) is added to it."""
        index = self.frequency.findData(minutes)
        if index < 0:
            self.frequency.addItem(f"{minutes} mins/month", minutes)
            index = self.frequency.count() - 1
        self.frequency.setCurrentIndex(index)

    def _pick(self, index: int) -> None:
        self._keep()
        self._shown = index
        self._load()

    def _relabel(self) -> None:
        self._keep()
        self.picker.setItemText(self._shown, plan_text(self._plans[self._shown]))

    def show_plan(self, index: int) -> None:
        """Show the plan at `index` of the picker (0 the newest)."""
        self.picker.setCurrentIndex(index)

    def add_plan(self) -> None:
        """Start a blank plan, of the kind, service type and frequency of the one shown, and show it."""
        self._keep()
        self._plans.insert(0, replace(self._shown_plan(()), plan_date=""))
        self._shown = 0
        self._list()
        self._load()
        self.plan_date.setFocus()

    def remove_plan(self, confirm: bool = True) -> None:
        """Delete the shown plan and its goals, after asking unless `confirm` is False; the
        last plan stays."""
        if len(self._plans) < 2:
            return
        if confirm and not self._ask_remove():
            return
        del self._plans[self._shown]
        self._shown = 0
        self._list()
        self._load()

    def _ask_remove(self) -> bool:
        box = QMessageBox(QMessageBox.Icon.Warning, tr("刪除計畫"),
                          tr("要刪除「{plan}」和它的目標嗎？", plan=plan_text(self._plans[self._shown])),
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, self)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)  # a stray Return keeps the plan
        return box.exec() == QMessageBox.StandardButton.Yes

    def as_edited(self) -> list[Plan]:
        """Every plan, the shown one as edited so far, without taking its edits into the list
        (it may be half loaded)."""
        plans = list(self._plans)
        plans[self._shown] = self._shown_plan(self.goals.goals())
        return plans

    def plans(self) -> list[Plan]:
        """Every plan, as edited, newest first as listed."""
        self._keep()
        return list(self._plans)

    def problem(self) -> str:
        """Why the plans cannot be saved as they are, or "": a date that cannot be read, or,
        with several plans, one without a date or two of the same date."""
        plans = self.plans()
        if any(p.plan_date.strip() and parse_plan_date(p.plan_date) is None for p in plans):
            return tr("IEP/504 日期請填成 10/29/2026 這樣的格式")
        if len(plans) > 1 and not all(p.plan_date.strip() for p in plans):
            return tr("日期格式錯誤：至少有一份計畫沒有填寫日期，請填寫日期")
        if len({parse_plan_date(p.plan_date) for p in plans}) < len(plans):
            return tr("兩份 IEP/504 計畫的日期不能相同")
        return ""


class StudentProfileDialog(QDialog):
    """Location, diagnosis, age, grade, classroom, case manager, MA billing, IEP or 504 date, school year
    and goals of one student, and their weekly session times. `locations` and `classrooms` fill the drop-downs
    of the location and of each session's 領取教室; any other can be typed."""

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
        self.grade = QComboBox()
        self.grade.addItems(["", *GRADES])
        if profile.grade not in GRADES and profile.grade:  # an older grade grade_choice could not read: kept
            self.grade.addItem(profile.grade)
        self.grade.setCurrentText(profile.grade)
        self.classroom = QLineEdit(profile.classroom)
        self.case_manager = QLineEdit(profile.case_manager)
        self.ma_billing = QCheckBox()
        self.ma_billing.setChecked(profile.ma_billing)
        start, end = parse_school_year(profile.school_year) or default_school_year(today or date.today())
        self.year_from = self._month_edit(start)
        self.year_to = self._month_edit(end)
        self.plans = PlanEditor(profile.plans)
        self.plan_date, self.plan_504, self.goals = self.plans.plan_date, self.plans.plan_504, self.plans.goals
        self.frequency = self.plans.frequency
        self.plans.set_preschool(profile.grade == PRESCHOOL)
        self.grade.currentTextChanged.connect(lambda grade: self.plans.set_preschool(grade == PRESCHOOL))
        self.sessions = SessionsEditor(profile.sessions, classrooms)
        self.problem = QLabel("")
        self.problem.setStyleSheet("color: #ff453a;")  # as in the unlock prompt
        self.gaps_note = QLabel("")  # what is not filled in yet, kept up to date while editing
        self.gaps_note.setWordWrap(True)
        self.gaps_note.setStyleSheet(f"color: {GAPS_COLOR};")

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
        form.addRow("MA billing", self.ma_billing)
        form.addRow("Service plan", self.plans)
        form.addRow("Plan type", self.plans.plan_type)
        form.addRow("Date", self.plan_date)
        form.addRow("Service type", self.plans.service_type)
        form.addRow("Frequency", self.plans.frequency_stack)
        form.addRow("Goals", self.goals)  # the shown plan's, so right below it
        form.addRow("School year", school_year)
        form.addRow(tr("看診時段"), self.sessions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.gaps_note)
        layout.addLayout(form)
        layout.addStretch(1)  # spare height below the form, not inside the goals
        layout.addWidget(self.problem)
        layout.addWidget(buttons)

        # The row of each part profile_gaps names, to mark it while it is blank.
        self._gap_labels = {gap: form.labelForField(widget) for gap, widget in (
            ("地點", self.location), ("Diagnosis", self.diagnosis), ("Age", self.age), ("Grade", self.grade),
            ("Classroom", self.classroom), ("Case manager", self.case_manager), ("IEP/504 Date", self.plan_date),
            ("Frequency", self.plans.frequency_stack), ("Goals", self.goals), ("看診時段", self.sessions))}
        self._gap_texts = {gap: label.text() for gap, label in self._gap_labels.items()}
        for edit in (self.diagnosis, self.age, self.classroom, self.case_manager):
            edit.textChanged.connect(self.show_gaps)
        self.location.editTextChanged.connect(self.show_gaps)
        self.grade.currentTextChanged.connect(self.show_gaps)
        self.plan_date.dateChanged.connect(self.show_gaps)
        for box in (self.plans.picker, self.plans.frequency, self.plans.visits, self.plans.days, self.plans.units):
            box.currentIndexChanged.connect(self.show_gaps)
        for button in (self.plans.add_btn, self.plans.remove_btn):
            button.clicked.connect(self.show_gaps)
        self.goals.changed.connect(self.show_gaps)
        self.sessions.changed.connect(self.show_gaps)
        self.show_gaps()

    def gaps(self) -> list[str]:
        """What profile_gaps finds blank in the profile as edited so far; a session time that
        cannot be read yet counts as filled in (accept() tells about it)."""
        try:
            sessions = self.sessions.sessions()
        except ValueError:
            sessions = (Session(0, "", ""),)
        start, end = (e.date() for e in (self.year_from, self.year_to))
        profile = StudentProfile(
            diagnosis=self.diagnosis.text(), age=self.age.text(), grade=self.grade.currentText(),
            classroom=self.classroom.text(), case_manager=self.case_manager.text(),
            school_year=format_school_year(date(start.year(), start.month(), 1), date(end.year(), end.month(), 1)),
            location=self.location.currentText(), sessions=sessions).with_plans(self.plans.as_edited())
        return profile_gaps(profile)

    def show_gaps(self) -> None:
        """Say above the form what is not filled in yet, and mark those rows in orange."""
        gaps = self.gaps()
        self.gaps_note.setText(tr("⚠ 基本資訊還沒填完整，缺：{parts}", parts="、".join(tr(g) for g in gaps)))
        self.gaps_note.setVisible(bool(gaps))
        for gap, label in self._gap_labels.items():
            missing = gap in gaps
            label.setText(f"⚠ {self._gap_texts[gap]}" if missing else self._gap_texts[gap])
            label.setStyleSheet(f"color: {GAPS_COLOR};" if missing else "")

    def accept(self) -> None:
        """Close only when every session time and plan date can be read; otherwise say so and
        stay open."""
        if problem := self.plans.problem():
            self.problem.setText(problem)
            return
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
            diagnosis=self.diagnosis.text(), age=self.age.text(), grade=self.grade.currentText(),
            classroom=self.classroom.text(), case_manager=self.case_manager.text(),
            ma_billing=self.ma_billing.isChecked(),
            school_year=format_school_year(date(start.year(), start.month(), 1),
                                           date(end.year(), end.month(), 1)),
            location=self.location.currentText(),
            sessions=self.sessions.sessions()).with_plans(self.plans.plans())


class ProfileSummary(QFrame):
    """The profile, read-only, at the top of a chart; its button asks for the edit dialog."""

    edit_requested = Signal()
    FIELDS = (("地點", "location"), ("Diagnosis", "diagnosis"), ("Age", "age"),
              ("Grade", "grade"), ("Classroom", "classroom"), ("Case manager", "case_manager"),
              ("MA billing", "ma_billing"), ("IEP/504 Date", "plan"))
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
            short_rows = -(-len(self.FIELDS) // self.PER_ROW)  # rows of the short fields, rounded up
            row, col = divmod(i, self.PER_ROW) if i < len(self.FIELDS) else (i - len(self.FIELDS) + short_rows, 0)
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

    def show_profile(self, name: str, profile: StudentProfile, day: date | None = None) -> None:
        """Show `profile`, with the plan and goals in effect on `day` (the latest without one)."""
        self.name.setText(name)
        plan = profile.plan if day is None else profile.plan_on(day)
        for field, label in self.values.items():
            label.setText(summary_value(profile, field, plan).strip() or "—")


def summary_value(profile: StudentProfile, field: str, plan: Plan | None = None) -> str:
    """What the summary shows for `field`: the profile's text, or for the session times, the
    plan and the goals (of `plan`, else the latest), a line made from them ("" when there is
    nothing to show)."""
    plan = plan or profile.plan
    if field == "sessions":
        return sessions_text(profile.sessions)
    if field == "plan":
        return " · ".join(t for t in (f"{plan.kind} {plan.plan_date}" if plan.plan_date else "",
                                      plan.frequency_text_for(profile.grade == PRESCHOOL)) if t)
    if field == "goals":
        return "\n".join(f"{i}. {goal}" for i, goal in enumerate(plan.goals, start=1))
    if field == "ma_billing":
        return "Yes" if profile.ma_billing else ""
    return getattr(profile, field)


GAPS_COLOR = "#e07b00"  # orange, readable light or dark: what is not filled in yet


def profile_gaps(profile: StudentProfile, location: str = "") -> list[str]:
    """The parts of a student's 基本資訊 left blank, named as the dialog names them: the
    location (`location`, else the profile's), diagnosis, age, grade, classroom, case manager,
    the latest plan's date, frequency (a pre-school student's times per days and units, a
    minutes a month otherwise) and goals, and the session times. MA billing and the school
    year always have a value."""
    plan = profile.plan
    frequency = (plan.visits and plan.days and plan.units) if profile.grade == PRESCHOOL else plan.frequency
    parts = (("地點", location or profile.location), ("Diagnosis", profile.diagnosis), ("Age", profile.age),
             ("Grade", profile.grade), ("Classroom", profile.classroom), ("Case manager", profile.case_manager),
             ("IEP/504 Date", plan.plan_date), ("Frequency", frequency),
             ("Goals", "".join(plan.goals)), ("看診時段", profile.sessions))
    return [name for name, value in parts if not (value.strip() if isinstance(value, str) else value)]

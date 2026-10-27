"""The weekly timetable: which active students come on which weekday at what time, from the
session times in their profiles. Clicking a student shows all of their charts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..db import RecordStore, Session, Student
from .cards import session_label, time_label, weekday_label
from .i18n import tr
from .student_view import StudentRecordsView

WORKDAYS = range(5)  # Monday to Friday always get a column; the weekend only when used


def timetable_grid(slots: list[tuple[Session, Student]]) -> tuple[list[int], list[str], dict]:
    """(weekdays, starts, cells) for the grid: the weekday columns, the distinct start times as
    rows, and {(weekday, start): [(session, student), …]} in the order of `slots`."""
    weekdays = sorted(set(WORKDAYS) | {session.weekday for session, _ in slots})
    starts = sorted({session.start for session, _ in slots})
    cells: dict[tuple[int, str], list[tuple[Session, Student]]] = {}
    for session, student in slots:
        cells.setdefault((session.weekday, session.start), []).append((session, student))
    return weekdays, starts, cells


class TimetableView(QWidget):
    """Two pages: the week grid, and one student's charts (with a way back to the grid).
    The window calls refresh() after anything that may change the timetable."""

    open_record = Signal(int)
    delete_record = Signal(int)
    rename_student = Signal(int)
    edit_profile = Signal(int)

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.slot_buttons: list[QPushButton] = []

        self.title = QLabel(tr("課表"))
        self.title.setObjectName("title")
        self.count = QLabel("")
        self.count.setObjectName("subtle")
        self.empty = QLabel(tr("還沒有學生設定看診時段。在學生的「基本資訊」加入看診時段，就會出現在課表上。"))
        self.empty.setObjectName("subtle")
        self.empty.setWordWrap(True)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        grid_page = QWidget()
        grid_layout = QVBoxLayout(grid_page)
        grid_layout.setContentsMargins(24, 20, 24, 12)
        grid_layout.setSpacing(0)
        grid_layout.addWidget(self.title)
        grid_layout.addWidget(self.count)
        grid_layout.addSpacing(10)
        grid_layout.addWidget(self.empty)
        grid_layout.addWidget(self.scroll, 1)

        self.back_btn = QPushButton(tr("‹ 課表"))
        self.back_btn.setObjectName("flat")
        self.student_view = StudentRecordsView(store)
        student_page = QWidget()
        student_layout = QVBoxLayout(student_page)
        student_layout.setContentsMargins(0, 12, 0, 0)
        student_layout.setSpacing(0)
        back_row = QHBoxLayout()
        back_row.setContentsMargins(18, 0, 0, 0)
        back_row.addWidget(self.back_btn)
        back_row.addStretch(1)
        student_layout.addLayout(back_row)
        student_layout.addWidget(self.student_view, 1)

        self.pages = QStackedWidget()
        self.pages.addWidget(grid_page)
        self.pages.addWidget(student_page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pages)

        self.back_btn.clicked.connect(self.show_grid)
        self.student_view.open_record.connect(self.open_record)
        self.student_view.delete_record.connect(self.delete_record)
        self.student_view.rename_student.connect(self.rename_student)
        self.student_view.edit_profile.connect(self.edit_profile)
        self.refresh()

    @property
    def student_id(self) -> int | None:
        """The student whose charts are shown, or None on the grid."""
        return self.student_view.student_id if self.pages.currentIndex() == 1 else None

    def show_grid(self) -> None:
        self.pages.setCurrentIndex(0)
        self.refresh()

    def show_student(self, student_id: int) -> None:
        self.student_view.show_student(student_id)
        self.pages.setCurrentIndex(1)

    def refresh(self) -> None:
        """Rebuild the grid from the profiles, and reload the shown student's charts (back to
        the grid if they were deleted)."""
        if self.student_id is not None:
            if self.student_id in {s.id for s in self.store.students()}:
                self.student_view.refresh()
            else:
                self.pages.setCurrentIndex(0)
        slots = self.store.timetable()
        self.count.setText(tr("{students} 位學生 · {sessions} 個時段",
                              students=len({student.id for _, student in slots}), sessions=len(slots)))
        self.empty.setVisible(not slots)
        self.scroll.setVisible(bool(slots))
        self.scroll.setWidget(self._grid(slots))

    def _grid(self, slots: list[tuple[Session, Student]]) -> QWidget:
        weekdays, starts, cells = timetable_grid(slots)
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.slot_buttons = []
        for col, weekday in enumerate(weekdays, start=1):
            head = QLabel(weekday_label(weekday))
            head.setObjectName("weekday")
            head.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(head, 0, col)
            grid.setColumnStretch(col, 1)
        for row, start in enumerate(starts, start=1):
            time = QLabel(time_label(start))
            time.setObjectName("slotTime")
            time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(time, row, 0)
            for col, weekday in enumerate(weekdays, start=1):
                cell = QVBoxLayout()
                cell.setSpacing(4)
                for session, student in cells.get((weekday, start), []):
                    lines = [student.name, session_label(session.start, session.end)]
                    if session.classroom:
                        lines.append(tr("領取教室：{room}", room=session.classroom))
                    button = QPushButton("\n".join(lines))
                    button.setObjectName("slot")
                    button.setToolTip(tr("查看 {name} 的所有病歷", name=student.name))
                    button.clicked.connect(lambda _=False, sid=student.id: self.show_student(sid))
                    button.setProperty("student_id", student.id)
                    self.slot_buttons.append(button)
                    cell.addWidget(button)
                cell.addStretch(1)
                grid.addLayout(cell, row, col)
        grid.setRowStretch(len(starts) + 1, 1)
        return widget

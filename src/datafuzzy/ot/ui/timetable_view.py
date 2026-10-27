"""The weekly timetable: which active students come on which weekday at what time, from the
session times in their profiles. Clicking a student shows all of their charts."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent, QPalette
from PySide6.QtWidgets import (
    QFrame,
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
# Each student keeps one of these colours wherever they appear, so the same child is easy to
# follow across the week; mid-tone, so they read on light and dark backgrounds alike.
STUDENT_COLOURS = ("#0a84ff", "#30a46c", "#f76b15", "#8e4ec6", "#d6409f", "#12a594", "#e5484d", "#c2860a")


def student_colour(student_id: int) -> QColor:
    return QColor(STUDENT_COLOURS[student_id % len(STUDENT_COLOURS)])


class SlotChip(QPushButton):
    """A student in the timetable: a rounded tile in the student's colour, the name in bold and
    the time (and pickup room) under it. text() holds all the lines, for tests and accessibility."""

    PAD_X, PAD_Y, GAP, BAR = 10, 7, 2, 3

    def __init__(self, student: Student, lines: list[str], parent: QWidget | None = None) -> None:
        super().__init__("\n".join([student.name, *lines]), parent)
        self.setObjectName("slot")
        self.name, self.lines = student.name, lines
        self.colour = student_colour(student.id)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def _fonts(self) -> tuple[QFont, QFont]:
        name = QFont(self.font())
        name.setWeight(QFont.Weight.Bold)
        small = QFont(self.font())
        small.setPointSizeF(small.pointSizeF() - 1)
        return name, small

    def sizeHint(self) -> QSize:
        name, small = self._fonts()
        widths = [QFontMetrics(name).horizontalAdvance(self.name)]
        widths += [QFontMetrics(small).horizontalAdvance(line) for line in self.lines]
        height = QFontMetrics(name).height() + len(self.lines) * (QFontMetrics(small).height() + self.GAP)
        return QSize(max(widths) + 2 * self.PAD_X + self.BAR, height + 2 * self.PAD_Y)

    def minimumSizeHint(self) -> QSize:
        return QSize(60, self.sizeHint().height())

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fill = QColor(self.colour)
        fill.setAlphaF(0.26 if self.underMouse() else 0.14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 9, 9)
        painter.setBrush(self.colour)
        painter.drawRoundedRect(QRectF(rect.left() + 5, rect.top() + 7, self.BAR, rect.height() - 14), 1.5, 1.5)

        name_font, small_font = self._fonts()
        left = int(rect.left()) + self.PAD_X + self.BAR
        width = int(rect.width()) - left - self.PAD_X
        top = self.PAD_Y
        painter.setFont(name_font)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        metrics = QFontMetrics(name_font)
        painter.drawText(left, top, width, metrics.height(), Qt.AlignmentFlag.AlignLeft,
                         metrics.elidedText(self.name, Qt.TextElideMode.ElideRight, width))
        top += metrics.height()
        painter.setFont(small_font)
        painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        metrics = QFontMetrics(small_font)
        for line in self.lines:
            top += self.GAP
            painter.drawText(left, top, width, metrics.height(), Qt.AlignmentFlag.AlignLeft,
                             metrics.elidedText(line, Qt.TextElideMode.ElideRight, width))
            top += metrics.height()


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
        """A rounded card: weekday headings (today's highlighted), then one rounded lane per
        start time, every other lane tinted, the students as coloured tiles in their weekday."""
        weekdays, starts, cells = timetable_grid(slots)
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        table = QFrame()
        table.setObjectName("timetable")
        outer.addWidget(table)
        outer.addStretch(1)
        grid = QGridLayout(table)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(6)
        self.slot_buttons = []
        today = date.today().weekday()
        for col, weekday in enumerate(weekdays, start=1):
            head = QLabel(weekday_label(weekday))
            head.setObjectName("weekday")
            head.setProperty("today", weekday == today)  # picked up by the stylesheet
            head.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(self._cell(head, kind="head"), 0, col)
            grid.setColumnStretch(col, 1)
        for row, start in enumerate(starts, start=1):
            band = "band" if row % 2 == 0 else "plain"
            lane = QFrame()  # behind the row's cells: added first, so drawn first
            lane.setObjectName("lane")
            lane.setProperty("kind", band)
            grid.addWidget(lane, row, 0, 1, len(weekdays) + 1)
            time = QLabel(time_label(start))
            time.setObjectName("slotTime")
            time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(self._cell(time, kind="time"), row, 0)
            for col, weekday in enumerate(weekdays, start=1):
                buttons = [self._slot_button(session, student)
                           for session, student in cells.get((weekday, start), [])]
                grid.addWidget(self._cell(*buttons, kind=band), row, col)
        return widget

    @staticmethod
    def _cell(*children: QWidget, kind: str) -> QFrame:
        """One cell of the table; `kind` (head, time, band or plain) says which part it is."""
        cell = QFrame()
        cell.setObjectName("ttCell")
        cell.setProperty("kind", kind)
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(5, 6, 5, 6)
        layout.setSpacing(5)
        for child in children:
            layout.addWidget(child)
        layout.addStretch(1)
        return cell

    def _slot_button(self, session: Session, student: Student) -> QPushButton:
        lines = [session_label(session.start, session.end)]
        if session.classroom:
            lines.append(tr("領取教室：{room}", room=session.classroom))
        button = SlotChip(student, lines)
        button.setToolTip(tr("查看 {name} 的所有病歷", name=student.name))
        button.clicked.connect(lambda _=False, sid=student.id: self.show_student(sid))
        button.setProperty("student_id", student.id)
        self.slot_buttons.append(button)
        return button

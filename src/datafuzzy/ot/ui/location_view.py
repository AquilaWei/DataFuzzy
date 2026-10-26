"""The by-location page: the students seen at one place; click one to see all of their
records, at every place, newest first."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..db import RecordStore
from .cards import date_label, preview_text, time_label
from .date_view import NAME_ROLE, PLACE_ROLE, PREVIEW_ROLE, TIME_ROLE, DayRecordDelegate
from .i18n import tr
from .widgets import record_menu

NO_LOCATION = "未填地點"


class LocationRecordsView(QWidget):
    """First a list of student names (most recently seen first). A student's records, from
    every location, look like the day list's rows with the date in bold where the name would be."""

    open_record = Signal(int)  # record id
    delete_record = Signal(int)  # record id chosen from a row's right-click menu

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.location: str | None = None
        self.student_id: int | None = None  # the student whose records are shown, if any
        self.back_btn = QPushButton(tr("‹ 學生"))
        self.back_btn.setObjectName("flat")
        self.back_btn.setToolTip(tr("回到這個地點的學生清單"))
        self.back_btn.clicked.connect(lambda: self.show_student(None))
        self.title = QLabel("")
        self.title.setObjectName("title")
        self.count = QLabel("")
        self.count.setObjectName("subtle")
        self.students = QListWidget()
        self.students.setSpacing(2)
        self.list = QListWidget()
        self.list.setSpacing(4)
        self.list.setItemDelegate(DayRecordDelegate(self.list))
        self.pages = QStackedWidget()
        self.pages.addWidget(self.students)
        self.pages.addWidget(self.list)
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        title_row.addWidget(self.back_btn)
        title_row.addWidget(self.title)
        title_row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(0)
        layout.addLayout(title_row)
        layout.addWidget(self.count)
        layout.addSpacing(10)
        layout.addWidget(self.pages, 1)
        self.students.itemClicked.connect(
            lambda item: self.show_student(item.data(Qt.ItemDataRole.UserRole)))
        self.list.itemClicked.connect(lambda item: self.open_record.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)

    def context_menu(self, pos: QPoint) -> QMenu | None:
        """The menu for the row at `pos` (list viewport coordinates), None off the rows."""
        item = self.list.itemAt(pos)
        if item is None:
            return None
        record_id = item.data(Qt.ItemDataRole.UserRole)
        return record_menu(self, lambda: self.delete_record.emit(record_id))

    def _show_menu(self, pos: QPoint) -> None:
        if menu := self.context_menu(pos):
            menu.exec(self.list.viewport().mapToGlobal(pos))

    def show_location(self, location: str | None) -> None:
        """`location` "" means the records without one; None shows nothing. A new location
        starts at its student list; the same one keeps the student being looked at."""
        if location != self.location:
            self.student_id = None
        self.location = location
        self.refresh()

    def show_student(self, student_id: int | None) -> None:
        """Show that student's records at this location, or the student list for None."""
        self.student_id = student_id
        self.refresh()

    def refresh(self) -> None:
        self.students.clear()
        self.list.clear()
        if self.location is None:
            self.title.setText("")
            self.count.setText("")
            self.back_btn.hide()
            return
        names = {s.id: s.name for s in self.store.students()}
        seen = self.store.students_at(self.location)
        if self.student_id not in seen:
            self.student_id = None  # deleted, or no longer seen here
        place = self.location or tr(NO_LOCATION)
        self.back_btn.setVisible(self.student_id is not None)
        if self.student_id is None:
            self.pages.setCurrentWidget(self.students)
            self.title.setText(place)
            self.count.setText(tr("{count} 位學生", count=len(seen)))
            for student_id in seen:
                item = QListWidgetItem(names[student_id])
                item.setData(Qt.ItemDataRole.UserRole, student_id)
                self.students.addItem(item)
            return
        self.pages.setCurrentWidget(self.list)
        records = self.store.records_for_student(self.student_id)
        self.title.setText(names[self.student_id])
        self.count.setText(tr("{count} 份病歷（所有地點）", count=len(records)))
        for record in records:
            first_line = preview_text(record.zh_text, record.en_text).splitlines()[0]
            item = QListWidgetItem(f"{record.visit_date.isoformat()}\n{record.location} · {first_line}")
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setData(NAME_ROLE, date_label(record.visit_date))
            item.setData(PLACE_ROLE, record.location or tr(NO_LOCATION))
            item.setData(PREVIEW_ROLE, first_line)
            item.setData(TIME_ROLE, (time_label(record.start_time), time_label(record.end_time)))
            self.list.addItem(item)

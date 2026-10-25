"""The by-location page: every record made at one place, newest first."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QWidget

from ..db import RecordStore
from .cards import date_label, preview_text
from .date_view import NAME_ROLE, PLACE_ROLE, PREVIEW_ROLE, TIME_ROLE, DayRecordDelegate
from .widgets import record_menu

NO_LOCATION = "未填地點"


class LocationRecordsView(QWidget):
    """Rows look like the day list's, with the date in the tag where the location would be."""

    open_record = Signal(int)  # record id
    delete_record = Signal(int)  # record id chosen from a row's right-click menu

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.location: str | None = None
        self.title = QLabel("")
        self.title.setObjectName("title")
        self.count = QLabel("")
        self.count.setObjectName("subtle")
        self.list = QListWidget()
        self.list.setSpacing(4)
        self.list.setItemDelegate(DayRecordDelegate(self.list))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(0)
        layout.addWidget(self.title)
        layout.addWidget(self.count)
        layout.addSpacing(10)
        layout.addWidget(self.list, 1)
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
        """`location` "" means the records without one; None shows nothing."""
        self.location = location
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        if self.location is None:
            self.title.setText("")
            self.count.setText("")
            return
        records = self.store.records_at(self.location)
        names = {s.id: s.name for s in self.store.students()}
        self.title.setText(self.location or NO_LOCATION)
        self.count.setText(f"{len(records)} 份病歷 · {len({r.student_id for r in records})} 位學生")
        for record in records:
            first_line = preview_text(record.zh_text, record.en_text).splitlines()[0]
            item = QListWidgetItem(f"{names[record.student_id]}\n{record.visit_date.isoformat()} · {first_line}")
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setData(NAME_ROLE, names[record.student_id])
            item.setData(PLACE_ROLE, date_label(record.visit_date))
            item.setData(PREVIEW_ROLE, first_line)
            item.setData(TIME_ROLE, record.start_time)
            self.list.addItem(item)

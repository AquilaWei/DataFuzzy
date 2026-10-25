"""The by-date page: a calendar that marks days with records, and who was seen on a day."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db import RecordStore
from .cards import date_label, preview_text
from .theme import ACCENT


def to_qdate(day: date) -> QDate:
    return QDate(day.year, day.month, day.day)


def to_date(day: QDate) -> date:
    return date(day.year(), day.month(), day.day())


class MarkedCalendar(QCalendarWidget):
    """A month calendar where days that have records are bold, tinted and accent-coloured."""

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setGridVisible(False)
        self.currentPageChanged.connect(lambda *_: self.refresh_markers())
        self.refresh_markers()

    def refresh_markers(self) -> None:
        """Re-read which days of the shown month (and the neighbouring days the grid also
        shows) have records. Call after records are added."""
        first = date(self.yearShown(), self.monthShown(), 1)
        last = (first + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        marked = self.store.dates_with_records(first - timedelta(days=7), last + timedelta(days=7))
        self.setDateTextFormat(QDate(), QTextCharFormat())  # an invalid date clears every format
        tint = QColor(ACCENT)
        tint.setAlpha(45)
        for day in marked:
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            fmt.setForeground(QColor(ACCENT))
            fmt.setBackground(tint)
            self.setDateTextFormat(to_qdate(day), fmt)

    def marked_dates(self) -> set[date]:
        return {to_date(d) for d, fmt in self.dateTextFormat().items()
                if fmt.fontWeight() == QFont.Weight.Bold}

    def selected(self) -> date:
        return to_date(self.selectedDate())


class DayRecordsView(QWidget):
    """The children with a record on one day; clicking one opens the record."""

    open_record = Signal(int)  # record id

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.day: date | None = None
        self.title = QLabel("")
        self.title.setObjectName("title")
        self.count = QLabel("")
        self.count.setObjectName("subtle")
        self.empty = QLabel("這天沒有病歷。")
        self.empty.setObjectName("subtle")
        self.list = QListWidget()
        self.list.setSpacing(4)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(0)
        layout.addWidget(self.title)
        layout.addWidget(self.count)
        layout.addSpacing(10)
        layout.addWidget(self.empty)
        layout.addWidget(self.list, 1)
        self.list.itemClicked.connect(lambda item: self.open_record.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.empty.setVisible(False)

    def show_day(self, day: date) -> None:
        self.day = day
        self.refresh()

    def refresh(self) -> None:
        if self.day is None:
            return
        names = {s.id: s.name for s in self.store.students_on(self.day)}  # sorted by name
        order = {student_id: i for i, student_id in enumerate(names)}
        records = sorted(self.store.records_on(self.day), key=lambda r: order[r.student_id])
        self.title.setText(date_label(self.day))
        self.count.setText(f"{len(records)} 位學生有病歷")
        self.list.clear()
        for record in records:
            place = record.location or "未填地點"
            first_line = preview_text(record.zh_text, record.en_text).splitlines()[0]
            item = QListWidgetItem(f"{names[record.student_id]}\n{place} · {first_line}")
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            self.list.addItem(item)
        self.empty.setVisible(not records)
        self.list.setVisible(bool(records))

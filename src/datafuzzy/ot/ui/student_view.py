"""The by-student page: one student's records as a stack of folder cards."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..db import RecordStore
from .cards import CardStack
from .widgets import SegmentedControl

NEWEST_FIRST = 0
OLDEST_FIRST = 1


class StudentRecordsView(QWidget):
    open_record = Signal(int)  # record id of the clicked card
    delete_record = Signal(int)  # record id chosen from a card's right-click menu

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.student_id: int | None = None

        self.title = QLabel("")
        self.title.setObjectName("title")
        self.count = QLabel("")
        self.count.setObjectName("subtle")
        self.sort = SegmentedControl(["最新在前", "最舊在前"])
        self.empty = QLabel("這位學生還沒有病歷。按「新增病歷」開始記錄。")
        self.empty.setObjectName("subtle")
        self.stack = CardStack()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.stack)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(self.title)
        titles.addWidget(self.count)
        header.addLayout(titles, 1)
        header.addWidget(self.sort)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.addLayout(header)
        layout.addWidget(self.empty)
        layout.addWidget(self.scroll, 1)

        self.sort.changed.connect(lambda _: self.refresh())
        self.stack.clicked.connect(self.open_record)
        self.stack.delete_requested.connect(self.delete_record)
        self.refresh()

    def show_student(self, student_id: int | None) -> None:
        self.student_id = student_id
        self.refresh()

    def refresh(self) -> None:
        """Reload the cards from the database, e.g. after an edit or an import."""
        if self.student_id is None:
            self.title.setText("")
            self.count.setText("")
            self.stack.set_records([])
            self.empty.setVisible(False)
            return
        records = self.store.records_for_student(self.student_id, newest_first=self.sort.index() == NEWEST_FIRST)
        self.title.setText(self.store.get_student(self.student_id).name)
        self.count.setText(f"{len(records)} 份病歷")
        self.stack.set_records(records)
        self.empty.setVisible(not records)

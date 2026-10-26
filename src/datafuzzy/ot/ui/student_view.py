"""The by-student page: one student's records as a stack of folder cards."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..db import RecordStore
from .cards import CardStack
from .i18n import tr
from .widgets import SegmentedControl

NEWEST_FIRST = 0
OLDEST_FIRST = 1


class StudentRecordsView(QWidget):
    open_record = Signal(int)  # record id of the clicked card
    delete_record = Signal(int)  # record id chosen from a card's right-click menu
    rename_student = Signal(int)  # student id, from the pencil next to the name
    edit_profile = Signal(int)  # student id, from the 基本資訊 button next to the name

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.student_id: int | None = None

        self.title = QLabel("")
        self.title.setObjectName("title")
        self.rename_btn = QPushButton("✎")
        self.rename_btn.setObjectName("flat")
        self.rename_btn.setToolTip(tr("修改姓名"))
        self.profile_btn = QPushButton(tr("基本資訊"))
        self.profile_btn.setToolTip(tr("Diagnosis、Grade、Goals 等，Excel 匯出時填入表頭"))
        self.count = QLabel("")
        self.count.setObjectName("subtle")
        self.sort = SegmentedControl([tr("最新在前"), tr("最舊在前")])
        self.empty = QLabel(tr("這位學生還沒有病歷。按「新增病歷」開始記錄。"))
        self.empty.setObjectName("subtle")
        self.stack = CardStack()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.stack)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        name_row = QHBoxLayout()
        name_row.setSpacing(4)
        name_row.addWidget(self.title)
        name_row.addWidget(self.rename_btn)
        name_row.addWidget(self.profile_btn)
        name_row.addStretch(1)
        titles.addLayout(name_row)
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
        self.rename_btn.clicked.connect(lambda: self.rename_student.emit(self.student_id))
        self.profile_btn.clicked.connect(lambda: self.edit_profile.emit(self.student_id))
        self.refresh()

    def show_student(self, student_id: int | None) -> None:
        self.student_id = student_id
        self.refresh()

    def refresh(self) -> None:
        """Reload the cards from the database, e.g. after an edit or an import."""
        if self.student_id is None:
            self.title.setText("")
            self.count.setText("")
            self.rename_btn.setVisible(False)
            self.profile_btn.setVisible(False)
            self.stack.set_records([])
            self.empty.setVisible(False)
            return
        records = self.store.records_for_student(self.student_id, newest_first=self.sort.index() == NEWEST_FIRST)
        self.title.setText(self.store.get_student(self.student_id).name)
        self.rename_btn.setVisible(True)
        self.profile_btn.setVisible(True)
        self.count.setText(tr("{count} 份病歷", count=len(records)))
        self.stack.set_records(records)
        self.empty.setVisible(not records)

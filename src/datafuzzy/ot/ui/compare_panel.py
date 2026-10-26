"""A second chart of the same student, read-only beside the one being edited."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..db import Record
from .cards import date_label, preview_text, session_label


def compare_candidates(records: list[Record], current_id: int, current_day: date) -> list[Record]:
    """The student's other charts in the order to offer them: the visits before `current_day`
    from the nearest back to the oldest, then any later ones from the nearest on."""
    others = [r for r in records if r.id != current_id]
    earlier = sorted((r for r in others if r.visit_date < current_day),
                     key=lambda r: (r.visit_date, r.id), reverse=True)
    later = sorted((r for r in others if r.visit_date >= current_day), key=lambda r: (r.visit_date, r.id))
    return earlier + later


def candidate_label(record: Record) -> str:
    """One line of the pick list: date, location and the start of the chart."""
    first_line = preview_text(record.zh_text, record.en_text).splitlines()[0]
    return f"{date_label(record.visit_date)} · {record.location or '未填地點'} · {first_line}"


class ComparePanel(QWidget):
    closed = Signal()

    def __init__(self, record: Record, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record_id = record.id
        when = date_label(record.visit_date)
        if record.start_time:
            when += f"  {session_label(record.start_time, record.end_time)}"
        self.title = QLabel(when)
        self.title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.location = QLabel(record.location or "未填地點")
        self.location.setObjectName("subtle")
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("flat")
        self.close_btn.setToolTip("關閉對照")
        self.activity = self._read_only(record.activity, "（沒有記錄活動）")
        self.activity.setMaximumHeight(self.activity.fontMetrics().lineSpacing() * 4 + 16)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._read_only(record.zh_text, "（沒有中文病歷）"), "中文")
        self.tabs.addTab(self._read_only(record.en_text, "（沒有英文病歷）"), "English")

        head = QHBoxLayout()
        head.addWidget(QLabel("對照"))
        head.addWidget(self.title, 1)
        head.addWidget(self.close_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addWidget(self.location)
        layout.addWidget(QLabel("活動"))
        layout.addWidget(self.activity)
        layout.addWidget(self.tabs, 1)
        self.close_btn.clicked.connect(self.closed)

    @staticmethod
    def _read_only(text: str, placeholder: str) -> QPlainTextEdit:
        edit = QPlainTextEdit(text)
        edit.setReadOnly(True)
        edit.setPlaceholderText(placeholder)
        return edit

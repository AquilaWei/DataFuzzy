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
from .cards import date_label, preview_text, time_label
from .i18n import language, tr
from .widgets import GrowingTextEdit


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
    return f"{date_label(record.visit_date)} · {record.location or tr('未填地點')} · {first_line}"


class ComparePanel(QWidget):
    closed = Signal()

    def __init__(self, record: Record, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record_id = record.id
        # Laid out row for row like the editor's chart, which then matches the row heights.
        self.title = QLabel(date_label(record.visit_date))
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.location = QLabel(tr("地點：{place}", place=record.location or tr("未填")))
        self.location.setObjectName("subtle")
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("flat")
        self.close_btn.setToolTip(tr("關閉對照"))
        self.start = QLabel(time_label(record.start_time) or "—")
        self.end = QLabel(time_label(record.end_time) or "—")
        self.activity = GrowingTextEdit(record.activity)
        self.activity.setReadOnly(True)
        self.activity.setPlaceholderText(tr("（沒有記錄活動）"))
        self.tabs = QTabWidget()
        self.tabs.addTab(self._read_only(record.zh_text, tr("（沒有中文病歷）")), tr("中文"))
        self.tabs.addTab(self._read_only(record.en_text, tr("（沒有英文病歷）")), "English")
        self.tabs.setCurrentIndex(1 if language() == "en" else 0)  # as in the editor
        self.tabs.setMinimumHeight(280)  # the editor's CHART_MIN_HEIGHT

        self.heading_row = QWidget()
        heading = QHBoxLayout(self.heading_row)
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(4)
        tag = QLabel(tr("對照"))
        tag.setObjectName("subtle")
        heading.addWidget(tag)
        heading.addSpacing(4)
        heading.addWidget(self.title)
        heading.addSpacing(8)
        heading.addWidget(self.location)
        heading.addStretch(1)
        heading.addWidget(self.close_btn)
        self.times_row = QWidget()
        times = QHBoxLayout(self.times_row)
        times.setContentsMargins(0, 0, 0, 0)
        times.addWidget(QLabel(tr("開始時間")))
        times.addWidget(self.start)
        times.addSpacing(12)
        times.addWidget(QLabel(tr("結束時間")))
        times.addWidget(self.end)
        times.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)  # the editor's chart spacing
        layout.addWidget(self.heading_row)
        layout.addWidget(self.times_row)
        layout.addWidget(QLabel(tr("活動")))
        layout.addWidget(self.activity)
        layout.addWidget(self.tabs, 1)
        self.close_btn.clicked.connect(self.closed)

    @staticmethod
    def _read_only(text: str, placeholder: str) -> QPlainTextEdit:
        edit = QPlainTextEdit(text)
        edit.setReadOnly(True)
        edit.setPlaceholderText(placeholder)
        return edit

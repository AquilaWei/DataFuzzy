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

from ..db import Record, session_label
from .cards import date_label, preview_text, time_label
from .i18n import language, tr
from .session_fields import GoalScores, shown_parts
from .widgets import GrowingTextEdit


def _session(record: Record) -> tuple[date, str, int]:
    """Where a record falls among the student's sessions: by day, then start time."""
    return record.visit_date, record.start_time or "99:99", record.id


def compare_candidates(records: list[Record], current: Record) -> list[Record]:
    """The student's other charts in the order to offer them: the sessions before `current`
    (an earlier one the same day included) from the nearest back to the oldest, then any later
    ones from the nearest on."""
    others = [r for r in records if r.id != current.id]
    earlier = sorted((r for r in others if _session(r) < _session(current)), key=_session, reverse=True)
    later = sorted((r for r in others if _session(r) > _session(current)), key=_session)
    return earlier + later


def candidate_label(record: Record) -> str:
    """One line of the pick list: date, start time, location and the start of the chart."""
    first_line = preview_text(record).splitlines()[0]
    when = " ".join(part for part in (date_label(record.visit_date), time_label(record.start_time)) if part)
    return f"{when} · {record.location or tr('未填地點')} · {first_line}"


class ComparePanel(QWidget):
    closed = Signal()

    def __init__(self, record: Record, goals: tuple[str, ...] = (), parent: QWidget | None = None) -> None:
        """`goals` are those of the plan in effect on the record's day, for naming its scores."""
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
        parts = shown_parts(record)  # as the editor would show this chart
        self.text_boxes: dict[str, QPlainTextEdit] = {}  # by Record field, e.g. "zh_text"
        self.tabs = QTabWidget()
        self.tabs.addTab(self._chart_page(record, "zh", parts, tr("（沒有中文記錄）"), tr("（沒有中文追蹤）")), tr("中文"))
        self.tabs.addTab(self._chart_page(record, "en", parts, tr("（沒有英文記錄）"), tr("（沒有英文追蹤）")), "English")
        self.tabs.setVisible(bool(parts & {"comments", "followup"}))
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
        self.type_row = QWidget()
        type_line = QHBoxLayout(self.type_row)
        type_line.setContentsMargins(0, 0, 0, 0)
        type_line.addWidget(QLabel("Session type"))
        self.session_type = QLabel(session_label(record.session_mode, record.session_type))
        type_line.addWidget(self.session_type, 1)
        self.scores_row = QWidget()
        scores = QVBoxLayout(self.scores_row)
        scores.setContentsMargins(0, 0, 0, 0)
        scores.addWidget(QLabel(tr("目標表現")))
        self.scores = GoalScores(goals, record.goal_scores, read_only=True)
        scores.addWidget(self.scores)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)  # the editor's chart spacing
        layout.addWidget(self.heading_row)
        layout.addWidget(self.times_row)
        layout.addWidget(self.type_row)
        layout.addWidget(self.scores_row)
        activity_label = QLabel(tr("活動"))
        layout.addWidget(activity_label)
        layout.addWidget(self.activity)
        self.scores_row.setVisible("scores" in parts)
        activity_label.setVisible("activity" in parts)
        self.activity.setVisible("activity" in parts)
        layout.addWidget(self.tabs, 1)
        if "deficit" in parts:
            layout.addWidget(QLabel(f"Underlying deficit: {record.deficit}"))
        self.close_btn.clicked.connect(self.closed)

    def _chart_page(self, record: Record, lang: str, parts: set[str],
                    no_comments: str, no_followup: str) -> QWidget:
        """One language's tab: the comments above the follow-up, each only if shown."""
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(8, 8, 8, 8)
        for part, field, label, placeholder, stretch in (
                ("comments", f"{lang}_text", tr("記錄"), no_comments, 3),
                ("followup", f"{lang}_followup", tr("追蹤"), no_followup, 1)):
            if part in parts:
                box = self.text_boxes[field] = self._read_only(getattr(record, field), placeholder)
                column.addWidget(QLabel(label))
                column.addWidget(box, stretch)
        return page

    @staticmethod
    def _read_only(text: str, placeholder: str) -> QPlainTextEdit:
        edit = QPlainTextEdit(text)
        edit.setReadOnly(True)
        edit.setPlaceholderText(placeholder)
        return edit

"""What the school form asks of each visit besides the chart: the session type and how the
student did on each of their goals. Editable in the chart editor, read-only beside it."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QWidget,
)

from ..db import DEFAULT_SESSION_TYPE, SESSION_TYPES
from ..excel_export import NO_SCORE
from .i18n import tr

SCORES = ("met", "not met", "not addressed")  # the choices the form takes for a goal
SCORE_WIDTH = 13  # characters the score box shows, "not addressed" in full


def session_type_label(session_type: str) -> str:
    """"Make up" for "make up": the form's words, capitalised as a choice."""
    return session_type[:1].upper() + session_type[1:]


class SessionTypePicker(QWidget):
    """One of SESSION_TYPES, picked with radio buttons."""

    changed = Signal()  # a different type was picked by hand

    def __init__(self, session_type: str = DEFAULT_SESSION_TYPE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        for i, name in enumerate(SESSION_TYPES):
            button = QRadioButton(session_type_label(name))
            self._group.addButton(button, i)
            row.addWidget(button)
        row.addStretch(1)
        self._group.button(SESSION_TYPES.index(session_type)).setChecked(True)
        self._group.idToggled.connect(lambda _, on: self.changed.emit() if on else None)

    def value(self) -> str:
        return SESSION_TYPES[self._group.checkedId()]

    def button(self, session_type: str) -> QRadioButton:
        return self._group.button(SESSION_TYPES.index(session_type))


class GoalScores(QWidget):
    """A score for each of the student's goals, a row each: "Goal 1", the score (one of SCORES,
    or blank for not recorded) and the goal itself. `read_only` shows the scores as
    text, for the chart shown beside the one being edited."""

    changed = Signal()  # a score was edited by hand

    def __init__(self, goals: tuple[str, ...] = (), scores: tuple[str, ...] = (),
                 read_only: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.read_only = read_only
        self.boxes: list[QComboBox | QLabel] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(4)
        self._grid.setColumnStretch(2, 1)
        self.set_goals(goals, scores)

    def set_goals(self, goals: tuple[str, ...], scores: tuple[str, ...] | None = None) -> None:
        """Show a row per goal, e.g. after the profile's goals changed; the scores typed so far
        stay with their goal number unless `scores` are given."""
        scores = self.scores() if scores is None else scores
        while self._grid.count():
            widget = self._grid.takeAt(0).widget()
            widget.setParent(None)  # off the screen now, not when deleteLater runs
            widget.deleteLater()
        self.boxes = []
        if not goals:
            empty = QLabel(tr("（基本資料還沒有目標）"))
            empty.setObjectName("subtle")
            self._grid.addWidget(empty, 0, 0, 1, 3)
        for i, goal in enumerate(goals):
            score = scores[i] if i < len(scores) else ""
            box = self._score_label(score) if self.read_only else self._score_box(score)
            text = QLabel(goal)
            text.setObjectName("subtle")
            text.setWordWrap(True)
            self._grid.addWidget(QLabel(f"Goal {i + 1}"), i, 0, Qt.AlignmentFlag.AlignTop)
            self._grid.addWidget(box, i, 1, Qt.AlignmentFlag.AlignTop)
            self._grid.addWidget(text, i, 2, Qt.AlignmentFlag.AlignTop)
            self.boxes.append(box)

    def _score_box(self, score: str) -> QComboBox:
        box = QComboBox()
        box.addItem(NO_SCORE, "")
        for choice in SCORES:
            box.addItem(choice, choice)
        if score and score not in SCORES:  # typed in by hand before the choices, e.g. "75%"
            box.addItem(score, score)
        box.setCurrentIndex(box.findData(score))
        box.setToolTip(tr("-- 表示沒有記錄"))
        box.setMinimumContentsLength(SCORE_WIDTH)
        box.currentIndexChanged.connect(self.changed)
        return box

    @staticmethod
    def _score_label(score: str) -> QLabel:
        label = QLabel(score or NO_SCORE)
        label.setMinimumWidth(label.fontMetrics().averageCharWidth() * SCORE_WIDTH)
        return label

    def scores(self) -> tuple[str, ...]:
        """One per goal, in order, as picked ("" for none)."""
        if self.read_only:
            return tuple("" if b.text() == NO_SCORE else b.text() for b in self.boxes)
        return tuple(box.currentData() for box in self.boxes)

"""What the school form and ACE ask of each visit besides the chart: the session's mode and
service type, the deficit it addressed and how the student did on each of their goals. Editable
in the chart editor, read-only beside it."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ..db import (
    COMMENT_TYPES,
    DEFAULT_SESSION_MODE,
    DEFAULT_SESSION_TYPE,
    DEFICITS,
    DIRECT_THERAPY,
    FULL_TYPES,
    SESSION_MODES,
    Record,
    types_for,
)
from ..excel_export import NO_SCORE
from .i18n import tr
from .widgets import SegmentedControl

SCORES = ("met", "not met", "not addressed")  # the choices the form takes for a goal
SCORE_WIDTH = 13  # characters the score box shows, "not addressed" in full
MODE_LABELS = ("Individual", "Group")  # SESSION_MODES as shown


def needed_parts(session_type: str) -> set[str]:
    """The parts of the chart below the times that a service type asks for, out of "scores",
    "activity", "comments", "followup" and "deficit" (see FULL_TYPES, COMMENT_TYPES)."""
    if session_type in FULL_TYPES:
        return {"scores", "activity", "comments", "followup", "deficit"}
    if session_type in COMMENT_TYPES:
        return {"comments"}
    return set()


def shown_parts(record: Record) -> set[str]:
    """The parts to show for `record`: those its service type asks for, and any other that has
    something in it (a chart from before the types, say), so nothing written is hidden."""
    filled = {"scores": any(record.goal_scores), "activity": bool(record.activity.strip()),
              "comments": bool(record.zh_text.strip() or record.en_text.strip()),
              "followup": bool(record.zh_followup.strip() or record.en_followup.strip())}
    return needed_parts(record.session_type) | {part for part, has in filled.items() if has}


class SessionPicker(QWidget):
    """The session's mode (Individual or Group) and its service type, whose choices follow the
    mode (see types_for): a type the new mode does not have falls back to Direct Therapy Time.
    No-Show is offered for a `preschool` student, and kept for a chart that has it even when the
    student is no longer one, so a later grade never changes a chart's type."""

    changed = Signal()  # the mode or the type was changed by hand

    def __init__(self, mode: str = DEFAULT_SESSION_MODE, session_type: str = DEFAULT_SESSION_TYPE,
                 preschool: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preschool = preschool
        self.mode_control = SegmentedControl(list(MODE_LABELS))
        self.mode_control.set_index(SESSION_MODES.index(mode))
        self.type_box = QComboBox()
        self.type_box.setMinimumContentsLength(22)
        self._fill_types(mode, session_type)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.mode_control)
        row.addSpacing(12)
        row.addWidget(self.type_box)
        row.addStretch(1)
        self.mode_control.changed.connect(self._mode_changed)
        self.type_box.currentIndexChanged.connect(self.changed)

    def _fill_types(self, mode: str, session_type: str) -> None:
        choices = list(types_for(mode, self.preschool))
        if session_type not in choices and session_type in types_for(mode, preschool=True):
            choices.append(session_type)  # No-Show of a student no longer in pre-school
        self.type_box.blockSignals(True)  # refilling is not a pick
        self.type_box.clear()
        self.type_box.addItems(choices)
        self.type_box.setCurrentText(session_type if session_type in choices else DIRECT_THERAPY)
        self.type_box.blockSignals(False)

    def _mode_changed(self) -> None:
        self._fill_types(self.mode(), self.session_type())
        self.changed.emit()

    def set_preschool(self, preschool: bool) -> None:
        """Offer No-Show or not, e.g. after the student's grade was edited; the type stays."""
        self.preschool = preschool
        self._fill_types(self.mode(), self.session_type())

    def mode(self) -> str:
        return SESSION_MODES[self.mode_control.index()]

    def session_type(self) -> str:
        return self.type_box.currentText()

    def set_mode(self, mode: str) -> None:
        self.mode_control.set_index(SESSION_MODES.index(mode))

    def set_session_type(self, session_type: str) -> None:
        self.type_box.setCurrentText(session_type)


class DeficitPicker(QComboBox):
    """The underlying deficit a therapy session addressed, one of DEFICITS."""

    def __init__(self, deficit: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.addItems(DEFICITS)
        self.setCurrentText(deficit)


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

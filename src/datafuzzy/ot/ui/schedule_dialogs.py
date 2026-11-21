"""The dialogs for calling sessions off (see schedule.py): a weekday off from the timetable,
what to do with the charts already on that day, and moving or cancelling a day's bookings.
Each only asks; the caller applies the choice."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..db import Record
from ..db import session_label as service_label
from ..schedule import CANCEL_REASONS, POSTPONE_WEEKS, Slot
from .cards import date_label, session_label, weekday_label
from .i18n import tr


class CheckList(QWidget):
    """Rows with a tick box each, all ticked to begin with, each carrying a value; buttons to
    tick or untick them all. The rows are check boxes named "checkRow", which the theme makes
    easy to tell apart ticked or not (see theme.stylesheet)."""

    changed = Signal()  # a row was ticked or unticked

    def __init__(self, rows: Iterable[tuple[str, object]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.boxes: list[QCheckBox] = []
        self.values: list[object] = []
        inner = QWidget()
        column = QVBoxLayout(inner)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        for text, value in rows:
            box = QCheckBox(text)
            box.setObjectName("checkRow")
            box.setChecked(True)
            box.toggled.connect(lambda _: self.changed.emit())
            column.addWidget(box)
            self.boxes.append(box)
            self.values.append(value)
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        self.all_btn = QPushButton(tr("全選"))
        self.none_btn = QPushButton(tr("全不選"))
        self.all_btn.clicked.connect(lambda: self.set_all(True))
        self.none_btn.clicked.connect(lambda: self.set_all(False))
        actions = QHBoxLayout()
        actions.addWidget(self.all_btn)
        actions.addWidget(self.none_btn)
        actions.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(actions)
        layout.addWidget(scroll, 1)

    def set_all(self, ticked: bool) -> None:
        for box in self.boxes:
            box.setChecked(ticked)

    def checked(self) -> list:
        """The values of the ticked rows, in order."""
        return [value for box, value in zip(self.boxes, self.values) if box.isChecked()]


def slot_text(name: str, start: str, end: str) -> str:
    """"王小明 · 9:30 AM–10:00 AM", or just the name for a session without times."""
    return f"{name} · {session_label(start, end)}" if start else name


def record_text(record: Record, name: str) -> str:
    """A booking as a row: who, when, and what it is booked as."""
    return f"{slot_text(name, record.start_time, record.end_time)} · " \
           f"{service_label(record.session_mode, record.session_type)}"


def weeks_box() -> QComboBox:
    box = QComboBox()
    for weeks in POSTPONE_WEEKS:
        box.addItem(tr("{weeks} 週後", weeks=weeks), weeks)
    return box


class _ChoiceDialog(QDialog):
    """A dialog ending in a tick list and OK / Cancel. Unless told otherwise, OK works only
    while at least one row is ticked: with none there is nothing to do."""

    def _finish(self, layout: QVBoxLayout, rows: CheckList, ok_text: str, need_one: bool = True) -> None:
        self.rows = rows
        buttons = QDialogButtonBox()
        self.ok_button: QPushButton = buttons.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(tr("返回"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(rows, 1)
        layout.addWidget(buttons)
        if need_one:
            rows.changed.connect(lambda: self.ok_button.setEnabled(bool(rows.checked())))
            self.ok_button.setEnabled(bool(rows.checked()))


class DayOffDialog(_ChoiceDialog):
    """A weekday off: which of the coming such days, and whose sessions. The rows are the
    weekday's sessions in the timetable, all ticked."""

    def __init__(self, reason: str, weekday: int, dates: list[date], slots: list[tuple[str, Slot]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{reason} · {weekday_label(weekday)}")
        self.resize(460, 480)
        self.day = QComboBox()
        for day in dates:
            self.day.addItem(date_label(day), day)
        form = QFormLayout()
        form.addRow(tr("日期"), self.day)
        intro = QLabel(tr("勾選的學生會在這一天新增「{reason}」的病歷。", reason=reason))
        intro.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(intro)
        self._finish(layout, CheckList((slot_text(name, s.start, s.end), s) for name, s in slots), tr("新增病歷"))

    def choice(self) -> tuple[date, list[Slot]]:
        return self.day.currentData(), self.rows.checked()


class ClashDialog(_ChoiceDialog):
    """The charts already on a day off, for the user to tick those to move a week on; the rest
    are replaced. Every row starts ticked, so nothing is deleted without a choice."""

    def __init__(self, day: date, records: list[Record], names: dict[int, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("這一天已經有病歷"))
        self.resize(520, 420)
        intro = QLabel(tr("這些學生在 {day} 已經有病歷。勾選的會延到下一週（{next}），"
                          "沒勾選的會被新的病歷取代：原本的病歷會刪除，無法復原。",
                          day=date_label(day), next=date_label(day + timedelta(weeks=1))))
        intro.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        # Ticking none is a choice too: replace them all.
        self._finish(layout, CheckList((record_text(r, names[r.student_id]), r.id) for r in records), tr("繼續"),
                     need_one=False)

    def choice(self) -> list[int]:
        """The ids of the records to move a week on."""
        return self.rows.checked()


class PostponeDialog(_ChoiceDialog):
    """Moving a day's bookings: by how many weeks, and which (all ticked)."""

    def __init__(self, records: list[Record], names: dict[int, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("預約延期"))
        self.resize(520, 420)
        self.weeks = weeks_box()
        form = QFormLayout()
        form.addRow(tr("延到"), self.weeks)
        intro = QLabel(tr("勾選的病歷會整份移到同一個星期幾的那一天。"))
        intro.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(intro)
        self._finish(layout, CheckList((record_text(r, names[r.student_id]), r.id) for r in records), tr("延期"))

    def choice(self) -> tuple[int, list[int]]:
        return self.weeks.currentData(), self.rows.checked()


class CancelDialog(_ChoiceDialog):
    """Cancelling a day's bookings: the reason, whether to move them on first (and by how many
    weeks), and which (all ticked). Unticked ones stay booked as they are."""

    def __init__(self, records: list[Record], names: dict[int, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("預約取消"))
        self.resize(520, 460)
        self.reason = QComboBox()
        for reason in CANCEL_REASONS:
            self.reason.addItem(reason, reason)
        self.move_first = QCheckBox(tr("先把預約延期"))
        self.weeks = weeks_box()
        form = QFormLayout()
        form.addRow(tr("取消原因"), self.reason)
        form.addRow(self.move_first)
        form.addRow(tr("延到"), self.weeks)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        self._finish(layout, CheckList((record_text(r, names[r.student_id]), r.id) for r in records), tr("取消預約"))
        self.move_first.toggled.connect(self._moved_first)
        self._moved_first(False)

    def _moved_first(self, on: bool) -> None:
        self.weeks.setEnabled(on)
        self.hint.setText(tr("勾選的預約會移到之後的那一天，原本這天改成取消原因的病歷。") if on else
                          tr("勾選的預約會被取消原因的病歷取代：原本的病歷會刪除，無法復原。沒勾選的照舊。"))

    def choice(self) -> tuple[str, int | None, list[int]]:
        """(reason, weeks to move on or None to replace, record ids)."""
        weeks = self.weeks.currentData() if self.move_first.isChecked() else None
        return self.reason.currentData(), weeks, self.rows.checked()

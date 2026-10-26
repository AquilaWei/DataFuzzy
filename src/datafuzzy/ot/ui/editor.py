"""Editor for one student's chart on one day: location, activities, Chinese and English text."""

from __future__ import annotations

import re
from datetime import date, datetime

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..db import DuplicateRecord, RecordStore, default_end_time
from .cards import time_label
from .compare_panel import ComparePanel, candidate_label, compare_candidates
from .date_view import to_date, to_qdate

AUTOSAVE_MS = 800
TIME_CHOICES = [time_label(f"{h:02d}:{m:02d}") for h in range(7, 20) for m in (0, 15, 30, 45)]
_TIME = re.compile(r"(\d{1,2}):([0-5]\d)\s*([AaPp])?\.?\s*[Mm]?\.?")


def normal_time(text: str) -> str | None:
    """`text` ("9:30 AM", "2:05pm", or 24-hour "14:05") as "HH:MM" ("" for blank), or None
    if it is not a time."""
    text = text.strip().replace("：", ":")
    if not text:
        return ""
    match = _TIME.fullmatch(text)
    if not match:
        return None
    hour, minute, half = int(match[1]), match[2], (match[3] or "").upper()
    if half:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if half == "P" else 0)
    elif hour > 23:
        return None
    return f"{hour:02d}:{minute}"


ACTIVITY_LINES = 3  # height of the activity box, in lines


class RecordEditor(QWidget):
    """Changes are saved on their own shortly after the last keystroke, and immediately by
    `flush()`: the window calls it before switching away or quitting, so nothing typed is lost.
    Only the fields that changed are written."""

    closed = Signal()    # the back button was pressed, after everything was saved
    saved = Signal(int)  # a record id, after a write; views showing it can refresh

    def __init__(self, store: RecordStore, record_id: int, debounce_ms: int = AUTOSAVE_MS,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        record = store.get_record(record_id)
        student = store.get_student(record.student_id)
        self.record_id = record_id
        self.student_id = record.student_id
        self.student_name = student.name
        self.compare: ComparePanel | None = None
        self.visit_date = record.visit_date
        self._dirty: set[str] = set()

        self.back_btn = QPushButton("‹ 返回")
        self.back_btn.setObjectName("flat")
        self.title = QLabel("")
        self.title.setObjectName("title")
        self.date_btn = QPushButton("✎")
        self.date_btn.setObjectName("flat")
        self.date_btn.setToolTip("修改日期")
        self._show_title()
        self.compare_btn = QPushButton("對照其他病歷")
        self.compare_btn.setToolTip("在右邊並排顯示這位學生的另一份病歷")
        self.status = QLabel("")
        self.status.setObjectName("subtle")

        self.location_box = QComboBox()
        self.location_box.setObjectName("place")
        self.location_box.setEditable(True)
        self.location_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)  # Enter must not add a row
        self.location_box.lineEdit().setPlaceholderText("地點（例如學校、診所）")
        self.location_box.addItems(store.all_locations())
        self.location_box.setEditText(record.location)

        self.time_box = QComboBox()
        self.time_box.setObjectName("time")  # the stylesheet gives it a clock icon
        self.time_box.setEditable(True)
        self.time_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.time_box.lineEdit().setPlaceholderText("例如 9:30 AM")
        self.time_box.addItems(TIME_CHOICES)
        self.time_box.setEditText(time_label(record.start_time))
        self.time_box.setMinimumContentsLength(8)
        self.end_box = QComboBox()
        self.end_box.setObjectName("time")
        self.end_box.setEditable(True)
        self.end_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.end_box.lineEdit().setPlaceholderText("例如 10:00 AM")
        self.end_box.addItems(TIME_CHOICES)
        self.end_box.setEditText(time_label(record.end_time))
        self.end_box.setMinimumContentsLength(8)
        # The end keeps to SESSION_MINUTES after the start until it is set by hand.
        self._end_follows = not record.end_time or record.end_time == default_end_time(record.start_time)

        self.activity_edit = QPlainTextEdit(record.activity)
        self.activity_edit.setPlaceholderText("今天的治療活動與手段（只留在本機，不會匯出）")
        lines = self.activity_edit.fontMetrics().lineSpacing() * ACTIVITY_LINES
        self.activity_edit.setFixedHeight(lines + 2 * self.activity_edit.frameWidth() + 12)

        self.zh_edit = QPlainTextEdit(record.zh_text)
        self.zh_edit.setPlaceholderText("中文病歷（可中英夾雜）")
        self.en_edit = QPlainTextEdit(record.en_text)
        self.en_edit.setPlaceholderText("English version (only the latest is kept)")
        self.tabs = QTabWidget()
        self.tabs.addTab(self.zh_edit, "中文")
        self.tabs.addTab(self.en_edit, "English")
        self.tabs.setToolTip("點兩下「中文」或「English」複製整份病歷")

        top = QHBoxLayout()
        top.addWidget(self.back_btn)
        top.addStretch(1)
        top.addWidget(self.status)
        top.addWidget(self.compare_btn)
        place = QHBoxLayout()
        place.addWidget(QLabel("地點"))
        place.addWidget(self.location_box, 1)
        place.addSpacing(12)
        place.addWidget(QLabel("開始時間"))
        place.addWidget(self.time_box)
        place.addWidget(QLabel("結束時間"))
        place.addWidget(self.end_box)
        heading = QHBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(self.title)
        heading.addWidget(self.date_btn)
        heading.addStretch(1)
        chart = QWidget()
        body = QVBoxLayout(chart)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addLayout(heading)
        body.addLayout(place)
        body.addWidget(QLabel("活動"))
        body.addWidget(self.activity_edit)
        body.addWidget(self.tabs, 1)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(chart)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 20)
        layout.setSpacing(10)
        layout.addLayout(top)
        layout.addWidget(self.splitter, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.flush)
        # Connected after the texts are filled in, so showing a record is not an edit.
        self.location_box.editTextChanged.connect(lambda: self._changed("location"))
        self.activity_edit.textChanged.connect(lambda: self._changed("activity"))
        self.time_box.editTextChanged.connect(self._start_changed)
        self.end_box.editTextChanged.connect(self._end_changed)
        self.zh_edit.textChanged.connect(lambda: self._changed("zh_text"))
        self.en_edit.textChanged.connect(lambda: self._changed("en_text"))
        self.back_btn.clicked.connect(self.close_editor)
        self.date_btn.clicked.connect(lambda: self.change_date())
        self.tabs.tabBarDoubleClicked.connect(self.copy_tab)
        self.compare_btn.clicked.connect(self._show_compare_menu)

    def compare_menu(self) -> QMenu:
        """The student's other charts, nearest earlier visit first (see compare_candidates)."""
        menu = QMenu(self)
        candidates = compare_candidates(self.store.records_for_student(self.student_id),
                                        self.record_id, self.visit_date)
        if not candidates:
            menu.addAction("這位學生沒有其他病歷").setEnabled(False)
        for record in candidates:
            menu.addAction(candidate_label(record)).triggered.connect(
                lambda _=False, rid=record.id: self.show_compare(rid))
        return menu

    def _show_compare_menu(self) -> None:
        self.compare_menu().exec(self.compare_btn.mapToGlobal(QPoint(0, self.compare_btn.height())))

    def show_compare(self, record_id: int) -> None:
        """Show another chart read-only on the right, in place of any shown before."""
        self.close_compare()
        self.compare = ComparePanel(self.store.get_record(record_id))
        self.compare.closed.connect(self.close_compare)
        self.splitter.addWidget(self.compare)
        half = max(self.splitter.width() // 2, 1)
        self.splitter.setSizes([half, half])

    def close_compare(self) -> None:
        if self.compare is None:
            return
        self.compare.setParent(None)  # out of the splitter now, not when deleteLater runs
        self.compare.deleteLater()
        self.compare = None

    def copy_tab(self, index: int) -> None:
        """Put the whole Chinese (0) or English (1) chart on the clipboard."""
        if index < 0:
            return
        edit = (self.zh_edit, self.en_edit)[index]
        QGuiApplication.clipboard().setText(edit.toPlainText())
        self.status.setText(f"已複製{('中文', '英文')[index]}病歷")

    def _show_title(self) -> None:
        self.title.setText(f"{self.student_name} · {self.visit_date.isoformat()}")

    def _ask_date(self) -> date | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("修改日期")
        edit = QDateEdit(to_qdate(self.visit_date))
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form = QFormLayout(dialog)
        form.addRow("日期", edit)
        form.addRow(buttons)
        return to_date(edit.date()) if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _warn_taken(self, day: date) -> None:
        QMessageBox.warning(self, "修改日期", f"{self.student_name} 在 {day.isoformat()} 已經有一份病歷，"
                            "日期沒有更改。")

    def change_date(self, day: date | None = None) -> bool:
        """Move the record to another day, asking which unless given. Refused (with a
        warning) if the student already has a record that day. Returns whether it moved."""
        day = self._ask_date() if day is None else day
        if day is None or day == self.visit_date:
            return False
        try:
            self.store.move_record(self.record_id, day)
        except DuplicateRecord:
            self._warn_taken(day)
            return False
        self.visit_date = day
        self._show_title()
        self.saved.emit(self.record_id)
        return True

    def _start_changed(self) -> None:
        self._changed("start_time")
        start = normal_time(self.time_box.currentText())
        if self._end_follows and start is not None:
            self.end_box.blockSignals(True)  # not a hand edit: keep following
            self.end_box.setEditText(time_label(default_end_time(start)))
            self.end_box.blockSignals(False)
            self._changed("end_time")

    def _end_changed(self) -> None:
        self._end_follows = False
        self._changed("end_time")

    def _changed(self, field: str) -> None:
        self._dirty.add(field)
        self.status.setText("編輯中…")
        self._timer.start()

    def flush(self) -> None:
        """Write pending changes now. Does nothing when there are none."""
        self._timer.stop()
        if not self._dirty:
            return
        values = {"location": self.location_box.currentText().strip(),
                  "activity": self.activity_edit.toPlainText(),
                  "zh_text": self.zh_edit.toPlainText(),
                  "en_text": self.en_edit.toPlainText(),
                  "start_time": normal_time(self.time_box.currentText()),
                  "end_time": normal_time(self.end_box.currentText())}
        # A half-typed time ("9:") is not saved; the last good one stays until it is complete.
        changed = {field: values[field] for field in self._dirty if values[field] is not None}
        self._dirty.clear()
        if not changed:
            self.status.setText("時間請填成 9:30 AM 這樣的格式")
            return
        self.store.update_record(self.record_id, **changed)
        self.status.setText(f"已儲存 {datetime.now():%H:%M:%S}")
        self.saved.emit(self.record_id)

    def reload(self) -> None:
        """Show what the database holds now, e.g. after an import wrote the English text.
        Pending edits are saved first so they are not replaced."""
        self.flush()
        record = self.store.get_record(self.record_id)
        for edit, text in ((self.zh_edit, record.zh_text), (self.en_edit, record.en_text)):
            if edit.toPlainText() != text:
                edit.setPlainText(text)
        self._dirty.clear()
        self._timer.stop()
        self.status.setText("")

    def close_editor(self) -> None:
        self.flush()
        self.closed.emit()

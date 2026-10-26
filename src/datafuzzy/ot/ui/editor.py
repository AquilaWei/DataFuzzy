"""Editor for one student's chart on one day: location, activities, Chinese and English text."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
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
from .cards import TIME_CHOICES, date_label, normal_time, time_label
from .compare_panel import ComparePanel, candidate_label, compare_candidates
from .date_view import to_date, to_qdate
from .i18n import language, tr
from .profile_dialog import ProfileSummary

AUTOSAVE_MS = 800


ACTIVITY_LINES = 3  # height of the activity box, in lines


class RecordEditor(QWidget):
    """Changes are saved on their own shortly after the last keystroke, and immediately by
    `flush()`: the window calls it before switching away or quitting, so nothing typed is lost.
    Only the fields that changed are written."""

    closed = Signal()    # the back button was pressed, after everything was saved
    saved = Signal(int)  # a record id, after a write; views showing it can refresh
    edit_profile = Signal(int)  # student id, from the profile's edit button

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

        self.back_btn = QPushButton(tr("‹ 返回"))
        self.back_btn.setObjectName("flat")
        self.title = QLabel("")  # this visit's day; the student's name heads the profile above
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.date_btn = QPushButton("✎")
        self.date_btn.setObjectName("flat")
        self.date_btn.setToolTip(tr("修改日期"))
        self._show_title()
        self.compare_btn = QPushButton(tr("對照其他病歷"))
        self.compare_btn.setToolTip(tr("在右邊並排顯示這位學生的另一份病歷"))
        self.status = QLabel("")
        self.status.setObjectName("subtle")

        self.profile = ProfileSummary()
        self.show_profile()
        # The record keeps the place it was seen at; the profile's location is for new ones.
        self.record_place = QLabel(tr("地點：{place}", place=record.location or tr("未填")))
        self.record_place.setObjectName("subtle")

        self.time_box = QComboBox()
        self.time_box.setObjectName("time")  # the stylesheet gives it a clock icon
        self.time_box.setEditable(True)
        self.time_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.time_box.lineEdit().setPlaceholderText(tr("例如 9:30 AM"))
        self.time_box.addItems(TIME_CHOICES)
        self.time_box.setEditText(time_label(record.start_time))
        self.time_box.setMinimumContentsLength(8)
        self.end_box = QComboBox()
        self.end_box.setObjectName("time")
        self.end_box.setEditable(True)
        self.end_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.end_box.lineEdit().setPlaceholderText(tr("例如 10:00 AM"))
        self.end_box.addItems(TIME_CHOICES)
        self.end_box.setEditText(time_label(record.end_time))
        self.end_box.setMinimumContentsLength(8)
        # The end keeps to SESSION_MINUTES after the start until it is set by hand.
        self._end_follows = not record.end_time or record.end_time == default_end_time(record.start_time)

        self.activity_edit = QPlainTextEdit(record.activity)
        self.activity_edit.setPlaceholderText(tr("今天的治療活動與手段（只留在本機，不會匯出）"))
        lines = self.activity_edit.fontMetrics().lineSpacing() * ACTIVITY_LINES
        self.activity_edit.setFixedHeight(lines + 2 * self.activity_edit.frameWidth() + 12)

        self.zh_edit = QPlainTextEdit(record.zh_text)
        self.zh_edit.setPlaceholderText(tr("中文病歷（可中英夾雜）"))
        self.en_edit = QPlainTextEdit(record.en_text)
        self.en_edit.setPlaceholderText("English version (only the latest is kept)")
        self.tabs = QTabWidget()
        self.tabs.addTab(self.zh_edit, tr("中文"))
        self.tabs.addTab(self.en_edit, "English")
        self.tabs.setCurrentIndex(1 if language() == "en" else 0)  # the interface language first
        self.tabs.setToolTip(tr("點兩下「中文」或「English」複製整份病歷"))

        top = QHBoxLayout()
        top.addWidget(self.back_btn)
        top.addStretch(1)
        top.addWidget(self.status)
        top.addWidget(self.compare_btn)
        # Rows are widgets so a comparison beside them can be lined up with them (see show_compare).
        self.heading_row = QWidget()
        heading = QHBoxLayout(self.heading_row)
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(4)
        heading.addWidget(self.title)
        heading.addWidget(self.date_btn)
        heading.addSpacing(8)
        heading.addWidget(self.record_place)
        heading.addStretch(1)
        self.times_row = QWidget()
        times = QHBoxLayout(self.times_row)
        times.setContentsMargins(0, 0, 0, 0)
        times.addWidget(QLabel(tr("開始時間")))
        times.addWidget(self.time_box)
        times.addSpacing(12)
        times.addWidget(QLabel(tr("結束時間")))
        times.addWidget(self.end_box)
        times.addStretch(1)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet("color: palette(mid);")
        chart = QWidget()
        body = QVBoxLayout(chart)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self.heading_row)
        body.addWidget(self.times_row)
        body.addWidget(QLabel(tr("活動")))
        body.addWidget(self.activity_edit)
        body.addWidget(self.tabs, 1)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(chart)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 20)
        layout.setSpacing(10)
        layout.addLayout(top)
        # Who the student is first and across the full width, so it stays on top while comparing.
        layout.addWidget(self.profile)
        layout.addWidget(line)
        layout.addWidget(self.splitter, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.flush)
        # Connected after the texts are filled in, so showing a record is not an edit.
        self.activity_edit.textChanged.connect(lambda: self._changed("activity"))
        self.time_box.editTextChanged.connect(self._start_changed)
        self.end_box.editTextChanged.connect(self._end_changed)
        self.zh_edit.textChanged.connect(lambda: self._changed("zh_text"))
        self.en_edit.textChanged.connect(lambda: self._changed("en_text"))
        self.back_btn.clicked.connect(self.close_editor)
        self.date_btn.clicked.connect(lambda: self.change_date())
        self.tabs.tabBarDoubleClicked.connect(self.copy_tab)
        self.compare_btn.clicked.connect(self._show_compare_menu)
        self.profile.edit_requested.connect(lambda: self.edit_profile.emit(self.student_id))

    def show_profile(self) -> None:
        """Re-read the student's name and profile, e.g. after they were edited."""
        self.student_name = self.store.get_student(self.student_id).name
        profile = self.store.get_profile(self.student_id)
        self.profile.show_profile(self.student_name,
                                  replace(profile, location=self.store.student_location(self.student_id)))

    def compare_menu(self) -> QMenu:
        """The student's other charts, nearest earlier visit first (see compare_candidates)."""
        menu = QMenu(self)
        candidates = compare_candidates(self.store.records_for_student(self.student_id),
                                        self.record_id, self.visit_date)
        if not candidates:
            menu.addAction(tr("這位學生沒有其他病歷")).setEnabled(False)
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
        self._line_up(self.compare)
        half = max(self.splitter.width() // 2, 1)
        self.splitter.setSizes([half, half])

    def _line_up(self, panel: ComparePanel) -> None:
        """Give the comparison's rows the heights of this chart's rows, so the two read across."""
        for mine, theirs in ((self.heading_row, panel.heading_row), (self.times_row, panel.times_row)):
            height = max(mine.sizeHint().height(), theirs.sizeHint().height())
            mine.setFixedHeight(height)
            theirs.setFixedHeight(height)
        panel.activity.setFixedHeight(self.activity_edit.maximumHeight())

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
        self.status.setText(tr(("已複製中文病歷", "已複製英文病歷")[index]))

    def _show_title(self) -> None:
        self.title.setText(date_label(self.visit_date))

    def _ask_date(self) -> date | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("修改日期"))
        edit = QDateEdit(to_qdate(self.visit_date))
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form = QFormLayout(dialog)
        form.addRow(tr("日期"), edit)
        form.addRow(buttons)
        return to_date(edit.date()) if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _warn_taken(self, day: date) -> None:
        QMessageBox.warning(self, tr("修改日期"), tr("{name} 在 {day} 已經有一份病歷，日期沒有更改。",
                                                 name=self.student_name, day=day.isoformat()))

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
        self.status.setText(tr("編輯中…"))
        self._timer.start()

    def flush(self) -> None:
        """Write pending changes now. Does nothing when there are none."""
        self._timer.stop()
        if not self._dirty:
            return
        values = {"activity": self.activity_edit.toPlainText(),
                  "zh_text": self.zh_edit.toPlainText(),
                  "en_text": self.en_edit.toPlainText(),
                  "start_time": normal_time(self.time_box.currentText()),
                  "end_time": normal_time(self.end_box.currentText())}
        # A half-typed time ("9:") is not saved; the last good one stays until it is complete.
        changed = {field: values[field] for field in self._dirty if values[field] is not None}
        self._dirty.clear()
        if not changed:
            self.status.setText(tr("時間請填成 9:30 AM 這樣的格式"))
            return
        self.store.update_record(self.record_id, **changed)
        self.status.setText(tr("已儲存 {time}", time=f"{datetime.now():%H:%M:%S}"))
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

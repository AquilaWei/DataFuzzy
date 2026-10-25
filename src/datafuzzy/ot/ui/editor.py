"""Editor for one student's chart on one day: location, activities, Chinese and English text."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..db import DuplicateRecord, RecordStore
from .date_view import to_date, to_qdate

AUTOSAVE_MS = 800
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
        self.student_name = student.name
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
        self.status = QLabel("")
        self.status.setObjectName("subtle")

        self.location_box = QComboBox()
        self.location_box.setEditable(True)
        self.location_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)  # Enter must not add a row
        self.location_box.lineEdit().setPlaceholderText("地點（例如學校、診所）")
        self.location_box.addItems(store.all_locations())
        self.location_box.setEditText(record.location)

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

        top = QHBoxLayout()
        top.addWidget(self.back_btn)
        top.addStretch(1)
        top.addWidget(self.status)
        place = QHBoxLayout()
        place.addWidget(QLabel("地點"))
        place.addWidget(self.location_box, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 20)
        layout.setSpacing(10)
        layout.addLayout(top)
        heading = QHBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(self.title)
        heading.addWidget(self.date_btn)
        heading.addStretch(1)
        layout.addLayout(heading)
        layout.addLayout(place)
        layout.addWidget(QLabel("活動"))
        layout.addWidget(self.activity_edit)
        layout.addWidget(self.tabs, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.flush)
        # Connected after the texts are filled in, so showing a record is not an edit.
        self.location_box.editTextChanged.connect(lambda: self._changed("location"))
        self.activity_edit.textChanged.connect(lambda: self._changed("activity"))
        self.zh_edit.textChanged.connect(lambda: self._changed("zh_text"))
        self.en_edit.textChanged.connect(lambda: self._changed("en_text"))
        self.back_btn.clicked.connect(self.close_editor)
        self.date_btn.clicked.connect(lambda: self.change_date())

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
                  "en_text": self.en_edit.toPlainText()}
        changed = {field: values[field] for field in self._dirty}
        self._dirty.clear()
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

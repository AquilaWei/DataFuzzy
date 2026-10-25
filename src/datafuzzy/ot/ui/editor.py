"""Editor for one student's chart on one day: location, Chinese text and English text."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..db import RecordStore

AUTOSAVE_MS = 800


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
        self._dirty: set[str] = set()

        self.back_btn = QPushButton("‹ 返回")
        self.back_btn.setObjectName("flat")
        self.title = QLabel(f"{student.name} · {record.visit_date.isoformat()}")
        self.title.setObjectName("title")
        self.status = QLabel("")
        self.status.setObjectName("subtle")

        self.location_box = QComboBox()
        self.location_box.setEditable(True)
        self.location_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)  # Enter must not add a row
        self.location_box.lineEdit().setPlaceholderText("地點（例如學校、診所）")
        self.location_box.addItems(store.all_locations())
        self.location_box.setEditText(record.location)

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
        layout.addWidget(self.title)
        layout.addLayout(place)
        layout.addWidget(self.tabs, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.flush)
        # Connected after the texts are filled in, so showing a record is not an edit.
        self.location_box.editTextChanged.connect(lambda: self._changed("location"))
        self.zh_edit.textChanged.connect(lambda: self._changed("zh_text"))
        self.en_edit.textChanged.connect(lambda: self._changed("en_text"))
        self.back_btn.clicked.connect(self.close_editor)

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

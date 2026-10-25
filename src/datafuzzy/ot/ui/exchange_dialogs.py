"""Dialogs for sending charts out for translation (export) and taking them back (paste)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.pipeline import Pipeline
from ...ui.worker import run_task
from ..db import RecordStore
from ..exchange import (
    ExportResult,
    ImportMismatch,
    ImportPreview,
    apply_import,
    export_range,
    preview_import,
)
from .date_view import to_date, to_qdate

REASONS = {
    "malformed": "標頭格式不正確",
    "not_in_export": "這份匯出沒有這筆病歷",
    "header_changed": "標頭的代號或日期被改過",
    "duplicate": "同一筆出現第二次",
}


class ExportDialog(QDialog):
    """Pick a date range, get the charts with people's names replaced by codes."""

    exported = Signal(object)  # ExportResult

    def __init__(self, store: RecordStore, pipeline: Pipeline, today: date | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.pipeline = pipeline
        self.result: ExportResult | None = None
        self._task = None
        today = today or date.today()
        self.setWindowTitle("匯出病歷")
        self.resize(640, 520)

        self.from_edit = QDateEdit(to_qdate(today - timedelta(days=6)))
        self.to_edit = QDateEdit(to_qdate(today))
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.export_btn = QPushButton("匯出")
        self.export_btn.setObjectName("primary")
        self.status = QLabel("選擇日期範圍後按「匯出」。學生與文中的人名會換成代號。")
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.copy_btn = QPushButton("一鍵複製")
        self.copy_btn.setEnabled(False)

        row = QHBoxLayout()
        row.addWidget(QLabel("從"))
        row.addWidget(self.from_edit)
        row.addWidget(QLabel("到"))
        row.addWidget(self.to_edit)
        row.addStretch(1)
        row.addWidget(self.export_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.status)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.copy_btn)

        self.export_btn.clicked.connect(self.start_export)
        self.copy_btn.clicked.connect(self.copy)

    def start_export(self) -> None:
        date_from, date_to = to_date(self.from_edit.date()), to_date(self.to_edit.date())
        if date_from > date_to:
            self.status.setText("開始日期晚於結束日期。")
            return
        self.export_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.status.setText("匯出中…")
        # Off the GUI thread: the first run loads the detection models.
        self._task = run_task(lambda: export_range(self.store, date_from, date_to, self.pipeline),
                              self._done, self._failed)

    def _done(self, result: ExportResult) -> None:
        self.result = result
        self.export_btn.setEnabled(True)
        self.text.setPlainText(result.text)
        self.copy_btn.setText("一鍵複製")
        self.copy_btn.setEnabled(bool(result.text))
        if not result.record_count:
            self.status.setText("這段期間沒有病歷。")
        else:
            note = f"已匯出 {result.record_count} 份病歷，人名已換成代號。"
            if self.pipeline.pii is None:
                note += "（偵測模型未安裝：只有學生姓名保證被替換，其他人名可能漏掉，請先到「模型管理」下載。）"
            self.status.setText(note)
        self.exported.emit(result)

    def _failed(self, message: str) -> None:
        self.export_btn.setEnabled(True)
        self.status.setText(f"匯出失敗：{message}")

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text.toPlainText())
        self.copy_btn.setText("已複製 ✓")


def ask_overwrite(parent: QWidget | None, count: int) -> bool:
    answer = QMessageBox.question(
        parent, "覆蓋英文版", f"有 {count} 份病歷已有英文版，貼回後會被取代（只保留最新一版）。要覆蓋嗎？")
    return answer == QMessageBox.StandardButton.Yes


class ImportDialog(QDialog):
    """Paste the corrected text back: shows what would be written, asks before overwriting."""

    applied = Signal(int)  # how many records were written

    def __init__(self, store: RecordStore, confirm: Callable[[int], bool] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.preview: ImportPreview | None = None
        self._confirm = confirm or (lambda count: ask_overwrite(self, count))
        self.setWindowTitle("貼回英文版")
        self.resize(640, 600)

        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText("把翻譯／修正後、含「=== REC-… ===」標頭的文字貼在這裡")
        self.preview_btn = QPushButton("檢查")
        self.status = QLabel("")
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)
        self.items = QListWidget()
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.apply_btn = QPushButton("套用")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setEnabled(False)

        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.apply_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.paste, 2)
        layout.addWidget(self.preview_btn)
        layout.addWidget(self.items, 2)
        layout.addWidget(self.notes)
        layout.addLayout(bottom)

        self.preview_btn.clicked.connect(self.run_preview)
        self.apply_btn.clicked.connect(self.apply)
        self.items.itemChanged.connect(lambda _: self._update_apply())

    def run_preview(self) -> None:
        self.items.clear()
        self.notes.setText("")
        self.preview = None
        try:
            preview = preview_import(self.store, self.paste.toPlainText())
        except ImportMismatch as e:
            self.status.setText(f"無法對應到匯出：{e}")
            self._update_apply()
            return
        self.preview = preview
        for item in preview.items:
            warning = "　⚠ 會覆蓋既有英文版" if item.overwrites else ""
            row = QListWidgetItem(f"{item.student_name} · {item.visit_date.isoformat()}{warning}")
            row.setData(Qt.ItemDataRole.UserRole, item.record_id)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked)
            self.items.addItem(row)
        self.notes.setText(self._notes(preview))
        self.status.setText(f"可套用 {len(preview.items)} 份病歷。")
        self._update_apply()

    @staticmethod
    def _notes(preview: ImportPreview) -> str:
        lines = [f"沒貼回：{m.student_name} · {m.visit_date.isoformat()}" for m in preview.missing]
        lines += [f"不認得的標頭（{REASONS[u.reason]}）：{u.header}" for u in preview.unrecognized]
        lines += [f"不認得的代號 {', '.join(i.unknown_codes)}：{i.student_name} · {i.visit_date.isoformat()}"
                  for i in preview.items if i.unknown_codes]
        return "\n".join(lines)

    def checked_ids(self) -> set[int]:
        return {self.items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.items.count())
                if self.items.item(i).checkState() == Qt.CheckState.Checked}

    def _update_apply(self) -> None:
        self.apply_btn.setEnabled(self.preview is not None and bool(self.checked_ids()))

    def apply(self) -> None:
        if self.preview is None:
            return
        ids = self.checked_ids()
        overwriting = [i for i in self.preview.overwriting if i.record_id in ids]
        if overwriting and not self._confirm(len(overwriting)):
            self.status.setText("已取消，沒有寫入。")
            return
        written = apply_import(self.store, self.preview, ids)
        self.apply_btn.setEnabled(False)
        self.status.setText(f"已寫入 {written} 份英文版。")
        self.applied.emit(written)

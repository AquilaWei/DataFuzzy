"""Dialogs for sending charts out for translation (export), taking them back (paste) and
writing them into the school's Excel form."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.pipeline import Pipeline
from ...ui.worker import run_task
from ..db import Record, RecordStore
from ..excel_export import file_name, group_by_location, write_location
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
    "deleted": "這筆病歷已刪除",
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


def ask_replace_file(parent: QWidget | None, path: Path) -> bool:
    answer = QMessageBox.question(parent, "取代檔案", f"「{path.name}」已經存在，要取代嗎？")
    return answer == QMessageBox.StandardButton.Yes


class ExcelExportDialog(QDialog):
    """Pick a date range; each location's visits go into the school's Excel form, one file per
    location in the folder chosen for it (remembered), one sheet per student."""

    LOCATION, COUNT, FOLDER = range(3)

    def __init__(self, store: RecordStore, today: date | None = None,
                 confirm: Callable[[Path], bool] | None = None,
                 choose: Callable[[str, str], str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.today = today or date.today()
        self.written: list[Path] = []
        self._confirm = confirm or (lambda path: ask_replace_file(self, path))
        self._choose = choose or (lambda location, start: QFileDialog.getExistingDirectory(
            self, f"「{location}」的匯出資料夾", start))
        self._groups: dict[str, list[Record]] = {}
        self.setWindowTitle("Excel 匯出")
        self.resize(680, 460)

        self.from_edit = QDateEdit(to_qdate(self.today.replace(day=1)))
        self.to_edit = QDateEdit(to_qdate(self.today))
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["地點", "病歷數", "匯出資料夾（點兩下更改）"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.LOCATION, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COUNT, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.FOLDER, QHeaderView.ResizeMode.Stretch)
        self.folder_btn = QPushButton("選擇資料夾…")
        self.export_btn = QPushButton("匯出")
        self.export_btn.setObjectName("primary")
        self.reveal_btn = QPushButton("在 Finder 中顯示")
        self.reveal_btn.setEnabled(False)
        self.status = QLabel("")
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(QLabel("從"))
        row.addWidget(self.from_edit)
        row.addWidget(QLabel("到"))
        row.addWidget(self.to_edit)
        row.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.folder_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.reveal_btn)
        buttons.addWidget(self.export_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

        self.from_edit.dateChanged.connect(lambda _: self.refresh())
        self.to_edit.dateChanged.connect(lambda _: self.refresh())
        self.table.cellDoubleClicked.connect(lambda r, _: self.choose_folder(r))
        self.folder_btn.clicked.connect(lambda: self.choose_folder(self.table.currentRow()))
        self.export_btn.clicked.connect(self.export)
        self.reveal_btn.clicked.connect(self.reveal)
        self.refresh()

    def locations(self) -> list[str]:
        return list(self._groups)

    def refresh(self) -> None:
        date_from, date_to = to_date(self.from_edit.date()), to_date(self.to_edit.date())
        records = self.store.records_between(date_from, date_to) if date_from <= date_to else []
        self._groups, unassigned = group_by_location(records)
        folders = self.store.excel_folders()
        self.table.setRowCount(len(self._groups))
        for i, (location, recs) in enumerate(self._groups.items()):
            self.table.setItem(i, self.LOCATION, QTableWidgetItem(location))
            self.table.setItem(i, self.COUNT, QTableWidgetItem(str(len(recs))))
            self.table.setItem(i, self.FOLDER, QTableWidgetItem(folders.get(location, "（尚未設定）")))
        if self._groups:
            self.table.setCurrentCell(0, 0)
        if date_from > date_to:
            note = "開始日期晚於結束日期。"
        elif not records:
            note = "這段期間沒有病歷。"
        else:
            note = "每個地點一個檔案（地點-今天日期.xlsx），每位學生一個分頁。"
            if unassigned:
                note += f"\n有 {len(unassigned)} 份病歷沒有填地點，不會匯出。"
        self.status.setText(note)
        self._update_buttons()

    def _update_buttons(self) -> None:
        folders = self.store.excel_folders()
        self.folder_btn.setEnabled(bool(self._groups))
        self.export_btn.setEnabled(any(loc in folders for loc in self._groups))

    def choose_folder(self, row: int) -> None:
        if not 0 <= row < len(self._groups):
            return
        location = self.locations()[row]
        start = self.store.excel_folders().get(location, str(Path.home()))
        folder = self._choose(location, start)
        if not folder:
            return
        self.store.set_excel_folder(location, folder)
        self.table.item(row, self.FOLDER).setText(folder)
        self._update_buttons()

    def export(self) -> None:
        folders = self.store.excel_folders()
        self.written = []
        lines: list[str] = []
        for location, records in self._groups.items():
            if location not in folders:
                lines.append(f"略過「{location}」：尚未設定匯出資料夾。")
                continue
            path = Path(folders[location]) / file_name(location, self.today)
            if path.exists() and not self._confirm(path):
                lines.append(f"略過「{location}」：沒有取代既有檔案。")
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                write_location(self.store, records, path)
            except OSError as e:
                lines.append(f"「{location}」寫入失敗：{e.strerror or e}")
                continue
            self.written.append(path)
            lines.insert(len(self.written) - 1, f"已匯出：{path}")
        self.status.setText("\n".join(lines) or "沒有可匯出的地點。")
        self.reveal_btn.setEnabled(bool(self.written))

    def reveal(self) -> None:
        if self.written:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.written[-1].parent)))

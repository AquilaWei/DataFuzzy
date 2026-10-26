"""Dialogs for sending charts out for translation (export), taking them back (paste) and
writing them into the school's Excel form."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
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
from ..excel_export import file_name, group_by_location, write_workbook
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
    """Pick a date range and, location by location, the students to export. Each student gets
    their own file of the school's Excel form with that location's visits, all in one folder
    (remembered)."""

    LOCATION, STUDENT, COUNT = range(3)

    def __init__(self, store: RecordStore, today: date | None = None,
                 confirm: Callable[[Path], bool] | None = None,
                 choose: Callable[[str], str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.today = today or date.today()
        self.written: list[Path] = []
        self.entries: list[tuple[str, int]] = []  # (location, student id), in the order added
        self._confirm = confirm or (lambda path: ask_replace_file(self, path))
        self._choose = choose or (lambda start: QFileDialog.getExistingDirectory(
            self, "Excel 匯出資料夾", start))
        self._groups: dict[str, list[Record]] = {}
        self.setWindowTitle("Excel 匯出")
        self.resize(680, 500)

        self.from_edit = QDateEdit(to_qdate(self.today.replace(day=1)))
        self.to_edit = QDateEdit(to_qdate(self.today))
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.location_box = QComboBox()
        self.student_box = QComboBox()
        self.student_box.setMinimumContentsLength(10)
        self.add_btn = QPushButton("加入")
        self.add_all_btn = QPushButton("加入此地點全部")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["地點", "學生", "病歷數"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.LOCATION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.STUDENT, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COUNT, QHeaderView.ResizeMode.ResizeToContents)
        self.remove_btn = QPushButton("移除")
        self.folder_label = QLabel("")
        self.folder_label.setWordWrap(True)
        self.folder_btn = QPushButton("選擇資料夾…")
        self.export_btn = QPushButton("匯出")
        self.export_btn.setObjectName("primary")
        self.reveal_btn = QPushButton("在 Finder 中顯示")
        self.reveal_btn.setEnabled(False)
        self.status = QLabel("")
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)

        dates = QHBoxLayout()
        dates.addWidget(QLabel("從"))
        dates.addWidget(self.from_edit)
        dates.addWidget(QLabel("到"))
        dates.addWidget(self.to_edit)
        dates.addStretch(1)
        pick = QHBoxLayout()
        pick.addWidget(QLabel("地點"))
        pick.addWidget(self.location_box, 1)
        pick.addWidget(QLabel("學生"))
        pick.addWidget(self.student_box, 1)
        pick.addWidget(self.add_btn)
        pick.addWidget(self.add_all_btn)
        folder = QHBoxLayout()
        folder.addWidget(QLabel("匯出資料夾："))
        folder.addWidget(self.folder_label, 1)
        folder.addWidget(self.folder_btn)
        buttons = QHBoxLayout()
        buttons.addWidget(self.remove_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.reveal_btn)
        buttons.addWidget(self.export_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(dates)
        layout.addLayout(pick)
        layout.addWidget(self.table, 1)
        layout.addLayout(folder)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

        self.from_edit.dateChanged.connect(lambda _: self.refresh())
        self.to_edit.dateChanged.connect(lambda _: self.refresh())
        self.location_box.currentIndexChanged.connect(lambda _: self._fill_students())
        self.add_btn.clicked.connect(self.add_selected)
        self.add_all_btn.clicked.connect(self.add_location)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.folder_btn.clicked.connect(self.choose_folder)
        self.export_btn.clicked.connect(self.export)
        self.reveal_btn.clicked.connect(self.reveal)
        self.refresh()

    def _range(self) -> tuple[date, date]:
        return to_date(self.from_edit.date()), to_date(self.to_edit.date())

    def locations(self) -> list[str]:
        return list(self._groups)

    def _records(self, location: str, student_id: int) -> list[Record]:
        return [r for r in self._groups.get(location, []) if r.student_id == student_id]

    def _students_at(self, location: str) -> list[tuple[int, str]]:
        """(id, name) of everyone with a visit at `location` in the range, by name."""
        ids = {r.student_id for r in self._groups.get(location, [])}
        students = sorted((self.store.get_student(i) for i in ids), key=lambda s: (s.name, s.id))
        return [(s.id, s.name) for s in students]

    def refresh(self) -> None:
        """Re-read the range: the drop-downs, the counts in the list and the note below it."""
        date_from, date_to = self._range()
        records = self.store.records_between(date_from, date_to) if date_from <= date_to else []
        self._groups, unassigned = group_by_location(records)
        keep = self.location_box.currentText()
        self.location_box.blockSignals(True)
        self.location_box.clear()
        self.location_box.addItems(self.locations())
        self.location_box.setCurrentIndex(max(self.location_box.findText(keep), 0))
        self.location_box.blockSignals(False)
        self._fill_students()
        self._fill_table()
        if date_from > date_to:
            note = "開始日期晚於結束日期。"
        elif not records:
            note = "這段期間沒有病歷。"
        else:
            note = "每位學生一個檔案（姓名-開始日期至結束日期.xlsx），只含所選地點的病歷。"
            if unassigned:
                note += f"\n有 {len(unassigned)} 份病歷沒有填地點，不會匯出。"
        self.status.setText(note)
        self._update_buttons()

    def _fill_students(self) -> None:
        self.student_box.clear()
        location = self.location_box.currentText()
        for student_id, name in self._students_at(location):
            count = len(self._records(location, student_id))
            self.student_box.addItem(f"{name}（{count} 份）", student_id)
        self._update_buttons()

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self.entries))
        for i, (location, student_id) in enumerate(self.entries):
            cells = (location, self.store.get_student(student_id).name,
                     str(len(self._records(location, student_id))))
            for col, text in enumerate(cells):
                self.table.setItem(i, col, QTableWidgetItem(text))

    def _add(self, location: str, student_ids: list[int]) -> None:
        for student_id in student_ids:
            if (location, student_id) not in self.entries:
                self.entries.append((location, student_id))
        self._fill_table()
        self._update_buttons()

    def add_selected(self) -> None:
        """Add the student picked in the drop-downs to the list (once)."""
        if self.student_box.currentIndex() >= 0:
            self._add(self.location_box.currentText(), [self.student_box.currentData()])

    def add_location(self) -> None:
        """Add everyone seen at the picked location in the range."""
        location = self.location_box.currentText()
        self._add(location, [sid for sid, _ in self._students_at(location)])

    def remove_selected(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        self.entries = [e for i, e in enumerate(self.entries) if i not in rows]
        self._fill_table()
        self._update_buttons()

    def _update_buttons(self) -> None:
        folder = self.store.excel_folder()
        self.folder_label.setText(folder or "（尚未設定）")
        has_student = self.student_box.count() > 0
        self.add_btn.setEnabled(has_student)
        self.add_all_btn.setEnabled(has_student)
        self.remove_btn.setEnabled(bool(self.entries))
        self.export_btn.setEnabled(bool(folder) and any(self._records(*e) for e in self.entries))

    def choose_folder(self) -> None:
        folder = self._choose(self.store.excel_folder() or str(Path.home()))
        if folder:
            self.store.set_excel_folder(folder)
            self._update_buttons()

    def _paths(self, folder: Path) -> list[Path]:
        """A file per entry; a name that would repeat in this export gets its location in front."""
        date_from, date_to = self._range()
        names = [self.store.get_student(sid).name for _, sid in self.entries]
        paths = []
        for (location, _), name in zip(self.entries, names):
            repeated = names.count(name) > 1
            paths.append(folder / file_name(name, date_from, date_to, location if repeated else None))
        return paths

    def export(self) -> None:
        folder = Path(self.store.excel_folder())
        self.written = []
        lines: list[str] = []
        used: set[Path] = set()
        for (location, student_id), path in zip(self.entries, self._paths(folder)):
            label = f"「{location}／{self.store.get_student(student_id).name}」"
            records = self._records(location, student_id)
            if not records:
                lines.append(f"略過{label}：這段期間沒有病歷。")
                continue
            if path in used:  # two students of one name at one location
                path = path.with_stem(f"{path.stem} ({student_id})")
            used.add(path)
            if path.exists() and not self._confirm(path):
                lines.append(f"略過{label}：沒有取代既有檔案。")
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                write_workbook(self.store, records, path)
            except OSError as e:
                lines.append(f"{label}寫入失敗：{e.strerror or e}")
                continue
            self.written.append(path)
            lines.insert(len(self.written) - 1, f"已匯出：{path}")
        if self.written and len(lines) == len(self.written):
            self.accept()  # every student written: nothing left to read here
            return
        self.status.setText("\n".join(lines) or "沒有可匯出的學生。")
        self.reveal_btn.setEnabled(bool(self.written))

    def reveal(self) -> None:
        if self.written:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.written[-1].parent)))

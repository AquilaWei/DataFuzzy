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
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.pipeline import Pipeline
from ...ui.worker import run_task
from ..ace_export import ace_cells, to_json
from ..db import Record, RecordStore
from ..excel_export import (
    file_name,
    group_by_location,
    progress_file_name,
    write_progress_report,
    write_workbook,
)
from ..exchange import (
    ExportResult,
    ImportMismatch,
    ImportPreview,
    apply_import,
    export_range,
    preview_import,
)
from .date_view import to_date, to_qdate
from .i18n import tr
from .location_view import NO_LOCATION
from .widgets import SegmentedControl

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
        self.setWindowTitle(tr("匯出病歷"))
        self.resize(640, 520)

        self.from_edit = QDateEdit(to_qdate(today - timedelta(days=6)))
        self.to_edit = QDateEdit(to_qdate(today))
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.export_btn = QPushButton(tr("匯出"))
        self.export_btn.setObjectName("primary")
        self.status = QLabel(tr("選擇日期範圍後按「匯出」。學生與文中的人名會換成代號。"))
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.copy_btn = QPushButton(tr("一鍵複製"))
        self.copy_btn.setEnabled(False)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("從")))
        row.addWidget(self.from_edit)
        row.addWidget(QLabel(tr("到")))
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
            self.status.setText(tr("開始日期晚於結束日期。"))
            return
        self.export_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.status.setText(tr("匯出中…"))
        # Off the GUI thread: the first run loads the detection models.
        self._task = run_task(lambda: export_range(self.store, date_from, date_to, self.pipeline),
                              self._done, self._failed)

    def _done(self, result: ExportResult) -> None:
        self.result = result
        self.export_btn.setEnabled(True)
        self.text.setPlainText(result.text)
        self.copy_btn.setText(tr("一鍵複製"))
        self.copy_btn.setEnabled(bool(result.text))
        if not result.record_count:
            self.status.setText(tr("這段期間沒有病歷。"))
        else:
            note = tr("已匯出 {count} 份病歷，人名已換成代號。", count=result.record_count)
            if self.pipeline.pii is None:
                note += tr("（偵測模型未安裝：只有學生姓名保證被替換，其他人名可能漏掉，請先到「模型管理」下載。）")
            self.status.setText(note)
        self.exported.emit(result)

    def _failed(self, message: str) -> None:
        self.export_btn.setEnabled(True)
        self.status.setText(tr("匯出失敗：{message}", message=message))

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text.toPlainText())
        self.copy_btn.setText(tr("已複製 ✓"))


def ask_overwrite(parent: QWidget | None, count: int) -> bool:
    answer = QMessageBox.question(
        parent, tr("覆蓋英文版"),
        tr("有 {count} 份病歷已有英文版，貼回後會被取代（只保留最新一版）。要覆蓋嗎？", count=count))
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
        self.setWindowTitle(tr("貼回英文版"))
        self.resize(640, 600)

        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText(tr("把翻譯／修正後、含「=== REC-… ===」標頭的文字貼在這裡"))
        self.preview_btn = QPushButton(tr("檢查"))
        self.status = QLabel("")
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)
        self.items = QListWidget()
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.apply_btn = QPushButton(tr("套用"))
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
            self.status.setText(tr("無法對應到匯出：{error}", error=e))
            self._update_apply()
            return
        self.preview = preview
        for item in preview.items:
            warning = tr("　⚠ 會覆蓋既有英文版") if item.overwrites else ""
            if not item.has_marker:  # the translator dropped the marker line
                warning += tr("　⚠ 沒有追蹤段落，全部放進記錄")
            row = QListWidgetItem(f"{item.student_name} · {item.visit_date.isoformat()}{warning}")
            row.setData(Qt.ItemDataRole.UserRole, item.record_id)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked)
            self.items.addItem(row)
        self.notes.setText(self._notes(preview))
        self.status.setText(tr("可套用 {count} 份病歷。", count=len(preview.items)))
        self._update_apply()

    @staticmethod
    def _notes(preview: ImportPreview) -> str:
        lines = [tr("沒貼回：{name} · {day}", name=m.student_name, day=m.visit_date.isoformat())
                 for m in preview.missing]
        lines += [tr("不認得的標頭（{reason}）：{header}", reason=tr(REASONS[u.reason]), header=u.header)
                  for u in preview.unrecognized]
        lines += [tr("不認得的代號 {codes}：{name} · {day}", codes=", ".join(i.unknown_codes),
                     name=i.student_name, day=i.visit_date.isoformat())
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
            self.status.setText(tr("已取消，沒有寫入。"))
            return
        written = apply_import(self.store, self.preview, ids)
        self.apply_btn.setEnabled(False)
        self.status.setText(tr("已寫入 {count} 份英文版。", count=written))
        self.applied.emit(written)


def ask_replace_file(parent: QWidget | None, path: Path) -> bool:
    answer = QMessageBox.question(parent, tr("取代檔案"), tr("「{name}」已經存在，要取代嗎？", name=path.name))
    return answer == QMessageBox.StandardButton.Yes


class ExcelExportDialog(QDialog):
    """Two modes. Handover: pick a date range and, location by location, the students to
    export; each student gets their own file of the school's Excel form with that location's
    visits. Progress report: pick a day; one file lists every active student's goals, a sheet
    per location. Either way into one folder (remembered)."""

    LOCATION, STUDENT, COUNT = range(3)
    HANDOVER, PROGRESS = range(2)

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
            self, tr("Excel 匯出資料夾"), start))
        self._groups: dict[str, list[Record]] = {}
        self.setWindowTitle(tr("Excel 匯出"))
        self.resize(680, 500)

        self.mode = SegmentedControl([tr("交接模式"), tr("Progress Report")])
        self.progress_edit = QDateEdit(to_qdate(self.today))
        self.progress_edit.setCalendarPopup(True)
        self.progress_edit.setDisplayFormat("yyyy-MM-dd")

        self.from_edit = QDateEdit(to_qdate(self.today.replace(day=1)))
        self.to_edit = QDateEdit(to_qdate(self.today))
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.location_box = QComboBox()
        self.student_box = QComboBox()
        self.student_box.setMinimumContentsLength(10)
        self.add_btn = QPushButton(tr("加入"))
        self.add_all_btn = QPushButton(tr("加入此地點全部"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("地點"), tr("學生"), tr("病歷數")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.LOCATION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.STUDENT, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COUNT, QHeaderView.ResizeMode.ResizeToContents)
        self.remove_btn = QPushButton(tr("移除"))
        self.folder_label = QLabel("")
        self.folder_label.setWordWrap(True)
        self.folder_btn = QPushButton(tr("選擇資料夾…"))
        self.export_btn = QPushButton(tr("匯出"))
        self.export_btn.setObjectName("primary")
        self.reveal_btn = QPushButton(tr("在 Finder 中顯示"))
        self.reveal_btn.setEnabled(False)
        self.status = QLabel("")
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)

        dates = QHBoxLayout()
        dates.addWidget(QLabel(tr("從")))
        dates.addWidget(self.from_edit)
        dates.addWidget(QLabel(tr("到")))
        dates.addWidget(self.to_edit)
        dates.addStretch(1)
        pick = QHBoxLayout()
        pick.addWidget(QLabel(tr("地點")))
        pick.addWidget(self.location_box, 1)
        pick.addWidget(QLabel(tr("學生")))
        pick.addWidget(self.student_box, 1)
        pick.addWidget(self.add_btn)
        pick.addWidget(self.add_all_btn)
        folder = QHBoxLayout()
        folder.addWidget(QLabel(tr("匯出資料夾：")))
        folder.addWidget(self.folder_label, 1)
        folder.addWidget(self.folder_btn)
        buttons = QHBoxLayout()
        buttons.addWidget(self.remove_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.reveal_btn)
        buttons.addWidget(self.export_btn)
        handover = QWidget()
        handover_layout = QVBoxLayout(handover)
        handover_layout.setContentsMargins(0, 0, 0, 0)
        handover_layout.addLayout(dates)
        handover_layout.addLayout(pick)
        handover_layout.addWidget(self.table, 1)
        progress = QWidget()
        progress_layout = QVBoxLayout(progress)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_day = QHBoxLayout()
        progress_day.addWidget(QLabel(tr("日期")))
        progress_day.addWidget(self.progress_edit)
        progress_day.addStretch(1)
        progress_layout.addLayout(progress_day)
        progress_layout.addStretch(1)
        self.pages = QStackedWidget()
        self.pages.addWidget(handover)
        self.pages.addWidget(progress)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode)
        mode_row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(mode_row)
        layout.addWidget(self.pages, 1)
        layout.addLayout(folder)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

        self.mode.changed.connect(self.set_mode)
        self.progress_edit.dateChanged.connect(lambda _: self.refresh())
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

    def set_mode(self, mode: int) -> None:
        """Show the handover or the progress report page."""
        if self.mode.index() != mode:
            self.mode.set_index(mode)  # calls back here through `changed`
            return
        self.pages.setCurrentIndex(mode)
        self.remove_btn.setVisible(mode == self.HANDOVER)
        self.refresh()

    def _progress_day(self) -> date:
        return to_date(self.progress_edit.date())

    def _active_count(self) -> int:
        return sum(s.active for s in self.store.students())

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
        if self.mode.index() == self.PROGRESS:
            count = self._active_count()
            note = (tr("每個地點一個分頁，列出 {count} 位啟用中學生在這天的 goals；Progress 欄先填入 goal 方便編輯。",
                       count=count) if count else tr("沒有啟用中的學生。"))
            self.status.setText(note)
            self._update_buttons()
            return
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
            note = tr("開始日期晚於結束日期。")
        elif not records:
            note = tr("這段期間沒有病歷。")
        else:
            note = tr("每位學生一個檔案（姓名-開始日期至結束日期.xlsx），只含所選地點的病歷。")
            if unassigned:
                note += tr("\n有 {count} 份病歷沒有填地點，不會匯出。", count=len(unassigned))
        self.status.setText(note)
        self._update_buttons()

    def _fill_students(self) -> None:
        self.student_box.clear()
        location = self.location_box.currentText()
        for student_id, name in self._students_at(location):
            count = len(self._records(location, student_id))
            self.student_box.addItem(tr("{name}（{count} 份）", name=name, count=count), student_id)
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
        self.folder_label.setText(folder or tr("（尚未設定）"))
        has_student = self.student_box.count() > 0
        self.add_btn.setEnabled(has_student)
        self.add_all_btn.setEnabled(has_student)
        self.remove_btn.setEnabled(bool(self.entries))
        if self.mode.index() == self.PROGRESS:
            self.export_btn.setEnabled(bool(folder) and self._active_count() > 0)
            return
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
        if self.mode.index() == self.PROGRESS:
            self.export_progress()
            return
        folder = Path(self.store.excel_folder())
        self.written = []
        lines: list[str] = []
        used: set[Path] = set()
        for (location, student_id), path in zip(self.entries, self._paths(folder)):
            label = f"「{location}／{self.store.get_student(student_id).name}」"
            records = self._records(location, student_id)
            if not records:
                lines.append(tr("略過{label}：這段期間沒有病歷。", label=label))
                continue
            if path in used:  # two students of one name at one location
                path = path.with_stem(f"{path.stem} ({student_id})")
            used.add(path)
            if path.exists() and not self._confirm(path):
                lines.append(tr("略過{label}：沒有取代既有檔案。", label=label))
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                write_workbook(self.store, records, path)
            except OSError as e:
                lines.append(tr("{label}寫入失敗：{error}", label=label, error=e.strerror or e))
                continue
            self.written.append(path)
            lines.insert(len(self.written) - 1, tr("已匯出：{path}", path=path))
        if self.written and len(lines) == len(self.written):
            self.accept()  # every student written: nothing left to read here
            return
        self.status.setText("\n".join(lines) or tr("沒有可匯出的學生。"))
        self.reveal_btn.setEnabled(bool(self.written))

    def export_progress(self) -> None:
        """Write the progress report of the picked day."""
        path = Path(self.store.excel_folder()) / progress_file_name(self._progress_day())
        self.written = []
        if path.exists() and not self._confirm(path):
            self.status.setText(tr("略過 {path}：沒有取代既有檔案。", path=path.name))
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_progress_report(self.store, self._progress_day(), path, tr(NO_LOCATION))
        except OSError as e:
            self.status.setText(tr("{label}寫入失敗：{error}", label=path.name, error=e.strerror or e))
            return
        self.written.append(path)
        self.accept()

    def reveal(self) -> None:
        if self.written:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.written[-1].parent)))


class AceExportDialog(QDialog):
    """Pick a week, save its charts as the ACE fill-in file the browser extension enters into
    ACE Portal (see ace_export.py), into a folder the user picks once (remembered; Downloads
    until then). The file is not encrypted, which the dialog says."""

    def __init__(self, store: RecordStore, today: date | None = None,
                 choose: Callable[[str], str] | None = None,
                 confirm: Callable[[Path], bool] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.written: Path | None = None
        self._choose = choose or (lambda start: QFileDialog.getExistingDirectory(
            self, tr("ACE 填寫檔資料夾"), start))
        self._confirm = confirm or (lambda path: ask_replace_file(self, path))
        today = today or date.today()
        monday = today - timedelta(days=today.weekday())  # ACE's grid shows Monday to Sunday
        self.setWindowTitle(tr("ACE 填寫檔"))
        self.resize(560, 240)

        self.from_edit = QDateEdit(to_qdate(monday))
        self.to_edit = QDateEdit(to_qdate(monday + timedelta(days=6)))
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.folder_label = QLabel(str(self.folder()))
        self.folder_label.setWordWrap(True)
        self.folder_btn = QPushButton(tr("選擇資料夾…"))
        self.save_btn = QPushButton(tr("存檔"))
        self.save_btn.setObjectName("primary")
        warning = QLabel(tr("檔案裡有學生姓名和英文病歷，沒有加密。在 ACE 填完後請刪除。"))
        warning.setWordWrap(True)
        self.status = QLabel("")
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("從")))
        row.addWidget(self.from_edit)
        row.addWidget(QLabel(tr("到")))
        row.addWidget(self.to_edit)
        row.addStretch(1)
        folder = QHBoxLayout()
        folder.addWidget(QLabel(tr("存放資料夾：")))
        folder.addWidget(self.folder_label, 1)
        folder.addWidget(self.folder_btn)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.save_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addLayout(folder)
        layout.addWidget(warning)
        layout.addWidget(self.status, 1)
        layout.addLayout(buttons)
        self.folder_btn.clicked.connect(self.choose_folder)
        self.save_btn.clicked.connect(self.save)

    def folder(self) -> Path:
        return Path(self.store.ace_folder() or Path.home() / "Downloads")

    def choose_folder(self) -> None:
        chosen = self._choose(str(self.folder()))
        if chosen:
            self.store.set_ace_folder(chosen)
            self.folder_label.setText(chosen)

    def save(self) -> None:
        date_from, date_to = to_date(self.from_edit.date()), to_date(self.to_edit.date())
        if date_from > date_to:
            self.status.setText(tr("開始日期晚於結束日期。"))
            return
        cells = ace_cells(self.store, date_from, date_to)
        if not cells:
            self.status.setText(tr("這段期間沒有病歷。"))
            return
        path = self.folder() / f"TheraNote-ACE-{date_from.isoformat()}.json"
        if path.exists() and not self._confirm(path):
            self.status.setText(tr("略過 {path}：沒有取代既有檔案。", path=path.name))
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(to_json(cells, date_from, date_to), encoding="utf-8")
        except OSError as e:
            self.status.setText(tr("{label}寫入失敗：{error}", label=path.name, error=e.strerror or e))
            return
        self.written = path
        manual = sum(bool(cell.problems) for cell in cells)
        self.status.setText(tr("已存 {count} 格到 {path}；其中 {manual} 格要手動填。",
                               count=len(cells), path=path, manual=manual))

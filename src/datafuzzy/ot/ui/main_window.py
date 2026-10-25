"""TheraNote's main window: a sidebar (students or calendar, plus actions) and a content area."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...core.models import ModelSpec
from ...core.pipeline import Pipeline
from ...ui.about import AboutDialog
from ...ui.model_manager import ModelManager
from .. import APP_NAME
from ..db import DuplicateRecord, RecordStore
from .date_view import DayRecordsView, MarkedCalendar, to_date, to_qdate
from .editor import RecordEditor
from .exchange_dialogs import ExportDialog, ImportDialog
from .student_view import StudentRecordsView
from .widgets import SegmentedControl

STUDENT_MODE = 0
DATE_MODE = 1

# Content pages
PLACEHOLDER, STUDENT_PAGE, DAY_PAGE, EDITOR_PAGE = range(4)


class NewRecordDialog(QDialog):
    """Choose the student and the day of a new chart."""

    def __init__(self, store: RecordStore, student_id: int | None, day: date,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新增病歷")
        self.student_box = QComboBox()
        for student in store.students():
            self.student_box.addItem(student.name, student.id)
        index = self.student_box.findData(student_id)
        self.student_box.setCurrentIndex(max(index, 0))
        self.date_edit = QDateEdit(to_qdate(day))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("學生", self.student_box)
        form.addRow("日期", self.date_edit)
        form.addRow(buttons)

    def choice(self) -> tuple[int, date]:
        return self.student_box.currentData(), to_date(self.date_edit.date())


class TheraNoteWindow(QMainWindow):
    def __init__(self, store: RecordStore, pipeline: Pipeline, specs: list[ModelSpec] | None = None,
                 models_root: Path | None = None, debounce_ms: int | None = None) -> None:
        super().__init__()
        self.store = store
        self.pipeline = pipeline
        self.specs = specs or []
        self.models_root = models_root
        self._editor_kwargs = {} if debounce_ms is None else {"debounce_ms": debounce_ms}
        self.editor: RecordEditor | None = None
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1100, 720)

        self._build_menus()
        self.mode_switch = SegmentedControl(["學生", "日期"])
        self.add_student_btn = QPushButton("新增學生")
        self.add_record_btn = QPushButton("新增病歷")
        self.export_btn = QPushButton("匯出")
        self.import_btn = QPushButton("貼回")
        self.student_list = QListWidget()
        self.calendar = MarkedCalendar(store)
        self.sidebar_stack = QStackedWidget()
        self.sidebar_stack.addWidget(self.student_list)
        self.sidebar_stack.addWidget(self.calendar)

        self.student_view = StudentRecordsView(store)
        self.day_view = DayRecordsView(store)
        self.placeholder = QLabel("選擇一位學生，或新增學生開始記錄。")
        self.placeholder.setObjectName("subtle")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content = QStackedWidget()
        self.content.setObjectName("Content")
        for page in (self.placeholder, self.student_view, self.day_view, QWidget()):
            self.content.addWidget(page)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        sidebar.setFixedWidth(300)
        actions = QGridLayout()
        actions.addWidget(self.add_student_btn, 0, 0)
        actions.addWidget(self.add_record_btn, 0, 1)
        actions.addWidget(self.export_btn, 1, 0)
        actions.addWidget(self.import_btn, 1, 1)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 16, 14, 12)
        side.setSpacing(10)
        side.addWidget(self.mode_switch)
        side.addLayout(actions)
        side.addWidget(self.sidebar_stack, 1)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.content, 1)
        self.setCentralWidget(root)

        self.mode_switch.changed.connect(self.set_mode)
        self.student_list.currentItemChanged.connect(self._student_selected)
        self.calendar.selectionChanged.connect(self._day_selected)
        self.student_view.open_record.connect(self.open_record)
        self.day_view.open_record.connect(self.open_record)
        self.add_student_btn.clicked.connect(lambda: self.add_student())
        self.add_record_btn.clicked.connect(lambda: self.new_record())
        self.export_btn.clicked.connect(self.open_export)
        self.import_btn.clicked.connect(self.open_import)

        self.refresh_students()
        self.day_view.show_day(self.calendar.selected())

    def _build_menus(self) -> None:
        models_action = QAction("模型管理…", self)
        models_action.triggered.connect(self.open_model_manager)
        self.menuBar().addMenu(APP_NAME).addAction(models_action)
        about_action = QAction(f"關於 {APP_NAME}", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)  # macOS: app menu
        about_action.triggered.connect(lambda: AboutDialog(self).exec())
        self.menuBar().addMenu("說明").addAction(about_action)

    # --- students and navigation ----------------------------------------------------

    def refresh_students(self, select_id: int | None = None) -> None:
        """Reload the student list, keeping (or setting) the selection."""
        keep = select_id if select_id is not None else self.current_student_id()
        self.student_list.blockSignals(True)
        self.student_list.clear()
        for student in self.store.students():
            item = QListWidgetItem(student.name)
            item.setData(Qt.ItemDataRole.UserRole, student.id)
            self.student_list.addItem(item)
            if student.id == keep:
                self.student_list.setCurrentItem(item)
        self.student_list.blockSignals(False)
        self.add_record_btn.setEnabled(self.student_list.count() > 0)
        self.student_view.show_student(self.current_student_id())
        if self.mode_switch.index() == STUDENT_MODE and self.editor is None:
            self.content.setCurrentIndex(STUDENT_PAGE if self.current_student_id() else PLACEHOLDER)

    def current_student_id(self) -> int | None:
        item = self.student_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _ask_student_name(self) -> str:
        name, ok = QInputDialog.getText(self, "新增學生", "學生姓名")
        return name.strip() if ok else ""

    def add_student(self, name: str | None = None) -> int | None:
        """Add and select a student, asking for the name unless given. Returns the id, or None
        if the name was empty or the dialog cancelled."""
        name = self._ask_student_name() if name is None else name.strip()
        if not name:
            return None
        student = self.store.add_student(name)
        self.set_mode(STUDENT_MODE)
        self.refresh_students(select_id=student.id)
        return student.id

    def set_mode(self, mode: int) -> None:
        """Switch between the by-student and the by-date arrangement."""
        self.close_editor()
        self.mode_switch.blockSignals(True)
        self.mode_switch.set_index(mode)
        self.mode_switch.blockSignals(False)
        self.sidebar_stack.setCurrentIndex(mode)
        if mode == STUDENT_MODE:
            self.student_view.refresh()
            self.content.setCurrentIndex(STUDENT_PAGE if self.current_student_id() else PLACEHOLDER)
        else:
            self.day_view.show_day(self.calendar.selected())
            self.content.setCurrentIndex(DAY_PAGE)

    def _student_selected(self, *_: object) -> None:
        self.close_editor()
        self.student_view.show_student(self.current_student_id())
        self.content.setCurrentIndex(STUDENT_PAGE if self.current_student_id() else PLACEHOLDER)

    def _day_selected(self) -> None:
        self.close_editor()
        self.day_view.show_day(self.calendar.selected())
        self.content.setCurrentIndex(DAY_PAGE)

    # --- records --------------------------------------------------------------------

    def _pick_new_record(self) -> tuple[int, date] | None:
        dialog = NewRecordDialog(self.store, self.current_student_id(), self.calendar.selected()
                                 if self.mode_switch.index() == DATE_MODE else date.today(), self)
        return dialog.choice() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _confirm_open_existing(self, student_name: str, day: date) -> bool:
        answer = QMessageBox.question(
            self, "已有病歷", f"{student_name} 在 {day.isoformat()} 已經有一份病歷。要開啟它嗎？")
        return answer == QMessageBox.StandardButton.Yes

    def new_record(self, student_id: int | None = None, day: date | None = None) -> int | None:
        """Start a chart for a student on a day (asking which, unless given) and open it.
        The location starts as the student's last one; a first chart starts empty. If the
        student already has a chart that day, offers to open it instead. Returns the record id."""
        if student_id is None or day is None:
            picked = self._pick_new_record()
            if picked is None:
                return None
            student_id, day = picked
        existing = self.store.find_record(student_id, day)
        if existing:
            if self._confirm_open_existing(self.store.get_student(student_id).name, day):
                self.open_record(existing.id)
                return existing.id
            return None
        try:
            record = self.store.add_record(student_id, day, self.store.student_default_location(student_id))
        except DuplicateRecord as e:  # created elsewhere between the check and now
            self.open_record(e.record_id)
            return e.record_id
        self.refresh_after_change()
        self.open_record(record.id)
        return record.id

    def open_record(self, record_id: int) -> None:
        """Show a record in the editor. Whatever was being edited is saved first."""
        self.close_editor()
        editor = RecordEditor(self.store, record_id, parent=self, **self._editor_kwargs)
        editor.saved.connect(lambda _: self.refresh_after_change())
        editor.closed.connect(self._editor_closed)
        self.editor = editor
        old = self.content.widget(EDITOR_PAGE)
        self.content.removeWidget(old)
        old.deleteLater()
        self.content.insertWidget(EDITOR_PAGE, editor)
        self.content.setCurrentIndex(EDITOR_PAGE)

    def close_editor(self) -> None:
        """Save and drop the open editor, if any (the content page is chosen by the caller)."""
        if self.editor is None:
            return
        self.editor.flush()
        self.editor = None

    def _editor_closed(self) -> None:
        self.editor = None
        self.refresh_after_change()
        if self.mode_switch.index() == STUDENT_MODE:
            self.content.setCurrentIndex(STUDENT_PAGE)
        else:
            self.content.setCurrentIndex(DAY_PAGE)

    def refresh_after_change(self) -> None:
        """Records changed: update the cards, the day list and the calendar markers."""
        self.student_view.refresh()
        self.day_view.refresh()
        self.calendar.refresh_markers()

    def flush(self) -> None:
        """Write any pending edit now (used on quit)."""
        if self.editor is not None:
            self.editor.flush()

    # --- export, import, models -----------------------------------------------------

    def open_export(self) -> None:
        self.flush()  # export what is on screen, not what was last auto-saved
        ExportDialog(self.store, self.pipeline, parent=self).exec()

    def open_import(self) -> None:
        self.flush()
        dialog = ImportDialog(self.store, parent=self)
        dialog.applied.connect(lambda _: self._imported())
        dialog.exec()

    def _imported(self) -> None:
        self.refresh_after_change()
        if self.editor is not None:
            self.editor.reload()

    def open_model_manager(self) -> None:
        if self.models_root is None:
            return
        dialog = ModelManager(self.specs, self.models_root, self)
        dialog.models_changed.connect(self.reload_models)
        dialog.exec()

    def reload_models(self) -> None:
        if self.models_root is not None:
            self.pipeline.load_models(self.specs, self.models_root)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.flush()
        event.accept()

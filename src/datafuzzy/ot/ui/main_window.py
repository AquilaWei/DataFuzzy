"""TheraNote's main window: a sidebar (students or calendar, plus actions) and a content area."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
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
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...core.models import ModelSpec
from ...core.pipeline import Pipeline
from ...ui.model_manager import ModelManager
from .. import APP_NAME
from ..db import DuplicateRecord, RecordStore, StudentProfile
from .about import AboutDialog
from .date_view import DayRecordsView, MarkedCalendar, to_date, to_qdate
from .editor import RecordEditor
from .exchange_dialogs import ExcelExportDialog, ExportDialog, ImportDialog
from .i18n import language, save_language, tr
from .location_view import NO_LOCATION, LocationRecordsView
from .profile_dialog import StudentProfileDialog
from .settings_dialog import SettingsDialog
from .student_view import StudentRecordsView
from .widgets import SegmentedControl

STUDENT_MODE = 0
DATE_MODE = 1
LOCATION_MODE = 2

# Content pages
PLACEHOLDER, STUDENT_PAGE, DAY_PAGE, EDITOR_PAGE, LOCATION_PAGE = range(5)


class NewRecordDialog(QDialog):
    """Choose the student and the day of a new chart. With `by_location`, a location is
    picked first and the student list narrows to those whose location it is. It starts at `location`
    if given, else at where that day's sessions were, else at the latest location."""

    ALL_LOCATIONS = "（所有學生）"

    def __init__(self, store: RecordStore, student_id: int | None, day: date,
                 parent: QWidget | None = None, by_location: bool = False,
                 location: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("新增病歷"))
        self.store = store
        self.location_box: QComboBox | None = None
        self.student_box = QComboBox()
        self.date_edit = QDateEdit(to_qdate(day))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        form = QFormLayout(self)
        locations = store.all_locations() if by_location else []
        if locations:
            self.location_box = QComboBox()
            for place in locations:
                self.location_box.addItem(place, place)
            self.location_box.addItem(tr(self.ALL_LOCATIONS), None)
            if not location:
                today = [r.location for r in store.records_on(day) if r.location]
                location = today[-1] if today else None
            self.location_box.setCurrentIndex(max(self.location_box.findData(location), 0))
            self.location_box.currentIndexChanged.connect(lambda: self._fill_students(None))
            form.addRow(tr("地點"), self.location_box)
        form.addRow(tr("學生"), self.student_box)
        form.addRow(tr("日期"), self.date_edit)
        form.addRow(buttons)
        self._fill_students(student_id)

    def location(self) -> str | None:
        """The chosen location, or None when no location was picked."""
        return self.location_box.currentData() if self.location_box else None

    def _fill_students(self, keep: int | None) -> None:
        location = self.location()
        students = self.store.students()
        if location is not None:
            students = [s for s in students if self.store.student_location(s.id) == location]
        self.student_box.clear()
        for student in students:
            self.student_box.addItem(student.name, student.id)
        self.student_box.setCurrentIndex(max(self.student_box.findData(keep), 0))
        self.ok_button.setEnabled(bool(students))

    def choice(self) -> tuple[int, date]:
        return self.student_box.currentData(), to_date(self.date_edit.date())


class TheraNoteWindow(QMainWindow):
    # The interface language was changed; its widgets keep their text, so the app makes a new
    # window (see app.Launcher).
    language_changed = Signal()

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
        self.mode_switch = SegmentedControl([tr("學生"), tr("日期"), tr("地點")])
        self.add_student_btn = QPushButton(tr("新增學生"))
        self.add_record_btn = QPushButton(tr("新增病歷"))
        self.export_btn = QPushButton(tr("匯出"))
        self.import_btn = QPushButton(tr("貼回"))
        self.excel_btn = QPushButton(tr("Excel 匯出"))
        self.settings_btn = QPushButton(tr("設定"))
        self.settings_btn.setObjectName("flat")
        self.student_list = QListWidget()
        self.calendar = MarkedCalendar(store)
        self.location_list = QListWidget()
        self.sidebar_stack = QStackedWidget()
        self.sidebar_stack.addWidget(self.student_list)
        self.sidebar_stack.addWidget(self.calendar)
        self.sidebar_stack.addWidget(self.location_list)

        self.student_view = StudentRecordsView(store)
        self.day_view = DayRecordsView(store)
        self.location_view = LocationRecordsView(store)
        self.placeholder = QLabel(tr("選擇一位學生，或新增學生開始記錄。"))
        self.placeholder.setObjectName("subtle")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content = QStackedWidget()
        self.content.setObjectName("Content")
        for page in (self.placeholder, self.student_view, self.day_view, QWidget(), self.location_view):
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
        actions.addWidget(self.excel_btn, 2, 0, 1, 2)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 16, 14, 12)
        side.setSpacing(10)
        side.addWidget(self.mode_switch)
        side.addLayout(actions)
        side.addWidget(self.sidebar_stack, 1)
        side.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignLeft)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.content, 1)
        self.setCentralWidget(root)

        self.mode_switch.changed.connect(self.set_mode)
        self.student_list.currentItemChanged.connect(self._student_selected)
        self.student_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.student_list.customContextMenuRequested.connect(self._show_student_menu)
        self.calendar.selectionChanged.connect(self._day_selected)
        self.location_list.currentItemChanged.connect(self._location_selected)
        self.location_view.open_record.connect(self.open_record)
        self.location_view.delete_record.connect(self.delete_record)
        self.student_view.open_record.connect(self.open_record)
        self.day_view.open_record.connect(self.open_record)
        self.student_view.delete_record.connect(self.delete_record)
        self.day_view.delete_record.connect(self.delete_record)
        self.student_view.rename_student.connect(lambda sid: self.rename_student(sid))
        self.student_view.edit_profile.connect(lambda sid: self.edit_profile(sid))
        self.add_student_btn.clicked.connect(lambda: self.add_student())
        self.add_record_btn.clicked.connect(lambda: self.new_record())
        self.export_btn.clicked.connect(self.open_export)
        self.import_btn.clicked.connect(self.open_import)
        self.excel_btn.clicked.connect(self.open_excel_export)
        self.settings_btn.clicked.connect(lambda: self.open_settings())

        self.refresh_students()
        self.refresh_locations()
        self.day_view.show_day(self.calendar.selected())

    def _build_menus(self) -> None:
        models_action = QAction(tr("模型管理…"), self)
        models_action.triggered.connect(self.open_model_manager)
        settings_action = QAction(tr("設定…"), self)
        settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)  # macOS: app menu, ⌘,
        settings_action.triggered.connect(lambda: self.open_settings())
        app_menu = self.menuBar().addMenu(APP_NAME)
        app_menu.addAction(models_action)
        app_menu.addAction(settings_action)
        about_action = QAction(tr("關於 {app}", app=APP_NAME), self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)  # macOS: app menu
        about_action.triggered.connect(lambda: AboutDialog(self).exec())
        self.menuBar().addMenu(tr("說明")).addAction(about_action)

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
        name, ok = QInputDialog.getText(self, tr("新增學生"), tr("學生姓名"))
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

    def _ask_new_name(self, current: str) -> str:
        name, ok = QInputDialog.getText(self, tr("修改姓名"), tr("學生姓名"), text=current)
        return name.strip() if ok else ""

    def rename_student(self, student_id: int, name: str | None = None) -> bool:
        """Correct a student's name, asking for it unless given. False if the name was empty,
        unchanged or the dialog cancelled."""
        current = self.store.get_student(student_id).name
        name = self._ask_new_name(current) if name is None else name.strip()
        if not name or name == current:
            return False
        self.store.rename_student(student_id, name)
        self.refresh_students(select_id=student_id)
        self.day_view.refresh()
        return True

    def _ask_profile(self, name: str, current: StudentProfile) -> StudentProfile | None:
        dialog = StudentProfileDialog(name, current, parent=self, locations=self.store.all_locations())
        return dialog.profile() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def edit_profile(self, student_id: int) -> bool:
        """Edit a student's profile in a dialog. False if it was cancelled. A new location
        applies to the student's new records; the ones already written keep theirs."""
        current = replace(self.store.get_profile(student_id),
                          location=self.store.student_location(student_id))
        profile = self._ask_profile(self.store.get_student(student_id).name, current)
        if profile is None:
            return False
        self.store.set_profile(student_id, profile)
        if self.editor is not None and self.editor.student_id == student_id:
            self.editor.show_profile()
        self.refresh_locations()  # a location may be new
        return True

    def student_menu(self, pos: QPoint) -> QMenu | None:
        """The menu for the student at `pos` (list viewport coordinates), None off the rows."""
        item = self.student_list.itemAt(pos)
        if item is None:
            return None
        student_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction(tr("刪除學生…")).triggered.connect(lambda: self.delete_student(student_id))
        return menu

    def _show_student_menu(self, pos: QPoint) -> None:
        if menu := self.student_menu(pos):
            menu.exec(self.student_list.viewport().mapToGlobal(pos))

    def _confirm_delete_student(self, student_name: str, record_count: int) -> bool:
        answer = QMessageBox.warning(
            self, tr("刪除學生"), tr("要刪除 {name} 嗎？\n這位學生的 {count} 份病歷（中英文內容）都會一併刪除，無法復原。",
                                    name=student_name, count=record_count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Yes

    def delete_student(self, student_id: int) -> bool:
        """Delete a student and all of their records after warning. Returns whether they were
        deleted."""
        records = self.store.records_for_student(student_id)
        if not self._confirm_delete_student(self.store.get_student(student_id).name, len(records)):
            return False
        editing_theirs = self.editor is not None and self.editor.record_id in {r.id for r in records}
        if editing_theirs:
            self.close_editor()  # its record is about to go; nothing may write to it later
        self.store.delete_student(student_id)
        self.refresh_students()
        self.refresh_after_change()
        if editing_theirs:
            self.content.setCurrentIndex(self._mode_page())
        return True

    def refresh_locations(self) -> None:
        """Reload the location list (most recently visited first, then records without a
        location), keeping the selection."""
        keep = self.current_location()
        locations = self.store.all_locations()
        if self.store.records_at(""):
            locations.append("")
        self.location_list.blockSignals(True)
        self.location_list.clear()
        for location in locations:
            item = QListWidgetItem(location or tr(NO_LOCATION))
            item.setData(Qt.ItemDataRole.UserRole, location)
            self.location_list.addItem(item)
            if location == keep:
                self.location_list.setCurrentItem(item)
        if self.location_list.currentItem() is None and self.location_list.count():
            self.location_list.setCurrentRow(0)
        self.location_list.blockSignals(False)
        self.location_view.show_location(self.current_location())

    def current_location(self) -> str | None:
        item = self.location_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _location_selected(self, *_: object) -> None:
        self.close_editor()
        self.location_view.show_location(self.current_location())
        self.content.setCurrentIndex(self._mode_page())

    def _mode_page(self) -> int:
        """The content page that goes with the current mode and selection."""
        mode = self.mode_switch.index()
        if mode == STUDENT_MODE:
            return STUDENT_PAGE if self.current_student_id() else PLACEHOLDER
        if mode == DATE_MODE:
            return DAY_PAGE
        return LOCATION_PAGE

    def set_mode(self, mode: int) -> None:
        """Switch between the by-student, by-date and by-location arrangements."""
        self.close_editor()
        self.mode_switch.blockSignals(True)
        self.mode_switch.set_index(mode)
        self.mode_switch.blockSignals(False)
        self.sidebar_stack.setCurrentIndex(mode)
        if mode == STUDENT_MODE:
            self.student_view.refresh()
        elif mode == DATE_MODE:
            self.day_view.show_day(self.calendar.selected())
        else:
            self.refresh_locations()
        self.content.setCurrentIndex(self._mode_page())

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
        mode = self.mode_switch.index()
        dialog = NewRecordDialog(self.store, self.current_student_id(),
                                 self.calendar.selected() if mode == DATE_MODE else date.today(), self,
                                 by_location=mode != STUDENT_MODE,
                                 location=self.current_location() if mode == LOCATION_MODE else None)
        return dialog.choice() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _confirm_open_existing(self, student_name: str, day: date) -> bool:
        answer = QMessageBox.question(
            self, tr("已有病歷"),
            tr("{name} 在 {day} 已經有一份病歷。要開啟它嗎？", name=student_name, day=day.isoformat()))
        return answer == QMessageBox.StandardButton.Yes

    def new_record(self, student_id: int | None = None, day: date | None = None) -> int | None:
        """Start a chart for a student on a day (asking which, unless given) and open it.
        It is at the student's location (from the profile) and in the time slot of their
        latest visit on the same weekday, else at their last start time; a first chart starts
        without one. If the student already has a chart that day,
        offers to open it instead. Returns the record id."""
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
        start_time, end_time = self.store.student_default_slot(student_id, day)
        try:
            record = self.store.add_record(
                student_id, day, self.store.student_location(student_id),
                start_time=start_time, end_time=end_time)
        except DuplicateRecord as e:  # created elsewhere between the check and now
            self.open_record(e.record_id)
            return e.record_id
        self.refresh_after_change()
        self.open_record(record.id)
        return record.id

    def _confirm_delete(self, student_name: str, day: date) -> bool:
        answer = QMessageBox.warning(
            self, tr("刪除病歷"), tr("要刪除 {name} 在 {day} 的病歷嗎？\n中英文內容都會一併刪除，無法復原。",
                                    name=student_name, day=day.isoformat()),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Yes

    def delete_record(self, record_id: int) -> bool:
        """Delete a record after asking. Returns whether it was deleted."""
        record = self.store.get_record(record_id)
        if not self._confirm_delete(self.store.get_student(record.student_id).name, record.visit_date):
            return False
        self.store.delete_record(record_id)
        self.refresh_after_change()
        return True

    def open_record(self, record_id: int) -> None:
        """Show a record in the editor. Whatever was being edited is saved first."""
        self.close_editor()
        editor = RecordEditor(self.store, record_id, parent=self, **self._editor_kwargs)
        editor.saved.connect(lambda _: self.refresh_after_change())
        editor.edit_profile.connect(lambda sid: self.edit_profile(sid))
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
        self.content.setCurrentIndex(self._mode_page())

    def refresh_after_change(self) -> None:
        """Records changed: update the cards, the day and location lists and the calendar
        markers."""
        self.student_view.refresh()
        self.day_view.refresh()
        self.refresh_locations()
        self.calendar.refresh_markers()

    def flush(self) -> None:
        """Write any pending edit now (used on quit)."""
        if self.editor is not None:
            self.editor.flush()

    # --- export, import, models -----------------------------------------------------

    def open_export(self) -> None:
        self.flush()  # export what is on screen, not what was last auto-saved
        ExportDialog(self.store, self.pipeline, parent=self).exec()

    def open_excel_export(self) -> None:
        self.flush()
        ExcelExportDialog(self.store, parent=self).exec()

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
        dialog = ModelManager(self.specs, self.models_root, self, translate=tr)
        dialog.models_changed.connect(self.reload_models)
        dialog.exec()

    def _ask_language(self) -> str | None:
        dialog = SettingsDialog(self)
        return dialog.chosen_language() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def open_settings(self, chosen: str | None = None) -> bool:
        """Ask for the settings (or take `chosen`); saves a new language and says so with
        language_changed. Returns whether the language changed."""
        chosen = chosen or self._ask_language()
        if chosen is None or chosen == language():
            return False
        self.flush()  # the window is about to be replaced
        save_language(chosen)
        self.language_changed.emit()
        return True

    def reload_models(self) -> None:
        if self.models_root is not None:
            self.pipeline.load_models(self.specs, self.models_root)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.flush()
        event.accept()

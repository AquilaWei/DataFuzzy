"""Side panel: the code files of this run (rename / delete) and a preview of the selected one."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.mapping import Session

ID = Qt.ItemDataRole.UserRole


def _summary(s: Session) -> str:
    time = s.created_at.split("T")[-1][:5]
    return f"{s.label}\n{time} · {len(s.rows())} 個代號"


class SessionPanel(QWidget):
    selected = Signal(str)  # session id
    rename_requested = Signal(str, str)  # session id, new label
    delete_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._sessions: dict[str, Session] = {}
        self._refreshing = False

        title = QLabel("<b>本次執行的代號檔</b>")
        hint = QLabel("雙擊重新命名 · 右鍵刪除 · 關閉軟體後全部刪除")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemDoubleClicked.connect(self.start_rename)
        self.list.itemChanged.connect(self._renamed)
        self.list.currentItemChanged.connect(self._current_changed)
        # Escape leaves the bare label in the item; put the summary back.
        self.list.itemDelegate().closeEditor.connect(lambda *_: QTimer.singleShot(0, self._redraw))

        self.preview_title = QLabel()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["代號", "原文"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(title)
        top_layout.addWidget(hint)
        top_layout.addWidget(self.list)
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self.preview_title)
        bottom_layout.addWidget(self.table)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self._show_preview(None)

    @property
    def current_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(ID) if item else None

    def refresh(self, sessions: list[Session], select: str | None = None) -> None:
        select = select or self.current_id
        self._sessions = {s.id: s for s in sessions}
        self._refreshing = True
        self.list.clear()
        for s in sessions:
            item = QListWidgetItem(_summary(s))
            item.setData(ID, s.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.list.addItem(item)
            if s.id == select:
                self.list.setCurrentItem(item)
        self._refreshing = False
        self._show_preview(self._sessions.get(self.current_id))

    def select(self, session_id: str | None) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(ID) == session_id:
                self.list.setCurrentRow(i)
                return

    def start_rename(self, item: QListWidgetItem) -> None:
        self._refreshing = True
        item.setText(self._sessions[item.data(ID)].label)  # edit the bare label
        self._refreshing = False
        self.list.editItem(item)

    def _renamed(self, item: QListWidgetItem) -> None:
        if not self._refreshing:
            self.rename_requested.emit(item.data(ID), item.text())

    def _redraw(self) -> None:
        self.refresh(list(self._sessions.values()))

    def _current_changed(self, item: QListWidgetItem | None, _prev) -> None:
        if self._refreshing:
            return
        self._show_preview(self._sessions.get(item.data(ID)) if item else None)
        if item:
            self.selected.emit(item.data(ID))

    def _show_preview(self, session: Session | None) -> None:
        rows = session.rows() if session else []
        self.preview_title.setText(f"<b>對應表</b> · {session.label}" if session else "<b>對應表</b>")
        self.table.setRowCount(len(rows))
        for r, (code, originals) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(code))
            self.table.setItem(r, 1, QTableWidgetItem(" / ".join(originals)))

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.addAction("重新命名", lambda: self.start_rename(item))
        menu.addAction("刪除", lambda: self.delete_requested.emit(item.data(ID)))
        menu.popup(self.list.viewport().mapToGlobal(pos))

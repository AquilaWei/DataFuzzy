"""Side panel listing the code files that exist for this run."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..core.mapping import Session


class SessionPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("<b>本次執行的代號檔</b>")
        hint = QLabel("關閉軟體後全部刪除")
        hint.setStyleSheet("color: gray;")
        self.list = QListWidget()
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.list)

    def refresh(self, sessions: list[Session]) -> None:
        self.list.clear()
        for s in sessions:
            time = s.created_at.split("T")[-1][:5]
            item = QListWidgetItem(f"{s.label}\n{time} · {len(s.to_code)} 筆")
            self.list.addItem(item)

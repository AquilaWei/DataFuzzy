"""Small widgets shared by the views."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget


class SegmentedControl(QWidget):
    """Two or more joined buttons of which exactly one is selected (macOS segmented control)."""

    changed = Signal(int)  # index of the newly selected segment

    def __init__(self, labels: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._buttons: list[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for i, label in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName("segment")
            button.setCheckable(True)
            position = "first" if i == 0 else "last" if i == len(labels) - 1 else "middle"
            button.setProperty("position", position)  # picked up by the stylesheet
            self._group.addButton(button, i)
            self._buttons.append(button)
            layout.addWidget(button)
        self._buttons[0].setChecked(True)
        self._group.idToggled.connect(lambda i, on: self.changed.emit(i) if on else None)

    def index(self) -> int:
        return self._group.checkedId()

    def set_index(self, index: int) -> None:
        """Select a segment; `changed` fires only if it was not selected already."""
        self._buttons[index].setChecked(True)

    def button(self, index: int) -> QPushButton:
        return self._buttons[index]

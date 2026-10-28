"""Small widgets shared by the views."""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QGuiApplication, QResizeEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from .i18n import tr

DELETE_RECORD = "刪除病歷…"
COPY_ENGLISH = "複製英文病歷"


def record_menu(parent: QWidget, on_delete: Callable[[], None],
                english: str | None = None) -> QMenu:
    """The right-click menu of a record (a card or a row of the day list). Given `english`,
    it starts with copying that chart, disabled while it is empty; delete stays last, apart."""
    menu = QMenu(parent)
    if english is not None:
        copy = menu.addAction(tr(COPY_ENGLISH))
        copy.setEnabled(bool(english.strip()))
        copy.triggered.connect(lambda: QGuiApplication.clipboard().setText(english))
        menu.addSeparator()
    menu.addAction(tr(DELETE_RECORD)).triggered.connect(on_delete)
    return menu


class SegmentedControl(QWidget):
    """Two or more joined buttons of which exactly one is selected (macOS segmented control)."""

    changed = Signal(int)  # index of the newly selected segment

    def __init__(self, labels: list[str], parent: QWidget | None = None, compact: bool = False) -> None:
        """`compact` narrows the padding, for many segments in a narrow place (the sidebar)."""
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
            button.setProperty("compact", compact)
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


class GrowingTextEdit(QPlainTextEdit):
    """A text box as tall as its text (never shorter than `min_lines`), so all of it shows
    without scrolling inside the box; the page around it scrolls instead. The height follows
    typing and rewrapping when the box gets narrower or wider.

    `floor` is a height in pixels it will not go below, for lining it up with another box."""

    fitted = Signal()  # after the height was recalculated

    def __init__(self, text: str = "", min_lines: int = 3, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.min_lines = min_lines
        self.floor = 0
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(lambda _: self.fit())
        self.fit()

    def needed_height(self) -> int:
        """Pixels to show every line, from the laid-out blocks (a wrapped block is several lines)."""
        layout = self.document().documentLayout()
        text_height = 0.0
        block = self.document().begin()
        while block.isValid():
            text_height += layout.blockBoundingRect(block).height()
            block = block.next()
        text_height = max(text_height, self.min_lines * self.fontMetrics().lineSpacing())
        margins = self.contentsMargins()
        return (math.ceil(text_height) + 2 * int(self.document().documentMargin())
                + margins.top() + margins.bottom())

    def fit(self) -> None:
        self.setFixedHeight(max(self.needed_height(), self.floor))
        self.fitted.emit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)  # rewraps the text to the new width
        if event.size().width() != event.oldSize().width():
            self.fit()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.fit()

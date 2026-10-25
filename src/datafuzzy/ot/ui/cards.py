"""Folder-style cards: a stack of overlapping cards, each showing just its top edge until the
pointer is over it, when it lifts and unfolds to preview its content."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QContextMenuEvent, QCursor, QMouseEvent, QPainter, QPalette
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from ..db import Record
from .theme import add_shadow
from .widgets import record_menu

MARGIN = 16
STEP = 56          # visible height of a folded card: its date and location line
CARD_H = 148
LIFT = 8           # how far the hovered card rises
EXPAND = CARD_H - STEP  # how far the cards below it make room
RADIUS = 14
HOVER_MS = 180
PREVIEW_LINES = 3
PREVIEW_CHARS = 140
WEEKDAYS = "一二三四五六日"


def date_label(day: date) -> str:
    return f"{day.isoformat()}  週{WEEKDAYS[day.weekday()]}"


def preview_text(zh_text: str, en_text: str) -> str:
    """The first lines of the chart (Chinese, else English) for a card."""
    text = zh_text.strip() or en_text.strip()
    if not text:
        return "（尚無內容）"
    lines = [line.strip() for line in text.splitlines() if line.strip()][:PREVIEW_LINES]
    joined = "\n".join(lines)
    return joined if len(joined) <= PREVIEW_CHARS else joined[:PREVIEW_CHARS].rstrip() + "…"


class RecordCard(QWidget):
    clicked = Signal(int)   # record id
    delete_requested = Signal(int)  # record id, from the right-click menu
    entered = Signal(int)   # index in the stack
    left = Signal(int)

    def __init__(self, record: Record, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record_id = record.id
        self.index = index
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(CARD_H)
        self.date_label = QLabel(date_label(record.visit_date))
        self.date_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.location_label = QLabel(record.location or "未填地點")
        self.location_label.setObjectName("subtle")
        self.preview_label = QLabel(preview_text(record.zh_text, record.en_text))
        self.preview_label.setWordWrap(True)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(2)
        layout.addWidget(self.date_label)
        layout.addWidget(self.location_label)
        layout.addSpacing(6)
        layout.addWidget(self.preview_label, 1)
        add_shadow(self, blur=22, dy=3, alpha=45)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.palette().color(QPalette.ColorRole.Base))
        painter.setPen(self.palette().color(QPalette.ColorRole.Mid))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)

    def enterEvent(self, event) -> None:
        self.entered.emit(self.index)

    def leaveEvent(self, event) -> None:
        self.left.emit(self.index)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.record_id)

    def context_menu(self) -> QMenu:
        return record_menu(self, lambda: self.delete_requested.emit(self.record_id))

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.context_menu().exec(event.globalPos())


class CardStack(QWidget):
    """Cards laid out top to bottom, each one overlapping the one before it.

    Hovering card k eases its `progress` to 1: it rises by LIFT and the cards below slide down
    EXPAND, so its whole body shows. Moving to another card hands the lift over."""

    clicked = Signal(int)  # record id of the card that was clicked
    delete_requested = Signal(int)  # record id chosen for deletion from a card's menu

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cards: list[RecordCard] = []
        self.progress: list[float] = []
        self._animations: list[QVariantAnimation] = []
        self.hovered: int | None = None

    def set_records(self, records: list[Record]) -> None:
        """Replace the cards, in the order given (the first is at the top)."""
        for card in self.cards:
            card.deleteLater()
        for animation in self._animations:
            animation.stop()
            animation.deleteLater()
        self.cards = []
        self.hovered = None
        for i, record in enumerate(records):
            card = RecordCard(record, i, self)
            card.clicked.connect(self.clicked)
            card.delete_requested.connect(self.delete_requested)
            card.entered.connect(self.set_hovered)
            card.left.connect(self._card_left)
            card.show()
            self.cards.append(card)
        self.progress = [0.0] * len(self.cards)
        self._animations = []
        for i in range(len(self.cards)):
            animation = QVariantAnimation(self)
            animation.setDuration(HOVER_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.valueChanged.connect(lambda value, i=i: self._set_progress(i, value))
            self._animations.append(animation)
        self.setMinimumHeight(self._resting_height())
        self._place()

    def _resting_height(self) -> int:
        """Tall enough for any card to be hovered, so the page does not jump while it unfolds."""
        if not self.cards:
            return 0
        return 2 * MARGIN + (len(self.cards) - 1) * STEP + CARD_H + EXPAND

    def set_hovered(self, index: int | None) -> None:
        """Lift card `index` (None puts every card back), animated."""
        self.hovered = index
        for i, animation in enumerate(self._animations):
            target = 1.0 if i == index else 0.0
            running = animation.state() != QVariantAnimation.State.Stopped
            if (running and animation.endValue() == target) or (not running and self.progress[i] == target):
                continue
            animation.stop()
            animation.setStartValue(self.progress[i])
            animation.setEndValue(target)
            animation.start()

    def _card_left(self, index: int) -> None:
        # The card moves as it lifts, so a leave event can arrive with the pointer still on it.
        card = self.cards[index]
        if self.hovered == index and not card.rect().contains(card.mapFromGlobal(QCursor.pos())):
            self.set_hovered(None)

    def _set_progress(self, index: int, value: float) -> None:
        self.progress[index] = float(value)
        self._place()

    def _place(self) -> None:
        width = max(self.width() - 2 * MARGIN, 0)
        y = float(MARGIN)
        for card, progress in zip(self.cards, self.progress):
            card.setGeometry(MARGIN, round(y - LIFT * progress), width, CARD_H)
            y += STEP + EXPAND * progress

    def resizeEvent(self, event) -> None:
        self._place()

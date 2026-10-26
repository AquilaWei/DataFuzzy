"""Folder-style cards: a stack of overlapping cards, each showing just its top edge until the
pointer is over it, when it lifts and unfolds to preview its content."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import (
    QEasingCurve,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QMouseEvent,
    QPainter,
    QPalette,
    QPixmap,
    QPixmapCache,
)
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from ..db import Record
from .widgets import record_menu

MARGIN = 16
STEP = 56          # visible height of a folded card: its date and location line
CARD_H = 148
LIFT = 8           # how far the hovered card rises
EXPAND = CARD_H - STEP  # how far the cards below it make room
RADIUS = 14
HOVER_MS = 180
SHADOW_SPREAD = 9  # how far the soft shadow reaches past the card's edge
SHADOW_DY = 3
SHADOW_LAYER_ALPHA = 2  # per layer; the layers add up toward the card
PREVIEW_LINES = 3
PREVIEW_CHARS = 140
WEEKDAYS = "一二三四五六日"


def date_label(day: date) -> str:
    return f"{day.isoformat()}  週{WEEKDAYS[day.weekday()]}"


def time_label(start_time: str) -> str:
    """A stored "HH:MM" start time as "9:30 AM" ("" stays ""). Only the display changes; the
    database keeps 24-hour times."""
    if not start_time:
        return ""
    hour, minute = (int(part) for part in start_time.split(":"))
    return f"{(hour - 1) % 12 + 1}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def session_label(start_time: str, end_time: str) -> str:
    """"9:30 AM–10:00 AM", or just the start (or "") when the end is not filled in."""
    if not start_time:
        return ""
    if not end_time:
        return time_label(start_time)
    return f"{time_label(start_time)}–{time_label(end_time)}"


def preview_text(zh_text: str, en_text: str) -> str:
    """The first lines of the chart (Chinese, else English) for a card."""
    text = zh_text.strip() or en_text.strip()
    if not text:
        return "（尚無內容）"
    lines = [line.strip() for line in text.splitlines() if line.strip()][:PREVIEW_LINES]
    joined = "\n".join(lines)
    return joined if len(joined) <= PREVIEW_CHARS else joined[:PREVIEW_CHARS].rstrip() + "…"


def shadow_pixmap(size: QSize, dpr: float) -> QPixmap:
    """The soft shadow of a card of `size`, SHADOW_SPREAD larger on every side. Drawn once per
    size and kept in QPixmapCache: a QGraphicsDropShadowEffect re-blurs on every repaint, which
    made the hover animation stutter."""
    key = f"theranote-card-shadow-{size.width()}x{size.height()}@{dpr}"
    cached = QPixmap()
    if QPixmapCache.find(key, cached):
        return cached
    outer = QSize(size.width() + 2 * SHADOW_SPREAD, size.height() + 2 * SHADOW_SPREAD)
    pixmap = QPixmap(outer * dpr)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, SHADOW_LAYER_ALPHA))
    # Nested translucent layers, largest first, add up to a shadow that fades toward its edge.
    body = QRectF(SHADOW_SPREAD, SHADOW_SPREAD + SHADOW_DY, size.width(), size.height())
    for grow in range(SHADOW_SPREAD, 0, -1):
        painter.drawRoundedRect(body.adjusted(-grow, -grow, grow, grow), RADIUS + grow, RADIUS + grow)
    painter.end()
    QPixmapCache.insert(key, pixmap)
    return pixmap


class CardShadow(QWidget):
    """The shadow under one card: a sibling stacked just below it, so the card above it in the
    stack still covers it, and transparent for the mouse, so it never takes the hover."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def follow(self, card: QRect) -> None:
        self.setGeometry(card.adjusted(-SHADOW_SPREAD, -SHADOW_SPREAD, SHADOW_SPREAD, SHADOW_SPREAD))

    def paintEvent(self, event) -> None:
        card = self.size() - QSize(2 * SHADOW_SPREAD, 2 * SHADOW_SPREAD)
        QPainter(self).drawPixmap(0, 0, shadow_pixmap(card, self.devicePixelRatioF()))


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
        when = date_label(record.visit_date) + (f"  {session_label(record.start_time, record.end_time)}" if record.start_time else "")
        self.date_label = QLabel(when)
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
    EXPAND, so its whole body shows. Moving to another card hands the lift over. One animation
    moves every card, so each frame lays the stack out once."""

    clicked = Signal(int)  # record id of the card that was clicked
    delete_requested = Signal(int)  # record id chosen for deletion from a card's menu

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cards: list[RecordCard] = []
        self._shadows: list[CardShadow] = []
        self.progress: list[float] = []
        self._from: list[float] = []  # progress when the running animation started
        self._to: list[float] = []    # and where it ends
        self.hovered: int | None = None
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(HOVER_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._step)

    def set_records(self, records: list[Record]) -> None:
        """Replace the cards, in the order given (the first is at the top)."""
        self._animation.stop()
        for widget in self.cards + self._shadows:
            widget.deleteLater()
        self.cards = []
        self._shadows = []
        self.hovered = None
        for i, record in enumerate(records):
            shadow = CardShadow(self)  # created first, so it stacks under its card
            shadow.show()
            self._shadows.append(shadow)
            card = RecordCard(record, i, self)
            card.clicked.connect(self.clicked)
            card.delete_requested.connect(self.delete_requested)
            card.entered.connect(self.set_hovered)
            card.left.connect(self._card_left)
            card.show()
            self.cards.append(card)
        self.progress = [0.0] * len(self.cards)
        self._to = list(self.progress)
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
        target = [1.0 if i == index else 0.0 for i in range(len(self.cards))]
        running = self._animation.state() != QVariantAnimation.State.Stopped
        if (self._to if running else self.progress) == target:
            return
        self._animation.stop()
        self._from = list(self.progress)
        self._to = target
        self._animation.start()

    def _card_left(self, index: int) -> None:
        # The card moves as it lifts, so a leave event can arrive with the pointer still on it.
        card = self.cards[index]
        if self.hovered == index and not card.rect().contains(card.mapFromGlobal(QCursor.pos())):
            self.set_hovered(None)

    def _step(self, t: float) -> None:
        self.progress = [a + (b - a) * t for a, b in zip(self._from, self._to)]
        self._place()

    def _place(self) -> None:
        width = max(self.width() - 2 * MARGIN, 0)
        y = float(MARGIN)
        for card, shadow, progress in zip(self.cards, self._shadows, self.progress):
            card.setGeometry(MARGIN, round(y - LIFT * progress), width, CARD_H)
            shadow.follow(card.geometry())
            y += STEP + EXPAND * progress

    def resizeEvent(self, event) -> None:
        self._place()

"""The by-date page: a calendar that marks days with records, and who was seen on a day."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPalette,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QCalendarWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..db import RecordStore
from .cards import date_label, preview_text, time_label
from .i18n import tr
from .theme import ACCENT
from .widgets import SegmentedControl, record_menu


def to_qdate(day: date) -> QDate:
    return QDate(day.year, day.month, day.day)


def to_date(day: QDate) -> date:
    return date(day.year(), day.month(), day.day())


class MarkedCalendar(QCalendarWidget):
    """A month calendar where days that have records are bold, tinted and accent-coloured."""

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setGridVisible(False)
        self.currentPageChanged.connect(lambda *_: self.refresh_markers())
        self.refresh_markers()

    def refresh_markers(self) -> None:
        """Re-read which days of the shown month (and the neighbouring days the grid also
        shows) have records. Call after records are added."""
        first = date(self.yearShown(), self.monthShown(), 1)
        last = (first + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        marked = self.store.dates_with_records(first - timedelta(days=7), last + timedelta(days=7))
        self.setDateTextFormat(QDate(), QTextCharFormat())  # an invalid date clears every format
        tint = QColor(ACCENT)
        tint.setAlpha(45)
        for day in marked:
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            fmt.setForeground(QColor(ACCENT))
            fmt.setBackground(tint)
            self.setDateTextFormat(to_qdate(day), fmt)

    def marked_dates(self) -> set[date]:
        return {to_date(d) for d, fmt in self.dateTextFormat().items()
                if fmt.fontWeight() == QFont.Weight.Bold}

    def selected(self) -> date:
        return to_date(self.selectedDate())


NAME_ROLE = Qt.ItemDataRole.UserRole + 1
PLACE_ROLE = Qt.ItemDataRole.UserRole + 2  # the tag: the location, or the date in the by-location list
PREVIEW_ROLE = Qt.ItemDataRole.UserRole + 3
TIME_ROLE = Qt.ItemDataRole.UserRole + 4  # (start, end) as shown, e.g. ("9:30 AM", "10:00 AM"), or ("", "")


class DayRecordDelegate(QStyledItemDelegate):
    """A row of the day list in distinct looks, so they are not read as one another: the
    session time in its own column at the left (start in accent bold, end under it), then the
    student's name in bold, the location as a small accent-tinted tag, and the start of the
    chart in grey."""

    PAD_X, PAD_Y, GAP, TAG_PAD = 12, 8, 4, 6
    BAR_W, BAR_GAP = 3, 12  # the accent bar between the time column and the rest

    def _time_font(self, option: QStyleOptionViewItem) -> QFont:
        font = QFont(option.font)
        font.setPointSizeF(font.pointSizeF() + 1)
        font.setWeight(QFont.Weight.Bold)
        return font

    def time_column_width(self, option: QStyleOptionViewItem) -> int:
        """Wide enough for the longest time, so every row's name starts at the same place."""
        return QFontMetrics(self._time_font(option)).horizontalAdvance("12:59 PM") + 4

    def _fonts(self, option: QStyleOptionViewItem) -> tuple[QFont, QFont, QFont]:
        name = QFont(option.font)
        name.setPointSizeF(name.pointSizeF() + 2)
        name.setWeight(QFont.Weight.Bold)
        tag = QFont(option.font)
        tag.setPointSizeF(tag.pointSizeF() - 1)
        return name, tag, QFont(option.font)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        name, tag, body = self._fonts(option)
        second = max(QFontMetrics(tag).height() + 4, QFontMetrics(body).height())
        return QSize(option.rect.width(), 2 * self.PAD_Y + QFontMetrics(name).height() + self.GAP + second)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style:  # hover and selection backgrounds from the stylesheet
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, opt.widget)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        palette = opt.palette
        text = palette.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text)
        grey = text if selected else palette.color(QPalette.ColorRole.PlaceholderText)
        name_font, tag_font, body_font = self._fonts(opt)
        r = opt.rect.adjusted(self.PAD_X, self.PAD_Y, -self.PAD_X, -self.PAD_Y)
        name_h = QFontMetrics(name_font).height()
        top = r.top() + name_h + self.GAP
        tag_fm = QFontMetrics(tag_font)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = text if selected else QColor(ACCENT)
        start, end = index.data(TIME_ROLE) or ("", "")
        column = QRect(r.left(), r.top(), self.time_column_width(opt), r.height())
        if start:
            painter.setFont(self._time_font(opt))
            painter.setPen(accent)
            painter.drawText(QRect(column.left(), r.top(), column.width(), name_h),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, start)
            painter.setFont(tag_font)
            painter.setPen(grey)
            painter.drawText(QRect(column.left(), top, column.width(), tag_fm.height() + 4),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, end)
        else:
            painter.setFont(tag_font)
            painter.setPen(grey)
            painter.drawText(QRect(column.left(), r.top(), column.width(), name_h),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, tr("未填時間"))
        bar = QColor(accent if start else grey)
        bar.setAlpha(255 if start else 90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bar)
        painter.drawRoundedRect(QRect(column.right() + self.BAR_GAP, r.top() + 2, self.BAR_W, r.height() - 4), 1.5, 1.5)
        r.setLeft(column.right() + 2 * self.BAR_GAP + self.BAR_W)

        painter.setFont(name_font)
        painter.setPen(text)
        painter.drawText(QRect(r.left(), r.top(), r.width(), name_h),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, index.data(NAME_ROLE))

        place = index.data(PLACE_ROLE)
        tag_rect = QRect(r.left(), top, tag_fm.horizontalAdvance(place) + 2 * self.TAG_PAD, tag_fm.height() + 4)
        fill = QColor(text if selected else ACCENT)
        fill.setAlpha(50 if selected else 36)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(tag_rect, 5, 5)
        painter.setFont(tag_font)
        painter.setPen(text if selected else QColor(ACCENT))
        painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, place)

        body_left = tag_rect.right() + 10
        body_rect = QRect(body_left, top, r.right() - body_left, tag_rect.height())
        painter.setFont(body_font)
        painter.setPen(grey)
        preview = QFontMetrics(body_font).elidedText(index.data(PREVIEW_ROLE), Qt.TextElideMode.ElideRight,
                                                    body_rect.width())
        painter.drawText(body_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, preview)
        painter.restore()


BY_TIME, BY_NAME = range(2)


class DayRecordsView(QWidget):
    """The children with a record on one day, by start time (those without one last) or by
    name; clicking one opens the record."""

    open_record = Signal(int)  # record id
    delete_record = Signal(int)  # record id chosen from a row's right-click menu

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.day: date | None = None
        self.title = QLabel("")
        self.title.setObjectName("title")
        self.count = QLabel("")
        self.count.setObjectName("subtle")
        self.sort = SegmentedControl([tr("依時間"), tr("依名字")])
        self.empty = QLabel(tr("這天沒有病歷。"))
        self.empty.setObjectName("subtle")
        self.list = QListWidget()
        self.list.setSpacing(4)
        self.list.setItemDelegate(DayRecordDelegate(self.list))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(0)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(self.title)
        titles.addWidget(self.count)
        header = QHBoxLayout()
        header.addLayout(titles, 1)
        header.addWidget(self.sort)
        layout.addLayout(header)
        layout.addSpacing(10)
        layout.addWidget(self.empty)
        layout.addWidget(self.list, 1)
        self.list.itemClicked.connect(lambda item: self.open_record.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)
        self.empty.setVisible(False)
        self.sort.changed.connect(lambda _: self.refresh())

    def context_menu(self, pos: QPoint) -> QMenu | None:
        """The menu for the row at `pos` (list viewport coordinates), None off the rows."""
        item = self.list.itemAt(pos)
        if item is None:
            return None
        record_id = item.data(Qt.ItemDataRole.UserRole)
        return record_menu(self, lambda: self.delete_record.emit(record_id))

    def _show_menu(self, pos: QPoint) -> None:
        if menu := self.context_menu(pos):
            menu.exec(self.list.viewport().mapToGlobal(pos))

    def show_day(self, day: date) -> None:
        self.day = day
        self.refresh()

    def refresh(self) -> None:
        if self.day is None:
            return
        names = {s.id: s.name for s in self.store.students_on(self.day)}  # sorted by name
        order = {student_id: i for i, student_id in enumerate(names)}
        records = sorted(self.store.records_on(self.day), key=lambda r: order[r.student_id])
        if self.sort.index() == BY_TIME:  # stable, so equal times stay in name order
            records.sort(key=lambda r: r.start_time or "99:99")
        self.title.setText(date_label(self.day))
        self.count.setText(tr("{count} 位學生有病歷", count=len(records)))
        self.list.clear()
        for record in records:
            place = record.location or tr("未填地點")
            first_line = preview_text(record.zh_text, record.en_text).splitlines()[0]
            item = QListWidgetItem(f"{names[record.student_id]}\n{place} · {first_line}")
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setData(NAME_ROLE, names[record.student_id])
            item.setData(PLACE_ROLE, place)
            item.setData(PREVIEW_ROLE, first_line)
            item.setData(TIME_ROLE, (time_label(record.start_time), time_label(record.end_time)))
            self.list.addItem(item)
        self.empty.setVisible(not records)
        self.list.setVisible(bool(records))

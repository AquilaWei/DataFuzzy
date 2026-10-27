"""The by-location page: the students seen at one place; click one to see all of their
records, at every place, newest first."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..db import RecordStore, StudentProfile
from .cards import date_label, preview_text, time_label
from .date_view import NAME_ROLE, PLACE_ROLE, PREVIEW_ROLE, TIME_ROLE, DayRecordDelegate
from .i18n import tr
from .profile_dialog import sessions_text
from .theme import ACCENT
from .widgets import record_menu

NO_LOCATION = "未填地點"
DETAILS_ROLE = Qt.ItemDataRole.UserRole + 1  # [(label, value), …] of the profile, "" when not filled
SESSIONS_ROLE = Qt.ItemDataRole.UserRole + 2  # the weekly session times as text, "" when none
INACTIVE_ROLE = Qt.ItemDataRole.UserRole + 3
PROFILE_FIELDS = (("Diagnosis", "diagnosis"), ("Age", "age"), ("Grade", "grade"), ("Classroom", "classroom"))


def profile_details(profile: StudentProfile) -> list[tuple[str, str]]:
    """The fields shown under a student's name, in this order, "—" standing in for an empty one
    so every row has its values in the same places."""
    return [(label, getattr(profile, field) or "—") for label, field in PROFILE_FIELDS]


class StudentRowDelegate(QStyledItemDelegate):
    """A student of the by-location list as a card: the name large and bold, then the profile's
    Diagnosis, Age, Grade and Classroom (label in grey, value in the text colour), then the weekly
    session times if any."""

    PAD_X, PAD_Y, GAP, PAIR_GAP = 14, 10, 5, 18

    def _fonts(self, option: QStyleOptionViewItem) -> tuple[QFont, QFont, QFont]:
        name = QFont(option.font)
        name.setPointSizeF(name.pointSizeF() + 3)
        name.setWeight(QFont.Weight.Bold)
        value = QFont(option.font)
        value.setWeight(QFont.Weight.DemiBold)
        small = QFont(option.font)
        small.setPointSizeF(small.pointSizeF() - 1)
        return name, value, small

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        name, value, small = self._fonts(option)
        height = 2 * self.PAD_Y + QFontMetrics(name).height() + self.GAP + QFontMetrics(value).height()
        if index.data(SESSIONS_ROLE):
            height += self.GAP + QFontMetrics(small).height()
        return QSize(option.rect.width(), height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        hovered = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        palette = QGuiApplication.palette()  # the list's own Base is transparent (stylesheet)
        text = palette.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text)
        grey = text if selected else palette.color(QPalette.ColorRole.PlaceholderText)
        name_font, value_font, small_font = self._fonts(opt)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = opt.rect.adjusted(1, 1, -1, -1)
        painter.setPen(QColor(palette.color(QPalette.ColorRole.Mid)))
        painter.setBrush(palette.color(QPalette.ColorRole.Highlight if selected
                                       else QPalette.ColorRole.Midlight if hovered else QPalette.ColorRole.Base))
        painter.drawRoundedRect(card, 8, 8)
        inactive = bool(index.data(INACTIVE_ROLE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grey if inactive else (text if selected else QColor(ACCENT)))
        painter.drawRoundedRect(QRect(card.left() + 6, card.top() + 8, 3, card.height() - 16), 1.5, 1.5)

        r = card.adjusted(self.PAD_X, self.PAD_Y - 1, -self.PAD_X, -self.PAD_Y + 1)
        name_h = QFontMetrics(name_font).height()
        painter.setFont(name_font)
        painter.setPen(grey if inactive else text)
        name = opt.text if not inactive else tr("{name}（停用）", name=opt.text)
        painter.drawText(QRect(r.left(), r.top(), r.width(), name_h),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        top = r.top() + name_h + self.GAP
        line_h = QFontMetrics(value_font).height()
        x = r.left()
        for label, value in index.data(DETAILS_ROLE) or []:
            for font, colour, part in ((small_font, grey, label + " "), (value_font, text, value)):
                metrics = QFontMetrics(font)
                room = r.right() - x
                if room <= 0:
                    break
                shown = metrics.elidedText(part, Qt.TextElideMode.ElideRight, room)
                painter.setFont(font)
                painter.setPen(colour)
                painter.drawText(QRect(x, top, room, line_h),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, shown)
                x += metrics.horizontalAdvance(shown)
            x += self.PAIR_GAP

        if sessions := index.data(SESSIONS_ROLE):
            top += line_h + self.GAP
            metrics = QFontMetrics(small_font)
            painter.setFont(small_font)
            painter.setPen(grey)
            painter.drawText(QRect(r.left(), top, r.width(), metrics.height()),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             metrics.elidedText(tr("看診時段") + "  " + sessions, Qt.TextElideMode.ElideRight,
                                                r.width()))
        painter.restore()


class LocationRecordsView(QWidget):
    """First a list of student names (most recently seen first). A student's records, from
    every location, look like the day list's rows with the date in bold where the name would be."""

    open_record = Signal(int)  # record id
    delete_record = Signal(int)  # record id chosen from a row's right-click menu

    def __init__(self, store: RecordStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.location: str | None = None
        self.student_id: int | None = None  # the student whose records are shown, if any
        self.back_btn = QPushButton(tr("‹ 學生"))
        self.back_btn.setObjectName("flat")
        self.back_btn.setToolTip(tr("回到這個地點的學生清單"))
        self.back_btn.clicked.connect(lambda: self.show_student(None))
        self.title = QLabel("")
        self.title.setObjectName("title")
        self.count = QLabel("")
        self.count.setObjectName("subtle")
        self.students = QListWidget()
        self.students.setSpacing(3)
        self.students.setItemDelegate(StudentRowDelegate(self.students))
        self.list = QListWidget()
        self.list.setSpacing(4)
        self.list.setItemDelegate(DayRecordDelegate(self.list))
        self.pages = QStackedWidget()
        self.pages.addWidget(self.students)
        self.pages.addWidget(self.list)
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        title_row.addWidget(self.back_btn)
        title_row.addWidget(self.title)
        title_row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(0)
        layout.addLayout(title_row)
        layout.addWidget(self.count)
        layout.addSpacing(10)
        layout.addWidget(self.pages, 1)
        self.students.itemClicked.connect(
            lambda item: self.show_student(item.data(Qt.ItemDataRole.UserRole)))
        self.list.itemClicked.connect(lambda item: self.open_record.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)

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

    def show_location(self, location: str | None) -> None:
        """`location` "" means the records without one; None shows nothing. A new location
        starts at its student list; the same one keeps the student being looked at."""
        if location != self.location:
            self.student_id = None
        self.location = location
        self.refresh()

    def show_student(self, student_id: int | None) -> None:
        """Show that student's records at this location, or the student list for None."""
        self.student_id = student_id
        self.refresh()

    def refresh(self) -> None:
        self.students.clear()
        self.list.clear()
        if self.location is None:
            self.title.setText("")
            self.count.setText("")
            self.back_btn.hide()
            return
        students = {s.id: s for s in self.store.students()}
        names = {sid: s.name for sid, s in students.items()}
        seen = self.store.students_at(self.location)
        if self.student_id not in seen:
            self.student_id = None  # deleted, or no longer seen here
        place = self.location or tr(NO_LOCATION)
        self.back_btn.setVisible(self.student_id is not None)
        if self.student_id is None:
            self.pages.setCurrentWidget(self.students)
            self.title.setText(place)
            self.count.setText(tr("{count} 位學生", count=len(seen)))
            # Inactive students last, as in the main student list; otherwise most recently seen first.
            for student_id in sorted(seen, key=lambda sid: not students[sid].active):
                profile = self.store.get_profile(student_id)
                item = QListWidgetItem(names[student_id])
                item.setData(Qt.ItemDataRole.UserRole, student_id)
                item.setData(DETAILS_ROLE, profile_details(profile))
                item.setData(SESSIONS_ROLE, sessions_text(profile.sessions))
                item.setData(INACTIVE_ROLE, not students[student_id].active)
                self.students.addItem(item)
            return
        self.pages.setCurrentWidget(self.list)
        records = self.store.records_for_student(self.student_id)
        self.title.setText(names[self.student_id])
        self.count.setText(tr("{count} 份病歷（所有地點）", count=len(records)))
        for record in records:
            first_line = preview_text(record.zh_text, record.en_text).splitlines()[0]
            item = QListWidgetItem(f"{record.visit_date.isoformat()}\n{record.location} · {first_line}")
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setData(NAME_ROLE, date_label(record.visit_date))
            item.setData(PLACE_ROLE, record.location or tr(NO_LOCATION))
            item.setData(PREVIEW_ROLE, first_line)
            item.setData(TIME_ROLE, (time_label(record.start_time), time_label(record.end_time)))
            self.list.addItem(item)

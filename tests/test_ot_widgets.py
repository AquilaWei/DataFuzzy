from PySide6.QtCore import QDate, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QDateEdit

from datafuzzy.ot.ui.widgets import ignore_wheel_on_pickers


def _wheel_down(qapp, widget):
    event = QWheelEvent(QPointF(5, 5), QPointF(widget.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    qapp.sendEvent(widget, event)


def test_wheel_over_a_drop_down_keeps_its_choice(qapp):
    ignore_wheel_on_pickers(qapp)
    box = QComboBox()
    box.addItems(["met", "not met", "not addressed"])
    box.show()
    _wheel_down(qapp, box)
    assert box.currentIndex() == 0


def test_wheel_over_a_date_field_keeps_its_date(qapp):
    ignore_wheel_on_pickers(qapp)
    edit = QDateEdit(QDate(2026, 11, 2))
    edit.show()
    _wheel_down(qapp, edit)
    assert edit.date() == QDate(2026, 11, 2)


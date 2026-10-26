from datetime import date

from PySide6.QtCore import QDate

from datafuzzy.ot.db import StudentProfile
from datafuzzy.ot.ui.profile_dialog import StudentProfileDialog


def test_dialog_starts_from_the_saved_profile(qtbot):
    saved = StudentProfile(diagnosis="ADHD, ODD", age="8", grade="3", classroom="301",
                           case_manager="Ms. Lee", school_year="09/2025-06/2026", goals="Fine motor",
                           location="新竹國小")
    dialog = StudentProfileDialog("王小明", saved, today=date(2026, 10, 26))
    qtbot.addWidget(dialog)
    assert dialog.profile() == saved


def test_new_profile_starts_with_the_current_school_year(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 26))
    qtbot.addWidget(dialog)
    assert dialog.profile().school_year == "09/2026-06/2027"


def test_school_year_months_are_picked_by_month_and_year(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 26))
    qtbot.addWidget(dialog)
    dialog.year_from.setDate(QDate(2026, 8, 1))
    dialog.year_to.setDate(QDate(2027, 7, 1))
    assert dialog.profile().school_year == "08/2026-07/2027"


def test_location_drop_down_offers_the_known_locations(qtbot):
    dialog = StudentProfileDialog("王小明", StudentProfile(), today=date(2026, 10, 26),
                                  locations=["A校", "B校"])
    qtbot.addWidget(dialog)
    assert [dialog.location.itemText(i) for i in range(dialog.location.count())] == ["A校", "B校"]
    dialog.location.setEditText("C校")
    assert dialog.profile().location == "C校"

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from datafuzzy.ot.ui.theme import add_shadow, apply_theme, palette_for


def test_light_scheme_has_white_cards_on_light_grey_window():
    palette = palette_for(Qt.ColorScheme.Light)
    assert (palette.color(QPalette.ColorRole.Base).name(), palette.color(QPalette.ColorRole.Window).name()) == (
        "#ffffff", "#f5f5f7")


def test_dark_scheme_has_dark_cards_and_light_text():
    palette = palette_for(Qt.ColorScheme.Dark)
    assert (palette.color(QPalette.ColorRole.Base).name(), palette.color(QPalette.ColorRole.Text).name()) == (
        "#2c2c2e", "#f5f5f7")


def test_unknown_scheme_falls_back_to_light():
    assert palette_for(Qt.ColorScheme.Unknown).color(QPalette.ColorRole.Base).name() == "#ffffff"


def test_apply_theme_sets_palette_based_stylesheet(qapp):
    apply_theme(qapp)
    assert "palette(base)" in qapp.styleSheet()


def test_apply_theme_sets_the_light_palette_when_system_has_no_scheme(qapp):
    apply_theme(qapp)
    assert qapp.palette().color(QPalette.ColorRole.Base).name() == "#ffffff"


def test_shadow_is_a_soft_drop_shadow_on_the_widget(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    effect = add_shadow(widget, blur=30)
    assert isinstance(widget.graphicsEffect(), QGraphicsDropShadowEffect)
    assert effect.blurRadius() == 30

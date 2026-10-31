from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

from datafuzzy.ot.ui import theme
from datafuzzy.ot.ui.theme import apply_theme, palette_for


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


def test_date_fields_show_a_calendar_icon():
    assert theme.CALENDAR_ICON.is_file()
    assert theme.CALENDAR_ICON.with_name("calendar@2x.png").is_file()
    assert theme.CALENDAR_ICON.as_posix() in theme.stylesheet()


def test_time_fields_show_a_clock_icon():
    assert theme.CLOCK_ICON.is_file()
    assert theme.CLOCK_ICON.with_name("clock@2x.png").is_file()
    assert theme.CLOCK_ICON.as_posix() in theme.stylesheet()


def test_location_fields_show_a_pin_icon():
    assert theme.PLACE_ICON.is_file()
    assert theme.PLACE_ICON.with_name("place@2x.png").is_file()
    assert theme.PLACE_ICON.as_posix() in theme.stylesheet()


def test_other_drop_downs_show_a_chevron():
    assert theme.CHEVRON_ICON.is_file()
    assert theme.CHEVRON_ICON.with_name("chevron@2x.png").is_file()
    assert f'QComboBox::down-arrow {{ image: url("{theme.CHEVRON_ICON.as_posix()}")' in theme.stylesheet()

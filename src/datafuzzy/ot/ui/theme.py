"""Apple-style look: system font, rounded controls, soft shadows, light or dark with the system.

The stylesheet only refers to palette roles (`palette(base)`...), so switching between light
and dark means swapping the palette; nothing is repainted by hand.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#0a84ff"
CALENDAR_ICON = Path(__file__).with_name("calendar.png")  # Qt picks calendar@2x.png on Retina
CLOCK_ICON = Path(__file__).with_name("clock.png")
PLACE_ICON = Path(__file__).with_name("place.png")

# role -> (light, dark)
COLORS: dict[QPalette.ColorRole, tuple[str, str]] = {
    QPalette.ColorRole.Window: ("#f5f5f7", "#1c1c1e"),
    QPalette.ColorRole.WindowText: ("#1d1d1f", "#f5f5f7"),
    QPalette.ColorRole.Base: ("#ffffff", "#2c2c2e"),
    QPalette.ColorRole.AlternateBase: ("#ebebf0", "#262628"),  # the sidebar
    QPalette.ColorRole.Text: ("#1d1d1f", "#f5f5f7"),
    QPalette.ColorRole.PlaceholderText: ("#8e8e93", "#8e8e93"),
    QPalette.ColorRole.Button: ("#ffffff", "#3a3a3c"),
    QPalette.ColorRole.ButtonText: ("#1d1d1f", "#f5f5f7"),
    QPalette.ColorRole.Mid: ("#d2d2d7", "#48484a"),  # hairline borders
    QPalette.ColorRole.Midlight: ("#e5e5ea", "#3a3a3c"),  # hover fill
    QPalette.ColorRole.Highlight: (ACCENT, ACCENT),
    QPalette.ColorRole.HighlightedText: ("#ffffff", "#ffffff"),
    QPalette.ColorRole.Link: (ACCENT, "#64a8ff"),
    QPalette.ColorRole.ToolTipBase: ("#ffffff", "#3a3a3c"),
    QPalette.ColorRole.ToolTipText: ("#1d1d1f", "#f5f5f7"),
}

STYLESHEET = """
QMainWindow, QDialog { background: palette(window); }
#Sidebar { background: palette(alternate-base); border-right: 1px solid palette(mid); }
#Content { background: palette(window); }
QLabel#title { font-size: 20px; font-weight: 600; }
QLabel#subtle { color: palette(placeholder-text); }

QPushButton {
    background: palette(button); color: palette(button-text);
    border: 1px solid palette(mid); border-radius: 8px; padding: 6px 14px;
}
QPushButton:hover { background: palette(midlight); }
QPushButton:pressed { background: palette(mid); }
QPushButton:disabled { color: palette(placeholder-text); }
QPushButton#primary {
    background: palette(highlight); color: palette(highlighted-text); border: none;
}
QPushButton#primary:hover { background: #3b9bff; }
QPushButton#primary:disabled { background: palette(mid); }
QPushButton#segment {
    border-radius: 0; border: 1px solid palette(mid); padding: 5px 16px; margin-left: -1px;
}
QPushButton#segment:checked { background: palette(highlight); color: palette(highlighted-text); }
QPushButton#segment[position="first"] {
    border-top-left-radius: 8px; border-bottom-left-radius: 8px; margin-left: 0;
}
QPushButton#segment[position="last"] { border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
QPushButton#flat { background: transparent; border: none; color: palette(highlight); padding: 4px 6px; }
QPushButton#flat:hover { background: palette(midlight); }

QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { border-radius: 8px; padding: 8px 10px; margin: 1px 6px; }
QListWidget::item:hover { background: palette(midlight); }
QListWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }

QPlainTextEdit, QLineEdit, QTextBrowser, QComboBox, QDateEdit {
    background: palette(base); color: palette(text);
    border: 1px solid palette(mid); border-radius: 8px; padding: 6px 8px;
    selection-background-color: palette(highlight);
}
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: palette(base); border: 1px solid palette(mid); border-radius: 8px;
    selection-background-color: palette(highlight);
}

QTabWidget::pane { border: none; top: 6px; }
QTabBar::tab {
    background: transparent; color: palette(placeholder-text);
    padding: 6px 16px; border-radius: 8px; margin-right: 4px;
}
QTabBar::tab:selected { background: palette(midlight); color: palette(text); }

QCalendarWidget QWidget { background: transparent; }
QCalendarWidget QAbstractItemView {
    background: palette(base); color: palette(text); selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text); outline: none;
}
QCalendarWidget QToolButton { border-radius: 8px; padding: 4px 8px; color: palette(text); }
QCalendarWidget QToolButton:hover { background: palette(midlight); }
QScrollArea { border: none; background: transparent; }
"""


def stylesheet() -> str:
    """STYLESHEET plus the rules that need a file path: a calendar icon on date fields and
    a clock on time fields (combo boxes named "time") and a pin on location fields (named
    "place"), so it is clear what clicking there opens."""
    calendar, clock, place = CALENDAR_ICON.as_posix(), CLOCK_ICON.as_posix(), PLACE_ICON.as_posix()
    return STYLESHEET + (
        "QDateEdit::drop-down, QComboBox#time::drop-down, QComboBox#place::drop-down"
        " { border: none; width: 26px; }\n"
        f"QDateEdit::down-arrow {{ image: url(\"{calendar}\"); width: 16px; height: 16px; }}\n"
        f"QComboBox#time::down-arrow {{ image: url(\"{clock}\"); width: 16px; height: 16px; }}\n"
        f"QComboBox#place::down-arrow {{ image: url(\"{place}\"); width: 16px; height: 16px; }}\n")


def is_dark(scheme: Qt.ColorScheme) -> bool:
    """Unknown (no system setting, e.g. headless) is treated as light."""
    return scheme == Qt.ColorScheme.Dark


def palette_for(scheme: Qt.ColorScheme) -> QPalette:
    index = 1 if is_dark(scheme) else 0
    palette = QPalette()
    for role, colors in COLORS.items():
        palette.setColor(role, QColor(colors[index]))
    return palette


def apply_theme(app: QApplication) -> None:
    """Fusion style (the same look on every platform) with our palette and stylesheet, kept
    in step with the system's light/dark setting while the app runs."""
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())
    hints = QGuiApplication.styleHints()
    app.setPalette(palette_for(hints.colorScheme()))
    hints.colorSchemeChanged.connect(lambda scheme: app.setPalette(palette_for(scheme)))

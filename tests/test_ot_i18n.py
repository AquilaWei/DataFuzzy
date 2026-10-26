import ast
import importlib
from datetime import date
from pathlib import Path

import pytest

from datafuzzy.core.pipeline import Pipeline
from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.ui import i18n
from datafuzzy.ot.ui.cards import date_label, preview_text
from datafuzzy.ot.ui.i18n import (
    ENGLISH,
    language,
    load_language,
    save_language,
    set_language,
    tr,
)
from datafuzzy.ot.ui.main_window import TheraNoteWindow
from datafuzzy.ot.ui.settings_dialog import SettingsDialog

UI = Path(i18n.__file__).parent
KEY = bytes(range(32))


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


def translated_texts():
    """Every text passed to tr in the interface: literals, and module constants by name."""
    for path in sorted(UI.glob("*.py")):
        module = importlib.import_module(f"datafuzzy.ot.ui.{path.stem}")
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant):
                    yield path.name, arg.value
                elif isinstance(arg, ast.Name) and isinstance(getattr(module, arg.id, None), str):
                    yield path.name, getattr(module, arg.id)


def test_every_interface_text_has_an_english_version():
    missing = [(name, text) for name, text in translated_texts() if text not in ENGLISH]
    assert missing == []


def test_the_texts_are_found():
    assert ("main_window.py", "新增學生") in set(translated_texts())


def test_english_versions_keep_the_fields_to_fill_in():
    assert tr("{count} 份病歷", count=3) == "3 份病歷"
    set_language("en")
    assert tr("{count} 份病歷", count=3) == "3 charts"


def test_chinese_is_the_default():
    load_language()
    assert language() == "zh"


def test_a_saved_language_is_used_next_time():
    save_language("en")
    set_language("zh")
    load_language()
    assert language() == "en"


def test_an_unknown_language_is_refused():
    with pytest.raises(ValueError):
        set_language("fr")


def test_preview_shows_chinese_first_in_chinese():
    assert preview_text("中文內容", "English text") == "中文內容"


def test_preview_shows_english_first_in_english():
    set_language("en")
    assert preview_text("中文內容", "English text") == "English text"


def test_preview_in_english_falls_back_to_chinese_without_an_english_version():
    set_language("en")
    assert preview_text("中文內容", "") == "中文內容"


def test_weekday_follows_the_language():
    set_language("en")
    assert date_label(date(2026, 10, 1)) == "2026-10-01  Thu"


def test_settings_dialog_starts_at_the_current_language(qtbot):
    set_language("en")
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    assert dialog.chosen_language() == "en"


def make_window(qtbot, store):
    window = TheraNoteWindow(store, Pipeline())
    qtbot.addWidget(window)
    return window


def test_window_in_english_shows_english_buttons(qtbot, store):
    set_language("en")
    window = make_window(qtbot, store)
    assert (window.add_student_btn.text(), window.settings_btn.text()) == ("Add student", "Settings")


def test_choosing_another_language_saves_it_and_asks_for_a_new_window(qtbot, store):
    window = make_window(qtbot, store)
    with qtbot.waitSignal(window.language_changed):
        assert window.open_settings("en")
    set_language("zh")
    load_language()
    assert language() == "en"


def test_keeping_the_language_changes_nothing(qtbot, store):
    window = make_window(qtbot, store)
    with qtbot.assertNotEmitted(window.language_changed):
        assert not window.open_settings("zh")


def test_a_chart_opens_on_the_english_tab_in_english(qtbot, store):
    set_language("en")
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.new_record(student_id, date(2026, 10, 1))
    assert window.editor.tabs.currentIndex() == 1


def test_a_chart_opens_on_the_chinese_tab_in_chinese(qtbot, store):
    window = make_window(qtbot, store)
    student_id = window.add_student("王小明")
    window.new_record(student_id, date(2026, 10, 1))
    assert window.editor.tabs.currentIndex() == 0

from datafuzzy import __version__
from datafuzzy.ot.ui.main_window import AboutDialog


def test_about_dialog_is_named_theranote(qtbot):
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "關於 TheraNote"


def test_about_dialog_shows_the_full_package_version(qtbot):
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    assert f"<h3>TheraNote {__version__}</h3>" in dialog.info.text()

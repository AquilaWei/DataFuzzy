"""The app's settings. For now the interface language, which also picks the language chart
previews show first."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QWidget,
)

from .i18n import LANGUAGES, language, tr


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("設定"))
        self.language_box = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_box.addItem(name, code)
        self.language_box.setCurrentIndex(self.language_box.findData(language()))
        note = QLabel(tr("病歷預覽會優先顯示這個語言的內容。"))
        note.setObjectName("subtle")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow(tr("介面語言"), self.language_box)
        form.addRow(note)
        form.addRow(buttons)

    def chosen_language(self) -> str:
        return self.language_box.currentData()

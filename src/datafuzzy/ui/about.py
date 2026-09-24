"""About dialog: version, license, and the third-party licenses bundled with packaged builds."""

from __future__ import annotations

from importlib.resources import files

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from .. import __version__

REPO = "https://github.com/AquilaWei/DataFuzzy"
NO_LICENSES = "開發版沒有附第三方授權清單；打包時由 packaging/licenses.py 產生。"


def third_party_licenses() -> str | None:
    """Written into the package by the packaging scripts; absent when running from source."""
    f = files("datafuzzy").joinpath("THIRD_PARTY_LICENSES.txt")
    return f.read_text() if f.is_file() else None


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("關於 DataFuzzy")
        self.resize(640, 480)
        self.info = QLabel(
            f"<h3>DataFuzzy {__version__}</h3>"
            "<p>在本機把文字中的機敏資訊換成代號，之後再換回來。</p>"
            f"<p>Copyright (C) 2026 AquilaWei · GPL-3.0-or-later · <a href='{REPO}'>{REPO}</a></p>"
            "<p>NER 模型不隨程式散布，由使用者在「模型管理」下載，各自適用其授權。</p>"
            "<p><b>第三方授權</b></p>")
        self.info.setOpenExternalLinks(True)
        self.info.setWordWrap(True)
        self.licenses = QPlainTextEdit(third_party_licenses() or NO_LICENSES)
        self.licenses.setReadOnly(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addWidget(self.licenses, 1)
        layout.addWidget(buttons)

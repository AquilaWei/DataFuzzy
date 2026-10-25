"""TheraNote's identity with the shared bundled-license viewer."""

from PySide6.QtWidgets import QWidget

from ... import __version__
from ...ui.about import REPO, AboutDialog as LicenseDialog
from .. import APP_NAME


class AboutDialog(LicenseDialog):
    """Show the full installed version and licenses without changing the base app dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"關於 {APP_NAME}")
        self.info.setText(
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>加密保存職能治療病歷，匯出時以可還原的代號遮蔽姓名。</p>"
            f"<p>Copyright (C) 2026 AquilaWei · GPL-3.0-or-later · <a href='{REPO}'>{REPO}</a></p>"
            "<p>以 DataFuzzy 為核心。NER 模型由使用者在「模型管理」下載，各自適用其授權。</p>"
            "<p><b>第三方授權</b></p>")

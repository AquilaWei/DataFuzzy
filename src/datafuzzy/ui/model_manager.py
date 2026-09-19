"""Dialog to download / delete the optional NER models."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..core.models import (
    ChecksumError,
    DownloadCancelled,
    ModelSpec,
    delete_model,
    download_model,
    is_installed,
)

LANG_NAMES = {"en": "英文", "zh": "中文", "any": "所有語言"}


class DownloadThread(QThread):
    progress = Signal(int, int)
    finished_with = Signal(str)  # "" on success, otherwise an error message

    def __init__(self, spec: ModelSpec, root: Path) -> None:
        super().__init__()
        self.spec = spec
        self.root = root
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            download_model(self.spec, self.root, self.progress.emit, self.cancel)
        except DownloadCancelled:
            self.finished_with.emit("已取消（下次會從中斷處繼續）")
        except ChecksumError:
            self.finished_with.emit("檔案驗證失敗，已刪除，請重新下載")
        except Exception as exc:
            self.finished_with.emit(f"下載失敗：{exc}")
        else:
            self.finished_with.emit("")


class _Row:
    def __init__(self, dialog: ModelManager, spec: ModelSpec, grid: QGridLayout, r: int) -> None:
        self.dialog = dialog
        self.spec = spec
        self.thread: DownloadThread | None = None
        info = QLabel(
            f"<b>{spec.name}</b><br>"
            f"<span style='color:gray;'>{LANG_NAMES.get(spec.lang, spec.lang)} · "
            f"{spec.size / 1e6:.0f} MB · 授權 {spec.license} · 來源 {spec.source}</span>"
        )
        self.status = QLabel()
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.button = QPushButton()
        self.button.clicked.connect(self.on_click)
        grid.addWidget(info, r, 0)
        grid.addWidget(self.status, r, 1)
        grid.addWidget(self.button, r, 2)
        grid.addWidget(self.bar, r + 1, 0, 1, 3)
        self.refresh()

    @property
    def installed(self) -> bool:
        return is_installed(self.spec, self.dialog.root)

    def refresh(self, message: str = "") -> None:
        downloading = self.thread is not None
        self.bar.setVisible(downloading)
        if downloading:
            self.button.setText("取消")
            self.status.setText("下載中…")
        elif self.installed:
            self.button.setText("刪除")
            self.status.setText(message or "✅ 已安裝")
        else:
            self.button.setText("下載")
            self.status.setText(message or "未安裝")

    def on_click(self) -> None:
        if self.thread is not None:
            self.thread.cancel.set()
        elif self.installed:
            delete_model(self.spec, self.dialog.root)
            self.dialog.models_changed.emit()
            self.refresh()
        else:
            self.start()

    def start(self) -> None:
        self.thread = DownloadThread(self.spec, self.dialog.root)
        self.thread.progress.connect(self.on_progress)
        self.thread.finished_with.connect(self.on_finished)
        self.bar.setValue(0)
        self.refresh()
        self.thread.start()

    def on_progress(self, done: int, total: int) -> None:
        self.bar.setMaximum(1000)
        self.bar.setValue(int(done / total * 1000) if total else 0)
        self.bar.setFormat(f"{done / 1e6:.0f} / {total / 1e6:.0f} MB")

    def on_finished(self, error: str) -> None:
        self.thread.wait()
        self.thread = None
        if not error:
            self.dialog.models_changed.emit()
        self.refresh(error)


class ModelManager(QDialog):
    models_changed = Signal()

    def __init__(self, specs: list[ModelSpec], root: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("模型管理")
        self.setMinimumWidth(620)
        self.root = root
        layout = QVBoxLayout(self)
        intro = QLabel(
            "模型用來辨識<b>人名、地址、生日、帳號</b>等個人資料，下載後完全在本機執行。<br>"
            "未安裝模型時仍可使用，但只會以規則偵測 Email、電話、IP 等格式化資料。<br>"
            "<span style='color:gray;'>下載模型是本軟體唯一會連網的時機。</span>"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        grid = QGridLayout()
        self.rows = [_Row(self, spec, grid, i * 2) for i, spec in enumerate(specs)]
        layout.addLayout(grid)
        location = QLabel(f"<span style='color:gray;'>存放位置：{root}</span>")
        location.setWordWrap(True)
        layout.addWidget(location)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def done(self, result: int) -> None:
        for row in self.rows:
            if row.thread is not None:
                row.thread.cancel.set()
                row.thread.wait()
        super().done(result)

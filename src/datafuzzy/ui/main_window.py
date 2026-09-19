"""Main window: mode / language / code-file pickers above a chat transcript."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.models import ModelSpec
from ..core.pipeline import ObfuscateResult, Pipeline
from ..core.store import SessionStore
from .chat_view import ChatView
from .model_manager import LANG_NAMES, ModelManager
from .session_panel import SessionPanel
from .worker import run_task

NEW_SESSION = "__new__"
LANGS = [("自動偵測", "auto"), ("English", "en"), ("中文", "zh")]


class MainWindow(QMainWindow):
    def __init__(self, pipeline: Pipeline, store: SessionStore,
                 specs: list[ModelSpec] | None = None, models_root: Path | None = None) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.store = store
        self.specs = specs or []
        self.models_root = models_root
        self._task = None
        self.setWindowTitle(f"DataFuzzy {__version__}")
        self.resize(960, 640)

        models_action = QAction("模型管理…", self)
        models_action.triggered.connect(self.open_model_manager)
        self.menuBar().addMenu("模型").addAction(models_action)

        # Top bar
        self.obfuscate_btn = QPushButton("模糊化")
        self.restore_btn = QPushButton("還原")
        self.mode_group = QButtonGroup(self)
        for btn in (self.obfuscate_btn, self.restore_btn):
            btn.setCheckable(True)
            self.mode_group.addButton(btn)
        self.obfuscate_btn.setChecked(True)
        self.mode_group.buttonToggled.connect(lambda *_: self._refresh_sessions())

        self.lang_box = QComboBox()
        for text, value in LANGS:
            self.lang_box.addItem(text, value)
        self.session_box = QComboBox()
        self.session_box.setMinimumWidth(200)
        self.model_status = QLabel()
        self.model_status.setStyleSheet("color: gray;")

        top = QHBoxLayout()
        top.addWidget(self.obfuscate_btn)
        top.addWidget(self.restore_btn)
        top.addSpacing(16)
        top.addWidget(QLabel("語言"))
        top.addWidget(self.lang_box)
        top.addSpacing(16)
        top.addWidget(QLabel("代號檔"))
        top.addWidget(self.session_box)
        top.addStretch()
        top.addWidget(self.model_status)

        # Chat + side panel
        self.chat = ChatView()
        self.chat.open_models.connect(self.open_model_manager)
        self.panel = SessionPanel()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.chat)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        # Input
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("輸入或貼上文字，按 ⌘/Ctrl + Enter 送出")
        self.input.setMaximumHeight(120)
        self.send_btn = QPushButton("送出")
        self.send_btn.clicked.connect(self.submit)
        QShortcut(QKeySequence("Ctrl+Return"), self.input, activated=self.submit)
        bottom = QHBoxLayout()
        bottom.addWidget(self.input)
        bottom.addWidget(self.send_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        layout.addLayout(bottom)
        self.setCentralWidget(root)

        self._refresh_model_status()
        self._refresh_sessions()
        self.chat.add_notice("所有處理都在本機完成。代號檔只存在於本次執行期間，關閉軟體即刪除。")

    @property
    def restoring(self) -> bool:
        return self.restore_btn.isChecked()

    @property
    def busy(self) -> bool:
        return self._task is not None

    def open_model_manager(self) -> None:
        if self.models_root is None:
            return
        dialog = ModelManager(self.specs, self.models_root, self)
        dialog.models_changed.connect(self.reload_models)
        dialog.exec()

    def reload_models(self) -> None:
        if self.models_root is not None:
            self.pipeline.load_models(self.specs, self.models_root)
        self._refresh_model_status()

    def _refresh_model_status(self) -> None:
        if not self.pipeline.models:
            self.model_status.setText("僅規則模式（尚未安裝模型）")
        else:
            names = " / ".join(LANG_NAMES.get(l, l) for l in sorted(self.pipeline.models))
            self.model_status.setText(f"已安裝模型：{names}")

    def _refresh_sessions(self, select: str | None = None) -> None:
        current = select or self.session_box.currentData()
        self.session_box.clear()
        if not self.restoring:
            self.session_box.addItem("＋ 新代號檔", NEW_SESSION)
        for s in self.store.list():
            self.session_box.addItem(f"{s.label}（{len(s.to_code)} 筆）", s.id)
        idx = self.session_box.findData(current)
        if idx >= 0:
            self.session_box.setCurrentIndex(idx)
        self.session_box.setEnabled(self.session_box.count() > 0)
        self.panel.refresh(self.store.list())

    def _set_busy(self, task) -> None:
        self._task = task
        for w in (self.send_btn, self.obfuscate_btn, self.restore_btn, self.session_box, self.lang_box):
            w.setEnabled(task is None)
        self.send_btn.setText("處理中…" if task else "送出")

    def submit(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self.busy:
            return
        if self.restoring:
            self._restore(text)
        else:
            self._obfuscate(text)
        self.input.clear()

    def _obfuscate(self, text: str) -> None:
        session_id = self.session_box.currentData()
        if session_id in (None, NEW_SESSION):
            session = self.store.new_session()
        else:
            session = self.store.sessions[session_id]
        lang = self.lang_box.currentData()
        self.chat.add_user(text, "模糊化")

        def done(result: ObfuscateResult) -> None:
            self._set_busy(None)
            self.store.save(session)
            note = f"{session.label} · 替換 {len(result.spans)} 處 · 語言 {result.lang}"
            self.chat.add_reply(result.text, result.code_spans, note)
            if not result.model_used:
                lang_name = LANG_NAMES.get(result.lang, result.lang)
                self.chat.add_notice(f"未安裝{lang_name}模型，本次只用規則偵測，人名等名稱不會被替換。",
                                     ("models:", "下載模型"))
            self._refresh_sessions(select=session.id)

        def failed(error: str) -> None:
            self._set_busy(None)
            self.chat.add_notice(f"處理失敗：{error}")
            self._refresh_sessions(select=session.id)

        self._set_busy(run_task(lambda: self.pipeline.obfuscate(text, session, lang), done, failed))

    def _restore(self, text: str) -> None:
        session_id = self.session_box.currentData()
        self.chat.add_user(text, "還原")
        if session_id is None:
            self.chat.add_notice("目前沒有代號檔，請先模糊化一段文字。")
            return
        session = self.store.sessions[session_id]
        result = self.pipeline.restore(text, session)
        note = f"{session.label} · 還原 {result.restored} 處"
        if result.unknown:
            note += " · 找不到：" + "、".join(result.unknown)
        self.chat.add_reply(result.text, note=note)

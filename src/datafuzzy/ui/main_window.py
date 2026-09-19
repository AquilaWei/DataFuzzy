"""Main window: mode / language / code-file pickers above a chat transcript."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.mapping import CODE_RE, apply_codes, recommend, revert_code
from ..core.models import ModelSpec
from ..core.pipeline import ObfuscateResult, Pipeline
from ..core.store import SessionStore
from .about import AboutDialog
from .chat_view import ChatView
from .model_manager import LANG_NAMES, ModelManager
from .session_panel import SessionPanel
from .worker import run_task

NEW_SESSION = "__new__"
LANGS = [("自動偵測", "auto"), ("English", "en"), ("中文", "zh")]
SCOPES = [("全部敏感資料", "all"), ("只處理人名", "names")]


class MainWindow(QMainWindow):
    def __init__(self, pipeline: Pipeline, store: SessionStore,
                 specs: list[ModelSpec] | None = None, models_root: Path | None = None) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.store = store
        self.specs = specs or []
        self.models_root = models_root
        self._task = None
        self._recommended: str | None = None
        self.setWindowTitle(f"DataFuzzy {__version__}")
        self.resize(960, 640)

        models_action = QAction("模型管理…", self)
        models_action.triggered.connect(self.open_model_manager)
        self.menuBar().addMenu("模型").addAction(models_action)
        about_action = QAction("關於 DataFuzzy", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)  # macOS: app menu
        about_action.triggered.connect(lambda: AboutDialog(self).exec())
        self.menuBar().addMenu("說明").addAction(about_action)

        # Top bar
        self.obfuscate_btn = QPushButton("模糊化")
        self.restore_btn = QPushButton("還原")
        self.mode_group = QButtonGroup(self)
        for btn in (self.obfuscate_btn, self.restore_btn):
            btn.setCheckable(True)
            self.mode_group.addButton(btn)
        self.obfuscate_btn.setChecked(True)
        self.mode_group.buttonToggled.connect(self._mode_changed)

        self.lang_box = QComboBox()
        for text, value in LANGS:
            self.lang_box.addItem(text, value)
        self.scope_box = QComboBox()
        for text, value in SCOPES:
            self.scope_box.addItem(text, value)
        self.scope_box.setToolTip("只處理人名：只替換人名，Email、電話、地址、公司等都保留原字")
        self.session_box = QComboBox()
        self.session_box.setMinimumWidth(200)
        self.session_box.currentIndexChanged.connect(
            lambda _: self.panel.select(self.session_box.currentData()))
        self.recommend_hint = QLabel()
        self.recommend_hint.setStyleSheet("color: gray;")
        self.recommend_hint.hide()
        self.model_status = QLabel()
        self.model_status.setStyleSheet("color: gray;")

        top = QHBoxLayout()
        top.addWidget(self.obfuscate_btn)
        top.addWidget(self.restore_btn)
        top.addSpacing(16)
        top.addWidget(QLabel("語言"))
        top.addWidget(self.lang_box)
        top.addSpacing(16)
        top.addWidget(QLabel("範圍"))
        top.addWidget(self.scope_box)
        top.addSpacing(16)
        top.addWidget(QLabel("代號檔"))
        top.addWidget(self.session_box)
        top.addStretch()
        top.addWidget(self.model_status)

        # Chat + side panel
        self.chat = ChatView()
        self.chat.open_models.connect(self.open_model_manager)
        self.chat.code_clicked.connect(self._code_menu)
        self.chat.mark_requested.connect(self.mark)
        self.panel = SessionPanel()
        self.panel.selected.connect(self._panel_selected)
        self.panel.rename_requested.connect(self.rename_session)
        self.panel.delete_requested.connect(self._confirm_delete)
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
        self.input.textChanged.connect(self._recommend)
        bottom = QHBoxLayout()
        bottom.addWidget(self.input)
        bottom.addWidget(self.send_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.recommend_hint)
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
        names = (["個資偵測"] if self.pipeline.pii else []) + \
            [LANG_NAMES.get(lang, lang) + "人名" for lang in sorted(self.pipeline.models)]
        if not names:
            self.model_status.setText("僅規則模式（尚未安裝模型）")
        else:
            self.model_status.setText(f"已安裝模型：{' / '.join(names)}")

    def _refresh_sessions(self, select: str | None = None) -> None:
        current = select or self.session_box.currentData()
        self.session_box.clear()
        if not self.restoring:
            self.session_box.addItem("＋ 新代號檔", NEW_SESSION)
        for s in self.store.list():
            self.session_box.addItem(f"{s.label}（{len(s.rows())} 個代號）", s.id)
        idx = self.session_box.findData(current)
        if idx >= 0:
            self.session_box.setCurrentIndex(idx)
        self.session_box.setEnabled(self.session_box.count() > 0 and not self.busy)
        self.panel.refresh(self.store.list(), select=self.session_box.currentData())

    def _set_busy(self, task) -> None:
        self._task = task
        for w in (self.send_btn, self.obfuscate_btn, self.restore_btn, self.session_box, self.lang_box,
                  self.scope_box):
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
        scope = self.scope_box.currentData()
        self.chat.add_user(text, "模糊化")

        def done(result: ObfuscateResult) -> None:
            self._set_busy(None)
            self.store.save(session)
            note = f"{session.label} · 替換 {len(result.spans)} 處 · 語言 {result.lang}"
            if scope == "names":
                note += " · 只處理人名"
            self.chat.add_reply(result.text, result.code_spans, note, result.originals, session.id)
            if not result.model_used:
                self.chat.add_notice("有模型未安裝，本次人名、生日、帳號等可能不會被替換。",
                                     ("models:", "下載模型"))
            self._refresh_sessions(select=session.id)

        def failed(error: str) -> None:
            self._set_busy(None)
            self.chat.add_notice(f"處理失敗：{error}")
            self._refresh_sessions(select=session.id)

        self._set_busy(run_task(lambda: self.pipeline.obfuscate(text, session, lang, scope), done, failed))

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

    def _mode_changed(self, *_) -> None:
        self._recommended = None
        self._refresh_sessions()
        self._recommend()

    def _recommend(self) -> None:
        """In restore mode, pick the code file that can restore the most codes in the input.
        Only switches when the best match changes, so a manual choice sticks while typing."""
        if not self.restoring:
            self._hint("")
            return
        text = self.input.toPlainText()
        best = recommend(text, self.store.list())
        if best is None:
            self._recommended = None
            self._hint("")
            return
        if best.id != self._recommended:
            self._recommended = best.id
            self.session_box.setCurrentIndex(self.session_box.findData(best.id))
        self._hint(f"已依代號自動選擇「{best.label}」：可還原 {best.match_count(text)} 個代號")

    def _hint(self, text: str) -> None:
        self.recommend_hint.setText(text)
        self.recommend_hint.setVisible(bool(text))

    def _panel_selected(self, session_id: str) -> None:
        idx = self.session_box.findData(session_id)
        if idx >= 0 and not self.busy:
            self.session_box.setCurrentIndex(idx)

    def rename_session(self, session_id: str, label: str) -> None:
        if session_id in self.store.sessions:
            self.store.rename(session_id, label)
        self._refresh_sessions()

    def _confirm_delete(self, session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if session is None:
            return
        answer = QMessageBox.question(
            self, "刪除代號檔", f"刪除「{session.label}」？刪除後就無法用它還原。")
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_session(session_id)

    def delete_session(self, session_id: str) -> None:
        if self.busy:  # the running task would save the file again
            self.chat.add_notice("處理中，請稍後再刪除代號檔。")
            return
        session = self.store.sessions.get(session_id)
        if session is None:
            return
        self.store.delete(session_id)
        for reply in self.chat.replies:
            if reply.session_id == session_id:
                reply.session_id = None  # its codes can no longer be un-marked
        self.chat.rerender()
        self.chat.add_notice(f"已刪除「{session.label}」。")
        self._recommended = None
        self._refresh_sessions()

    def _code_menu(self, reply_idx: int, code: str) -> None:
        reply = self.chat.replies[reply_idx]
        session = self.store.sessions.get(reply.session_id or "")
        originals = [o for o, c in session.to_code.items() if c == code] if session else []
        if not originals or self.busy:
            return
        menu = QMenu(self)
        shown = max(originals, key=len)
        menu.addAction(f"取消標記「{shown}」（不是敏感資料）", lambda: self.unmark(reply_idx, code))
        menu.popup(QCursor.pos())

    def unmark(self, reply_idx: int, code: str) -> None:
        """Treat `code`'s original as not sensitive: put it back in every reply of this code
        file, and never code it again in this code file."""
        session_id = self.chat.replies[reply_idx].session_id
        session = self.store.sessions.get(session_id or "")
        if session is None or self.busy:
            return
        originals = session.unmark(code)
        if not originals:
            return
        self.store.save(session)
        for i, reply in enumerate(self.chat.replies):
            if reply.session_id == session_id and any(s.text == code for s in reply.spans):
                self.chat.update_reply(i, *revert_code(reply.text, reply.spans, reply.originals, code))
        self.chat.rerender()
        names = "、".join(f"「{o}」" for o in originals)
        self.chat.add_notice(f"已取消標記 {names}，{session.label} 之後不會再替換它。"
                             "先前複製出去的 " + code + " 仍可還原。")
        self._refresh_sessions()

    def mark(self, reply_idx: int, text: str, label: str) -> None:
        """Code a value the detectors missed: in every reply of this code file now, and in
        everything obfuscated with it later."""
        session_id = self.chat.replies[reply_idx].session_id
        session = self.store.sessions.get(session_id or "")
        if session is None or self.busy:
            return
        if CODE_RE.search(text):
            self.chat.add_notice("選取範圍不能包含代號，請只選取漏掉的文字。")
            return
        values = session.mark(text, label)
        self.store.save(session)
        replaced = 0
        for i, reply in enumerate(self.chat.replies):
            if reply.session_id != session_id:
                continue
            new = apply_codes(reply.text, reply.spans, reply.originals, values)
            replaced += len(new[1]) - len(reply.spans)
            self.chat.update_reply(i, *new)
        self.chat.rerender()
        self.chat.add_notice(f"已將「{text}」標記為 {values[text]}，替換 {replaced} 處；"
                             f"{session.label} 之後也會自動替換。")
        self._refresh_sessions()

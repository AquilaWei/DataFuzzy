"""Asking for the password when there is no system keyring (Linux fallback).

The key is fetched on a worker thread (it can block on a system prompt); the provider's
password callback runs there too, so `PasswordPrompter` carries each request to the GUI thread
and the answer back.
"""

from __future__ import annotations

import queue
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from .. import APP_NAME
from .i18n import tr

CREATE_HINT = (f"這台電腦沒有可用的系統鑰匙圈。請設定一組密碼來保護 {APP_NAME} 的病歷。\n"
               "忘記密碼就無法讀回資料，請自行妥善保存。")
ENTER_HINT = f"輸入密碼以解鎖 {APP_NAME}。"
WRONG_PASSWORD = "密碼不正確，請再試一次。"
MISMATCH = "兩次輸入的密碼不一致。"


class PasswordDialog(QDialog):
    """Enter the password; when `creating`, enter it twice."""

    def __init__(self, creating: bool, retry: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.creating = creating
        self.setWindowTitle(tr("解鎖 {app}", app=APP_NAME))
        self.hint = QLabel(tr(CREATE_HINT if creating else ENTER_HINT))
        self.hint.setWordWrap(True)
        self.problem = QLabel(tr(WRONG_PASSWORD) if retry and not creating else "")
        self.problem.setStyleSheet("color: #ff453a;")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_btn: QPushButton = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_btn.setObjectName("primary")
        form = QFormLayout(self)
        form.addRow(self.hint)
        form.addRow(tr("密碼"), self.password_edit)
        if creating:
            form.addRow(tr("確認密碼"), self.confirm_edit)
        form.addRow(self.problem)
        form.addRow(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.password_edit.textChanged.connect(self._validate)
        self.confirm_edit.textChanged.connect(self._validate)
        self._validate()

    def _validate(self) -> None:
        password = self.password_edit.text()
        matches = not self.creating or password == self.confirm_edit.text()
        self.ok_btn.setEnabled(bool(password) and matches)
        if self.creating:
            self.problem.setText("" if matches or not self.confirm_edit.text() else tr(MISMATCH))

    def password(self) -> str:
        return self.password_edit.text()

    @staticmethod
    def ask(creating: bool, retry: bool = False) -> str | None:
        """Show the dialog; the password, or None if the user cancelled."""
        dialog = PasswordDialog(creating, retry)
        return dialog.password() if dialog.exec() == QDialog.DialogCode.Accepted else None


class PasswordPrompter(QObject):
    """Lets the key provider, running on a worker thread, ask for a password: `ask` blocks the
    worker while the dialog is shown on the GUI thread. Create it on the GUI thread."""

    _requested = Signal(bool, bool)

    def __init__(self, show: Callable[[bool, bool], str | None] = PasswordDialog.ask) -> None:
        super().__init__()
        self._show = show
        self._answers: queue.Queue[str | None] = queue.Queue()
        self._requested.connect(self._on_request)

    def ask(self, creating: bool, retry: bool) -> str | None:
        """For `PasswordKeyProvider`; call from the worker thread only (it would deadlock the
        GUI thread)."""
        self._requested.emit(creating, retry)
        return self._answers.get()

    @Slot(bool, bool)
    def _on_request(self, creating: bool, retry: bool) -> None:
        answer = None  # a failing dialog must not leave the worker waiting forever
        try:
            answer = self._show(creating, retry)
        finally:
            self._answers.put(answer)

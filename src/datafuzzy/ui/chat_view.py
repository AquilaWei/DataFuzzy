"""Conversation transcript with highlighted codes and per-reply copy links."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QTextBrowser

from ..core.detect import Span

CODE_STYLE = "background-color:#f5c451; color:#1a1a1a; border-radius:3px;"


def _html(text: str) -> str:
    return escape(text).replace("\n", "<br>")


def highlight(text: str, spans: list[Span]) -> str:
    parts: list[str] = []
    pos = 0
    for s in sorted(spans, key=lambda s: s.start):
        parts.append(_html(text[pos:s.start]))
        parts.append(f'<span style="{CODE_STYLE}" title="{escape(s.label)}">{_html(text[s.start:s.end])}</span>')
        pos = s.end
    parts.append(_html(text[pos:]))
    return "".join(parts)


class ChatView(QTextBrowser):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor)
        self._replies: list[str] = []

    def add_user(self, text: str, mode: str) -> None:
        self.append(
            f'<p style="margin-top:12px;"><b>你（{escape(mode)}）</b></p>'
            f'<p style="margin-left:12px;">{_html(text)}</p>'
        )

    def add_reply(self, text: str, spans: list[Span] | None = None, note: str = "") -> None:
        idx = len(self._replies)
        self._replies.append(text)
        body = highlight(text, spans or [])
        footer = f' <span style="color:gray;">{escape(note)}</span>' if note else ""
        self.append(
            f'<p style="margin-top:8px;"><b>DataFuzzy</b> · <a href="copy:{idx}">複製</a>{footer}</p>'
            f'<p style="margin-left:12px;">{body}</p>'
        )

    def add_notice(self, text: str) -> None:
        self.append(f'<p style="color:gray;">{_html(text)}</p>')

    def reply_text(self, idx: int) -> str:
        return self._replies[idx]

    def _on_anchor(self, url: QUrl) -> None:
        if url.scheme() == "copy":
            QGuiApplication.clipboard().setText(self._replies[int(url.path())])

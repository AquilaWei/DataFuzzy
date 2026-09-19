"""Conversation transcript with clickable codes and per-reply copy links."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QTextBrowser

from ..core.detect import Span

CODE_STYLE = "background-color:#f5c451; color:#1a1a1a; border-radius:3px;"


def _html(text: str) -> str:
    return escape(text).replace("\n", "<br>")


def highlight(text: str, spans: list[Span], link: str | None = None) -> str:
    """Mark `spans` in `text`. With `link`, each span becomes an anchor `<link>:<index>`."""
    parts: list[str] = []
    pos = 0
    for i, s in enumerate(sorted(spans, key=lambda s: s.start)):
        parts.append(_html(text[pos:s.start]))
        mark = f'<span style="{CODE_STYLE}" title="{escape(s.label)}">{_html(text[s.start:s.end])}</span>'
        if link:
            mark = f'<a href="{link}:{i}" style="text-decoration:none;">{mark}</a>'
        parts.append(mark)
        pos = s.end
    parts.append(_html(text[pos:]))
    return "".join(parts)


@dataclass
class Reply:
    text: str
    spans: list[Span] = field(default_factory=list)  # codes in `text`, sorted by position
    originals: list[str] = field(default_factory=list)  # what each code replaced
    note: str = ""
    session_id: str | None = None  # the code file an obfuscation reply belongs to


class ChatView(QTextBrowser):
    open_models = Signal()
    code_clicked = Signal(int, str)  # reply index, code

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor)
        self.replies: list[Reply] = []
        self._blocks: list[str | int] = []  # HTML, or an index into `replies`

    def add_user(self, text: str, mode: str) -> None:
        self._add(
            f'<p style="margin-top:12px;"><b>你（{escape(mode)}）</b></p>'
            f'<p style="margin-left:12px;">{_html(text)}</p>'
        )

    def add_reply(self, text: str, spans: list[Span] | None = None, note: str = "",
                  originals: list[str] | None = None, session_id: str | None = None) -> None:
        spans = sorted(spans or [], key=lambda s: s.start)
        self.replies.append(Reply(text, spans, originals or [], note, session_id))
        self._add(len(self.replies) - 1)

    def add_notice(self, text: str, link: tuple[str, str] | None = None) -> None:
        """Gray system message; `link` is (href, text) appended after it."""
        extra = f' <a href="{link[0]}">{escape(link[1])}</a>' if link else ""
        self._add(f'<p style="color:gray;">{_html(text)}{extra}</p>')

    def reply_text(self, idx: int) -> str:
        return self.replies[idx].text

    def update_reply(self, idx: int, text: str, spans: list[Span], originals: list[str]) -> None:
        reply = self.replies[idx]
        reply.text, reply.spans, reply.originals = text, spans, originals

    def rerender(self) -> None:
        """Redraw everything (after replies changed), keeping the scroll position."""
        bar = self.verticalScrollBar()
        pos = bar.value()
        self.setHtml("".join(self._render(b) for b in self._blocks))
        bar.setValue(pos)

    def _add(self, block: str | int) -> None:
        self._blocks.append(block)
        self.append(self._render(block))

    def _render(self, block: str | int) -> str:
        if isinstance(block, str):
            return block
        reply = self.replies[block]
        # Only obfuscation replies can un-mark a code; restored text has none.
        link = f"code:{block}" if reply.session_id and reply.originals else None
        body = highlight(reply.text, reply.spans, link)
        footer = f' <span style="color:gray;">{escape(reply.note)}</span>' if reply.note else ""
        hint = ' <span style="color:gray;">· 點代號可取消標記</span>' if link and reply.spans else ""
        return (
            f'<p style="margin-top:8px;"><b>DataFuzzy</b> · <a href="copy:{block}">複製</a>'
            f'{footer}{hint}</p>'
            f'<p style="margin-left:12px;">{body}</p>'
        )

    def _on_anchor(self, url: QUrl) -> None:
        if url.scheme() == "copy":
            QGuiApplication.clipboard().setText(self.replies[int(url.path())].text)
        elif url.scheme() == "code":
            idx, i = map(int, url.path().split(":"))
            self.code_clicked.emit(idx, self.replies[idx].spans[i].text)
        elif url.scheme() == "models":
            self.open_models.emit()

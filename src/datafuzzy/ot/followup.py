"""The follow-up part of a chart's comments: finding it in comments written before it had a box
of its own, and joining it to the comments (and splitting it off again) for a translation export
and the Excel sheet."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .db import Record

# The line between the comments and the follow-up in a translation export. It is kept even when
# the follow-up is empty, so the text that comes back always has the same shape.
FOLLOW_UP_MARKER = "--- FOLLOW-UP ---"
# The marker as a translator may hand it back: any case, a space or nothing for the hyphen.
_MARKER_LINE_RE = re.compile(r"^[ \t]*-{2,}[ \t]*follow[ \t-]?up[ \t]*-{2,}[ \t]*$", re.IGNORECASE | re.MULTILINE)

# How the Excel sheet introduces the follow-up, as charts wrote it before it had a box.
EXCEL_FOLLOW_UP_LABEL = "* **Follow-up:**"

# A line that starts a follow-up in an older chart: an optional bullet (*, -, •), then a label,
# optionally bold (** or __), with its colon inside or outside the bold. A label goes; the rest of
# the line stays as the follow-up's first words. "Next session" and 下次 also start sentences, so
# without a colon after them they are kept as part of the follow-up.
_LABELS = (r"(?P<label>follow[ \t-]?up|f/u|fu(?=[ \t]*[:：])|追蹤|plan(?=[ \t]*(?:\*\*|__)?[ \t]*[:：])"
           r"|(?P<sentence>next[ \t]+session|下次))")
_FOLLOW_UP_LINE_RE = re.compile(
    rf"^[ \t]*(?:[*\-•][ \t]+)?(?:\*\*|__)?[ \t]*{_LABELS}"
    r"(?P<colon>[ \t]*[:：]?[ \t]*(?:\*\*|__)?[ \t]*[:：]?)[ \t]*",
    re.IGNORECASE | re.MULTILINE)


def split_followup(text: str) -> tuple[str, str] | None:
    """(comments, follow-up) for older comments with a follow-up in them: cut at the first line
    that starts with a follow-up label (see _LABELS). None if no line does, or if nothing
    follows the label, so there is nothing to move."""
    match = _FOLLOW_UP_LINE_RE.search(text)
    if match is None:
        return None
    keeps_label = match["sentence"] and not re.search("[:：]", match["colon"])
    followup = text[match.start("label") if keeps_label else match.end():].strip()
    if not followup:
        return None
    return text[:match.start()].rstrip(), followup


def join_chart(comments: str, followup: str) -> str:
    """The comments and the follow-up as one text for a translation export, FOLLOW_UP_MARKER
    on a line between them."""
    return f"{comments.strip()}\n{FOLLOW_UP_MARKER}\n{followup.strip()}".strip()


def split_chart(text: str) -> tuple[str, str] | None:
    """(comments, follow-up) from a text made by join_chart and translated: split at the marker
    line, however the translator wrote it. None if there is no marker."""
    match = _MARKER_LINE_RE.search(text)
    if match is None:
        return None
    return text[:match.start()].strip(), text[match.end():].strip()


def excel_comment(comments: str, followup: str) -> str:
    """The comments with the follow-up after them, as one cell of the Excel sheet showed them
    before the follow-up had a box: a blank line, then EXCEL_FOLLOW_UP_LABEL."""
    if not followup.strip():
        return comments
    return f"{comments.rstrip()}\n\n{EXCEL_FOLLOW_UP_LABEL} {followup.strip()}".lstrip()


@dataclass(frozen=True)
class FollowupSplit:
    """A chart from before follow-ups had a box, with the follow-up found in its comments: the
    new texts, one or both languages split (a language with nothing found keeps its comments)."""
    record: Record
    zh_text: str
    zh_followup: str
    en_text: str
    en_followup: str

    def texts(self) -> dict[str, str]:
        """The fields for RecordStore.set_chart_texts."""
        return {"zh_text": self.zh_text, "zh_followup": self.zh_followup,
                "en_text": self.en_text, "en_followup": self.en_followup}


def followup_splits(records: Iterable[Record]) -> list[FollowupSplit]:
    """The charts whose follow-up is still empty in both languages but can be found in their
    comments (see split_followup), for the user to review before anything is moved. Only the
    comments are read."""
    found: list[FollowupSplit] = []
    for record in records:
        if record.zh_followup.strip() or record.en_followup.strip():
            continue
        zh, en = split_followup(record.zh_text), split_followup(record.en_text)
        if zh is None and en is None:
            continue
        zh_text, zh_followup = zh or (record.zh_text, "")
        en_text, en_followup = en or (record.en_text, "")
        found.append(FollowupSplit(record, zh_text, zh_followup, en_text, en_followup))
    return found

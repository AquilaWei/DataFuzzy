"""Speaker names in pasted chat logs ("張明：好的", "10:23\t張明\t好的", "[10:23] Emma: ok").

The model often misses a name standing alone at the start of a line. But when it does
recognise one speaker, the other line-start labels in the same position are very
likely people too.
"""

from __future__ import annotations

import re

from .detect import Span
from .mapping import COMMON_SURNAMES, COMPOUND_SURNAMES, PERSON

# Line-start labels that name a role or a field, not a person.
NOT_SPEAKERS = {"Note", "Notes", "Subject", "From", "To", "Cc", "Re", "Date", "Time",
                "Customer", "Manager", "Admin", "System", "User", "Me", "Q", "A"}

_PREFIX = r"^[ \t]*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?[ \t]+)?"  # optional "10:23" / "[10:23]"
_LABEL = r"([\u3400-\u9fff]{2,4}|[A-Z][a-z]+(?: [A-Z][a-z]+){0,2})"
SPEAKER_RE = re.compile(_PREFIX + _LABEL + r"(?:[ \t]*[:：]|\t)", re.MULTILINE)


def _looks_like_name(label: str) -> bool:
    if label[0].isascii():
        return label not in NOT_SPEAKERS
    return label[0] in COMMON_SURNAMES or label[:2] in COMPOUND_SURNAMES


def speaker_spans(text: str, persons: set[str]) -> list[Span]:
    """Line-start speaker labels, as PERSON spans, when at least one of them is already
    a known person (`persons`)."""
    labels = [(m.start(1), m.end(1), m.group(1)) for m in SPEAKER_RE.finditer(text)]
    if not any(label in persons for *_, label in labels):
        return []
    return [Span(s, e, PERSON, label) for s, e, label in labels
            if label in persons or _looks_like_name(label)]

"""Pick which language model to use for a piece of text."""

from __future__ import annotations

import re
from typing import Literal

Lang = Literal["en", "zh"]

# CJK Unified Ideographs + Extension A + compatibility ideographs + CJK punctuation.
_CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x3000, 0x303F))


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def detect_language(text: str, threshold: float = 0.2) -> Lang:
    """Return "zh" when CJK characters make up at least `threshold` of letters."""
    letters = [c for c in text if c.isalpha() or _is_cjk(c)]
    if not letters:
        return "en"
    ratio = sum(_is_cjk(c) for c in letters) / len(letters)
    return "zh" if ratio >= threshold else "en"


def has_cjk(text: str) -> bool:
    return any(_is_cjk(c) for c in text)


def languages_in(text: str) -> list[Lang]:
    """Every language with text worth running a model on: Chinese for any CJK character,
    English for any run of two or more ASCII letters (a name like "Li" counts)."""
    langs: list[Lang] = []
    if has_cjk(text):
        langs.append("zh")
    if re.search(r"[A-Za-z]{2}", text):
        langs.append("en")
    return langs

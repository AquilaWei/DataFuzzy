"""Rule-based detection for structured secrets (email, phone, IDs, keys...)."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass

from .base import Span

# ASCII-only boundaries: \b treats CJK characters as word chars, so "證A123456789"
# would have no boundary before "A".
_L = r"(?<![A-Za-z0-9_])"
_R = r"(?![A-Za-z0-9_])"


def _luhn_ok(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# Taiwan national ID letter codes (A=10 ... Z=33, non-sequential by design).
_TW_LETTERS = {
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14, "F": 15, "G": 16, "H": 17,
    "I": 34, "J": 18, "K": 19, "L": 20, "M": 21, "N": 22, "O": 35, "P": 23,
    "Q": 24, "R": 25, "S": 26, "T": 27, "U": 28, "V": 29, "W": 32, "X": 30,
    "Y": 31, "Z": 33,
}


def _tw_id_ok(candidate: str) -> bool:
    n = _TW_LETTERS[candidate[0].upper()]
    weights = [1, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1]
    digits = [n // 10, n % 10] + [int(c) for c in candidate[1:]]
    return sum(d * w for d, w in zip(digits, weights)) % 10 == 0


def _ipv6_ok(candidate: str) -> bool:
    if len(candidate) < 6:  # skip tiny matches such as "a::"
        return False
    try:
        ipaddress.IPv6Address(candidate)
    except ValueError:
        return False
    return True


_CJK = r"[一-鿿]"
_NUM = r"(?:[0-9０-９]+|[一二三四五六七八九十百零〇]+)"
# Place and road names don't contain these ("住在中山路", "寄到台北市"), so the match
# doesn't swallow the words in front of the address.
_ROAD_CHAR = r"(?:(?![在於到住從往的和與及跟是為至向由近了])" + _CJK + ")"
# Taiwan street address: [縣市][區鄉鎮市] road [段][巷][弄] number 號 [樓][室].
# The house number is required, so "環北路與新生路口" is not an address, and the road
# name has two or more characters, so "線路 3 號" isn't either.
TW_ADDRESS = re.compile(
    rf"(?:{_ROAD_CHAR}{{2}}[縣市])?(?:{_ROAD_CHAR}{{1,3}}?[區鄉鎮市])?"
    rf"{_ROAD_CHAR}{{2,8}}?(?:路|街|大道)"
    rf"(?:\s*{_NUM}\s*段)?(?:\s*{_NUM}\s*巷)?(?:\s*{_NUM}\s*弄)?"
    rf"\s*{_NUM}(?:\s*之\s*{_NUM})?\s*號"
    rf"(?:\s*{_NUM}\s*樓(?:\s*之\s*{_NUM})?)?(?:\s*[0-9０-９]+\s*室)?"
)


@dataclass(frozen=True)
class Rule:
    label: str
    pattern: re.Pattern[str]
    validate: Callable[[str], bool] | None = None
    group: int = 0  # capture group holding the sensitive part


RULES: list[Rule] = [
    Rule("SECRET", re.compile(
        r"(?i)(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|密碼|密鑰|金鑰)"
        r"\s*[:=：]\s*[\"']?([^\s\"'，。；;,]{4,})"
    ), group=1),
    Rule("SECRET", re.compile(
        _L + r"(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{36,}|AKIA[0-9A-Z]{16}"
        r"|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}"
        r"|eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})" + _R
    )),
    Rule("URL", re.compile(r"https?://[^\s<>\"'，。、；）」』)\]]+")),
    Rule("EMAIL", re.compile(_L + r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}" + _R)),
    Rule("TWID", re.compile(_L + r"[A-Za-z][1289]\d{8}" + _R), _tw_id_ok),
    Rule("CARD", re.compile(_L + r"\d(?:[ -]?\d){12,18}" + _R), _luhn_ok),
    Rule("IP", re.compile(
        _L + r"(?<!\d\.)(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}" + r"(?![\d.]*\d)"
    )),
    Rule("IP", re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Fa-f:])"), _ipv6_ok),
    Rule("PHONE", re.compile(
        r"(?<![\d+])(?:"
        r"\+886[\s-]?9\d{2}[\s-]?\d{3}[\s-]?\d{3}"      # TW mobile, international
        r"|09\d{2}[\s-]?\d{3}[\s-]?\d{3}"                # TW mobile
        r"|\(0\d{1,2}\)\s?\d{3,4}[\s-]?\d{4}"            # TW landline (02) 2345-6789
        r"|0\d{1,2}-\d{3,4}-?\d{4}"                      # TW landline 02-2345-6789
        r"|\+\d{1,3}[\s-]?\(?\d{1,4}\)?(?:[\s-]?\d{2,4}){2,3}"  # generic international
        r"|\(\d{3}\)\s?\d{3}-\d{4}|\d{3}-\d{3}-\d{4}"    # North America
        r")(?!\d)"
    )),
    Rule("LOC", TW_ADDRESS),
]


class RegexDetector:
    name = "regex"

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules if rules is not None else RULES

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for rule in self.rules:
            for m in rule.pattern.finditer(text):
                value = m.group(rule.group)
                if not value or (rule.validate and not rule.validate(value)):
                    continue
                start, end = m.span(rule.group)
                spans.append(Span(start, end, rule.label, value))
        return spans

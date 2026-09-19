"""Code sessions: bidirectional mapping between sensitive text and codes like [PERSON_A]."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .detect.base import Span

CODE_RE = re.compile(r"\[([A-Z]+)_([A-Z]+)\]")

PERSON = "PERSON"
TITLES = {"Mr", "Mrs", "Ms", "Miss", "Dr", "Prof", "Sir", "Madam"}
NAME_PART_RE = re.compile(r"[A-Z][A-Za-z'’\-·・]+")


CJK_NAME_RE = re.compile(r"[\u3400-\u9fff]{3,4}")
COMPOUND_SURNAMES = {
    "歐陽", "司馬", "諸葛", "上官", "東方", "皇甫", "尉遲", "公孫", "慕容", "長孫",
    "宇文", "司徒", "夏侯", "軒轅", "令狐", "端木", "西門", "南宮", "獨孤", "澹臺",
    "张简", "欧阳", "诸葛", "东方", "公孙", "长孙", "轩辕", "独孤", "張簡", "范姜",
}


def name_parts(name: str) -> list[str]:
    """Parts of a name that can stand for the whole person on their own:
    "John Smith" -> ["John", "Smith"], "王小明" -> ["小明"], "歐陽娜娜" -> ["娜娜"].
    A Chinese surname alone is too short to link safely; two-character names have none."""
    if CJK_NAME_RE.fullmatch(name):
        surname = 2 if len(name) == 4 else 1
        if len(name) == 4 and name[:2] not in COMPOUND_SURNAMES:
            return []
        return [name[surname:]]
    words = name.split()
    if len(words) < 2:
        return []
    return [w for w in words if NAME_PART_RE.fullmatch(w) and w not in TITLES]

COMMON_SURNAMES = set(
    "陳林黃張李王吳劉蔡楊許鄭謝洪郭邱曾廖賴徐周葉蘇莊呂江何蕭羅高潘簡朱鍾彭游詹胡施沈余"
    "趙盧梁顏柯孫魏翁戴范宋方鄧杜傅侯曹薛丁卓阮馬董温溫唐藍石蔣古紀姚連馮歐程湯田康姜白"
    "汪鄒尤巫鐘黎涂龔嚴韓袁金童陸夏柳邵錢伍倪于譚駱熊任甘秦顧毛章史官萬俞雷粘饒闕凃崔孔"
    "包易武辛賈段岳常樊葛齊殷祝左牛聶申"
    "陈刘黄张吴赵孙杨郑谢许邓冯萧罗叶苏卢蒋钟韩严龚鲁钱汤陆顾邹闫贾"
)


def find_all(text: str, values: dict[str, str]) -> list[Span]:
    """Every occurrence of each value (value -> label). Values that start/end with an
    ASCII letter or digit must not touch another one, so "Al" won't match in "Alice"."""
    spans: list[Span] = []
    for value, label in values.items():
        if not value.strip():
            continue
        left = r"(?<![A-Za-z0-9])" if value[0].isascii() and value[0].isalnum() else ""
        right = r"(?![A-Za-z0-9])" if value[-1].isascii() and value[-1].isalnum() else ""
        for m in re.finditer(left + re.escape(value) + right, text):
            spans.append(Span(m.start(), m.end(), label, value))
    return spans


def name_aliases(names: dict[str, str]) -> dict[str, str]:
    """Map each unambiguous name part to its full name's key (name -> any key, e.g. a code).
    A part shared by two different people ("John" in John Smith and John Doe) is dropped."""
    owners: dict[str, set[str]] = {}
    for name, key in names.items():
        for part in name_parts(name):
            owners.setdefault(part, set()).add(key)
    return {part: next(iter(keys)) for part, keys in owners.items()
            if len(keys) == 1 and part not in names}


def letters(n: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, 27 -> AB ... (bijective base-26)."""
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(ord("A") + r) + out
    return out


@dataclass
class RestoreResult:
    text: str
    restored: int
    unknown: list[str]


@dataclass
class Session:
    """One code file: every original gets a stable code for the session's lifetime."""

    label: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    to_code: dict[str, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    # Originals the user un-marked as false positives -> the code they had. They are
    # never coded again in this session, but text already sent out can still be restored.
    ignored: dict[str, str] = field(default_factory=dict)

    @property
    def to_original(self) -> dict[str, str]:
        """Code -> original. A linked person restores to the longest form, i.e. the full name."""
        out: dict[str, str] = {}
        for orig, code in self.to_code.items():
            if len(orig) > len(out.get(code, "")):
                out[code] = orig
        return out

    def _lookup(self) -> dict[str, str]:
        """Code -> original for restoring, including codes retired by `unmark`."""
        return {**{code: orig for orig, code in self.ignored.items()}, **self.to_original}

    def rows(self) -> list[tuple[str, list[str]]]:
        """(code, originals) for previewing the mapping, ordered by label then code."""
        grouped: dict[str, list[str]] = {}
        for orig, code in self.to_code.items():
            grouped.setdefault(code, []).append(orig)
        order = lambda code: (code[1:].rsplit("_", 1)[0], len(code), code)  # noqa: E731
        return [(code, sorted(grouped[code], key=len, reverse=True))
                for code in sorted(grouped, key=order)]

    def unmark(self, code: str) -> list[str]:
        """Stop treating `code`'s originals as sensitive. Returns them, longest first.
        The code is never reused, so it can't restore to a different value later."""
        originals = sorted((o for o, c in self.to_code.items() if c == code), key=len, reverse=True)
        for orig in originals:
            del self.to_code[orig]
            self.ignored[orig] = code
        return originals

    def mark(self, original: str, label: str) -> dict[str, str]:
        """Code a value the detectors missed. Returns every value to replace -> its code:
        the value, plus the parts of a person's name that now stand for them ("小明").
        A value un-marked before gets its old code back, so copies sent out still match."""
        if original in self.ignored:
            self.to_code[original] = self.ignored.pop(original)
        code = self.code_for(original, label)
        values = {original: code}
        if label == PERSON:
            for part, part_code in self.person_aliases().items():
                if part_code == code and part not in self.ignored:
                    self.to_code.setdefault(part, code)
                    values[part] = code
        return values

    def person_aliases(self) -> dict[str, str]:
        """Unambiguous parts of full person names in this session -> their code."""
        names = {o: c for o, c in self.to_code.items() if c.startswith(f"[{PERSON}_")}
        return name_aliases(names)

    def linked_person_code(self, original: str) -> str | None:
        """An existing code for the same person: "John" after "John Smith", or the reverse."""
        alias = self.person_aliases().get(original)
        if alias:
            return alias
        originals: dict[str, list[str]] = {}
        for orig, code in self.to_code.items():
            if code.startswith(f"[{PERSON}_"):
                originals.setdefault(code, []).append(orig)
        # A full name whose part was coded on its own earlier, and that code isn't yet
        # another full name (John -> A, then John Smith and John Doe must not both be A).
        candidates = {self.to_code[part] for part in name_parts(original)
                      if part in self.to_code and self.to_code[part] in originals
                      and not any(name_parts(o) for o in originals[self.to_code[part]])}
        return candidates.pop() if len(candidates) == 1 else None

    def code_for(self, original: str, label: str) -> str:
        if original not in self.to_code:
            code = self.linked_person_code(original) if label == PERSON else None
            if code is None:
                n = self.counters.get(label, 0)
                self.counters[label] = n + 1
                code = f"[{label}_{letters(n)}]"
            self.to_code[original] = code
        return self.to_code[original]

    def obfuscate(self, text: str, spans: list[Span]) -> tuple[str, list[Span]]:
        """Replace `spans` (non-overlapping) with codes. Returns new text and code spans in it."""
        out: list[str] = []
        code_spans: list[Span] = []
        pos = 0
        length = 0
        for span in sorted(spans, key=lambda s: s.start):
            prefix = text[pos:span.start]
            out.append(prefix)
            length += len(prefix)
            code = self.code_for(span.text, span.label)
            code_spans.append(Span(length, length + len(code), span.label, code))
            out.append(code)
            length += len(code)
            pos = span.end
        out.append(text[pos:])
        return "".join(out), code_spans

    def restore(self, text: str) -> RestoreResult:
        lookup = self._lookup()
        unknown: list[str] = []
        restored = 0

        def repl(m: re.Match[str]) -> str:
            nonlocal restored
            code = m.group(0)
            if code in lookup:
                restored += 1
                return lookup[code]
            if code not in unknown:
                unknown.append(code)
            return code

        return RestoreResult(CODE_RE.sub(repl, text), restored, unknown)

    def match_count(self, text: str) -> int:
        """How many distinct codes in `text` this session can restore."""
        lookup = self._lookup()
        return len({m.group(0) for m in CODE_RE.finditer(text)} & lookup.keys())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "created_at": self.created_at,
            "to_code": self.to_code,
            "counters": self.counters,
            "ignored": self.ignored,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        return cls(
            label=data["label"],
            id=data["id"],
            created_at=data["created_at"],
            to_code=dict(data["to_code"]),
            counters=dict(data["counters"]),
            ignored=dict(data.get("ignored", {})),
        )


def revert_code(text: str, code_spans: list[Span], originals: list[str],
                code: str) -> tuple[str, list[Span], list[str]]:
    """Put the originals back wherever `code` sits in an obfuscated text.
    `originals[i]` is what `code_spans[i]` replaced. Returns the new text, spans, originals."""
    out: list[str] = []
    spans: list[Span] = []
    kept: list[str] = []
    pos = 0
    shift = 0
    for span, orig in zip(code_spans, originals):
        if span.text != code:
            spans.append(Span(span.start + shift, span.end + shift, span.label, span.text))
            kept.append(orig)
            continue
        out.append(text[pos:span.start])
        out.append(orig)
        pos = span.end
        shift += len(orig) - len(span)
    out.append(text[pos:])
    return "".join(out), spans, kept


def recommend(text: str, sessions: list[Session]) -> Session | None:
    """The session that can restore the most codes found in `text`, if any."""
    best = max(sessions, key=lambda s: s.match_count(text), default=None)
    if best is None or best.match_count(text) == 0:
        return None
    return best


def apply_codes(text: str, code_spans: list[Span], originals: list[str],
                values: dict[str, str]) -> tuple[str, list[Span], list[str]]:
    """Replace each value (value -> code) wherever it appears outside the codes already in
    an obfuscated text. The inverse of `revert_code`; returns the new text, spans, originals."""
    labels = {v: code[1:].rsplit("_", 1)[0] for v, code in values.items()}
    taken = [(s.start, s.end) for s in code_spans]
    found = sorted((m for m in find_all(text, labels)
                    if not any(m.start < e and s < m.end for s, e in taken)),
                   key=lambda m: (m.start, -len(m)))
    new: list[Span] = []
    for m in found:  # longest first at each position, never overlapping
        if not new or m.start >= new[-1].end:
            new.append(m)
    items = sorted([(s, o, False) for s, o in zip(code_spans, originals)]
                   + [(m, m.text, True) for m in new], key=lambda t: t[0].start)
    out: list[str] = []
    spans: list[Span] = []
    kept: list[str] = []
    pos = 0
    length = 0
    for span, orig, is_new in items:
        prefix = text[pos:span.start]
        out.append(prefix)
        length += len(prefix)
        code = values[orig] if is_new else span.text
        spans.append(Span(length, length + len(code), span.label, code))
        kept.append(orig)
        out.append(code)
        length += len(code)
        pos = span.end
    out.append(text[pos:])
    return "".join(out), spans, kept

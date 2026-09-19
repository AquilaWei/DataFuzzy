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


def name_parts(name: str) -> list[str]:
    """Parts of a multi-word name that can stand for the whole person on their own:
    "John Smith" -> ["John", "Smith"]. Single words and CJK names have none."""
    words = name.split()
    if len(words) < 2:
        return []
    return [w for w in words if NAME_PART_RE.fullmatch(w) and w not in TITLES]


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

    @property
    def to_original(self) -> dict[str, str]:
        """Code -> original. A linked person restores to the longest form, i.e. the full name."""
        out: dict[str, str] = {}
        for orig, code in self.to_code.items():
            if len(orig) > len(out.get(code, "")):
                out[code] = orig
        return out

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
        lookup = self.to_original
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
        lookup = self.to_original
        return len({m.group(0) for m in CODE_RE.finditer(text)} & lookup.keys())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "created_at": self.created_at,
            "to_code": self.to_code,
            "counters": self.counters,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        return cls(
            label=data["label"],
            id=data["id"],
            created_at=data["created_at"],
            to_code=dict(data["to_code"]),
            counters=dict(data["counters"]),
        )


def recommend(text: str, sessions: list[Session]) -> Session | None:
    """The session that can restore the most codes found in `text`, if any."""
    best = max(sessions, key=lambda s: s.match_count(text), default=None)
    if best is None or best.match_count(text) == 0:
        return None
    return best

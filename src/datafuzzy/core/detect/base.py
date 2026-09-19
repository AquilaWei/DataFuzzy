"""Common types shared by all detectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Span:
    """A sensitive substring: text[start:end] of category `label`."""

    start: int
    end: int
    label: str
    text: str
    score: float = 1.0

    def __len__(self) -> int:
        return self.end - self.start


class Detector(Protocol):
    name: str

    def detect(self, text: str) -> list[Span]: ...


def resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Keep non-overlapping spans, preferring earlier, then longer, then higher score."""
    kept: list[Span] = []
    for span in sorted(spans, key=lambda s: (s.start, -len(s), -s.score)):
        if not kept or span.start >= kept[-1].end:
            kept.append(span)
    return kept

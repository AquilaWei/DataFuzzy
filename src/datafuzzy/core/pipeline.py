"""Glue: pick detectors for a language, obfuscate into a session, restore from one."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .detect import Detector, RegexDetector, Span, resolve_overlaps
from .lang import Lang, detect_language
from .mapping import RestoreResult, Session

LangChoice = Literal["auto", "en", "zh"]


@dataclass
class ObfuscateResult:
    text: str
    lang: Lang
    spans: list[Span]       # sensitive spans found in the input
    code_spans: list[Span]  # where the codes sit in the output


class Pipeline:
    def __init__(self) -> None:
        self.rules = RegexDetector()
        # Language-specific model detectors, registered once their model is available.
        self.models: dict[Lang, Detector] = {}

    def detectors_for(self, lang: Lang) -> list[Detector]:
        detectors: list[Detector] = [self.rules]
        if lang in self.models:
            detectors.append(self.models[lang])
        return detectors

    def detect(self, text: str, lang: LangChoice = "auto") -> tuple[Lang, list[Span]]:
        resolved: Lang = detect_language(text) if lang == "auto" else lang
        spans = [s for d in self.detectors_for(resolved) for s in d.detect(text)]
        return resolved, resolve_overlaps(spans)

    def obfuscate(self, text: str, session: Session, lang: LangChoice = "auto") -> ObfuscateResult:
        resolved, spans = self.detect(text, lang)
        out, code_spans = session.obfuscate(text, spans)
        return ObfuscateResult(out, resolved, spans, code_spans)

    @staticmethod
    def restore(text: str, session: Session) -> RestoreResult:
        return session.restore(text)

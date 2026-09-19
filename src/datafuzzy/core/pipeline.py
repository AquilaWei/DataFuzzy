"""Glue: pick detectors for a language, obfuscate into a session, restore from one."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .detect import Detector, RegexDetector, Span, resolve_overlaps
from .detect.ner import NerDetector
from .lang import Lang, detect_language
from .mapping import PERSON, RestoreResult, Session, name_aliases
from .models import ModelSpec, is_installed

LangChoice = Literal["auto", "en", "zh"]


@dataclass
class ObfuscateResult:
    text: str
    lang: Lang
    spans: list[Span]       # sensitive spans found in the input
    code_spans: list[Span]  # where the codes sit in the output
    model_used: bool        # False when no model is installed for `lang`


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


class Pipeline:
    def __init__(self) -> None:
        self.rules = RegexDetector()
        # Language-specific model detectors, registered once their model is installed.
        self.models: dict[Lang, Detector] = {}

    def load_models(self, specs: list[ModelSpec], root: Path) -> None:
        """(Re)register detectors for installed models. Models load lazily on first use."""
        current = {lang: d for lang, d in self.models.items() if isinstance(d, NerDetector)}
        self.models = {}
        for spec in specs:
            if not is_installed(spec, root):
                continue
            existing = current.get(spec.lang)
            if existing and existing.model_dir == root / spec.id:
                self.models[spec.lang] = existing
            else:
                self.models[spec.lang] = NerDetector(root / spec.id, spec.labels, name=spec.id)

    def detect(self, text: str, lang: LangChoice = "auto",
               known: dict[str, str] | None = None) -> tuple[Lang, list[Span], bool]:
        resolved: Lang = detect_language(text) if lang == "auto" else lang
        detectors: list[Detector] = [self.rules]
        model = self.models.get(resolved)
        if model:
            detectors.append(model)
        spans = [s for d in detectors for s in d.detect(text)]
        # Names are what models miss most: once a value is found anywhere in this text,
        # or already has a code in the session, replace every occurrence of it.
        values = dict(known or {})
        values.update({s.text: s.label for s in spans})
        # A first or last name on its own ("John" after "John Smith") is the same person.
        persons = {v: v for v, label in values.items() if label == PERSON}
        values.update({part: PERSON for part in name_aliases(persons)})
        spans += find_all(text, values)
        return resolved, resolve_overlaps(spans), model is not None

    def obfuscate(self, text: str, session: Session, lang: LangChoice = "auto") -> ObfuscateResult:
        known = {orig: code[1:].rsplit("_", 1)[0] for orig, code in session.to_code.items()}
        resolved, spans, model_used = self.detect(text, lang, known)
        out, code_spans = session.obfuscate(text, spans)
        return ObfuscateResult(out, resolved, spans, code_spans, model_used)

    @staticmethod
    def restore(text: str, session: Session) -> RestoreResult:
        return session.restore(text)

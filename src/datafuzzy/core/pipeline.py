"""Glue: pick detectors for a language, obfuscate into a session, restore from one."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .detect import Detector, RegexDetector, Span, resolve_overlaps
from .detect.ner import NerDetector
from .detect.privacy_filter import PrivacyFilterDetector
from .lang import Lang, detect_language, languages_in
from .mapping import PERSON, RestoreResult, Session, find_all, name_aliases
from .models import ModelSpec, is_installed
from .speakers import speaker_spans

LangChoice = Literal["auto", "en", "zh"]
# "names": code only people, leave emails, places, IDs... readable.
Scope = Literal["all", "names"]


@dataclass
class ObfuscateResult:
    text: str
    lang: Lang
    spans: list[Span]       # sensitive spans found in the input
    code_spans: list[Span]  # where the codes sit in the output
    originals: list[str]    # what each code span replaced
    model_used: bool        # False when no model is installed for `lang`


LINE_RE = re.compile(r"[^\n]+")


def line_entities(model: Detector, text: str) -> list[Span]:
    """Entities found line by line. Unrelated lines of a form (病歷號、身分證、地址...) run
    together confuse the models: an address found on its own line is lost or broken into
    single characters when the lines above it are in the same input."""
    spans: list[Span] = []
    for m in LINE_RE.finditer(text):
        if m.group().strip():
            for s in model.detect(m.group()):
                spans.append(Span(s.start + m.start(), s.end + m.start(), s.label, s.text, s.score))
    return spans


LOC = "LOC"
# CJK ideographs and punctuation, fullwidth forms.
CJK_RUN = re.compile(r"[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]+")


def latin_parts(text: str, spans: list[Span]) -> list[Span]:
    """The privacy filter finds personal data in Chinese text but not where it starts and
    ends ("李建宏 警", "ARK-5821 對吧？"). A span with Chinese characters is cut at them and
    keeps its pieces with a digit (numbers, dates, codes) or, for a person, with Latin
    letters ("Dr. Kevin Lee"). Chinese names come from the Chinese model, Taiwan
    addresses from the address rule."""
    out: list[Span] = []
    for s in spans:
        if not CJK_RUN.search(s.text):
            out.append(s)
            continue
        if s.label == LOC:
            continue
        keep = re.compile(r"[A-Za-z]{2}" if s.label == PERSON else r"\d")
        start = 0
        for piece in CJK_RUN.split(s.text):
            at = s.text.index(piece, start)
            start = at + len(piece)
            core = piece.strip(" \t:;,.")
            if keep.search(core):
                begin = s.start + at + piece.index(core)
                out.append(Span(begin, begin + len(core), s.label, core, s.score))
    return out


class Pipeline:
    def __init__(self) -> None:
        self.rules = RegexDetector()
        # Personal data in any language (openai/privacy-filter), once installed.
        self.pii: Detector | None = None
        # People in one language the privacy filter reads poorly (Chinese), once installed.
        self.models: dict[Lang, Detector] = {}

    def load_models(self, specs: list[ModelSpec], root: Path) -> None:
        """(Re)register detectors for installed models. Models load lazily on first use."""
        current = {d.model_dir: d for d in (self.pii, *self.models.values())
                   if isinstance(d, (NerDetector, PrivacyFilterDetector))}
        self.pii, self.models = None, {}
        for spec in specs:
            if not is_installed(spec, root):
                continue
            detector = current.get(root / spec.id)
            if spec.kind == "privacy-filter":
                self.pii = detector or PrivacyFilterDetector(root / spec.id, spec.labels, name=spec.id)
            else:
                self.models[spec.lang] = detector or NerDetector(root / spec.id, spec.labels, name=spec.id)

    def detect(self, text: str, lang: LangChoice = "auto",
               known: dict[str, str] | None = None,
               ignore: set[str] | frozenset[str] = frozenset(),
               scope: Scope = "all") -> tuple[Lang, list[Span], bool]:
        """`known`: values that already have a code (value -> label); `ignore`: values the
        user marked as not sensitive."""
        resolved: Lang = detect_language(text) if lang == "auto" else lang
        # Auto mode runs every language's model on mixed text ("請 John Smith 跟王小明...").
        langs = languages_in(text) if lang == "auto" else [resolved]
        spans = self.rules.detect(text)
        if self.pii:
            spans += latin_parts(text, self.pii.detect(text))
        for x in langs:
            if model := self.models.get(x):
                spans += line_entities(model, text)
        model_used = self.pii is not None and all(x in self.models for x in langs if x != "en")
        spans = [s for s in spans if s.text not in ignore]
        # Names are what models miss most: once a value is found anywhere in this text,
        # or already has a code in the session, replace every occurrence of it.
        # A single character is too common to replace everywhere ("明" would hit "明天").
        values = {v: label for v, label in (known or {}).items() if len(v) > 1}
        values.update({s.text: s.label for s in spans if len(s.text) > 1})
        # Chat logs: once one speaker is a known person, the other speakers are too.
        speakers = speaker_spans(text, {v for v, label in values.items() if label == PERSON})
        for s in speakers:
            if s.text not in ignore:
                values.setdefault(s.text, PERSON)
        # A first or last name on its own ("John" after "John Smith") is the same person.
        persons = {v: v for v, label in values.items() if label == PERSON}
        values.update({part: PERSON for part in name_aliases(persons)})
        spans += [s for s in find_all(text, values) if s.text not in ignore]
        if scope == "names":
            # Before overlaps are resolved, so a name inside a longer value is still coded.
            spans = [s for s in spans if s.label == PERSON]
        return resolved, resolve_overlaps(spans), model_used

    def obfuscate(self, text: str, session: Session, lang: LangChoice = "auto",
                  scope: Scope = "all") -> ObfuscateResult:
        known = {orig: code[1:].rsplit("_", 1)[0] for orig, code in session.to_code.items()}
        resolved, spans, model_used = self.detect(text, lang, known, set(session.ignored), scope)
        out, code_spans = session.obfuscate(text, spans)
        originals = [s.text for s in sorted(spans, key=lambda s: s.start)]
        return ObfuscateResult(out, resolved, spans, code_spans, originals, model_used)

    @staticmethod
    def restore(text: str, session: Session) -> RestoreResult:
        return session.restore(text)

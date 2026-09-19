"""Glue: pick detectors for a language, obfuscate into a session, restore from one."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .detect import Detector, RegexDetector, Span, resolve_overlaps
from .detect.ner import NerDetector
from .lang import Lang, detect_language, has_cjk, languages_in
from .mapping import COMMON_SURNAMES, PERSON, RestoreResult, Session, find_all, name_aliases
from .models import ModelSpec, is_installed
from .speakers import speaker_spans

LangChoice = Literal["auto", "en", "zh"]


@dataclass
class ObfuscateResult:
    text: str
    lang: Lang
    spans: list[Span]       # sensitive spans found in the input
    code_spans: list[Span]  # where the codes sit in the output
    originals: list[str]    # what each code span replaced
    model_used: bool        # False when no model is installed for `lang`


CLAUSE_RE = re.compile(r"[^。！？；，、,;!?\n]+")
LINE_RE = re.compile(r"[^\n]+")


def detect_pieces(model: Detector, pieces: list[re.Match[str]]) -> list[Span]:
    spans: list[Span] = []
    for m in pieces:
        for s in model.detect(m.group()):
            spans.append(Span(s.start + m.start(), s.end + m.start(), s.label, s.text, s.score))
    return spans


def line_entities(model: Detector, text: str) -> list[Span]:
    """Entities found line by line. Unrelated lines of a form (病歷號、身分證、地址...) run
    together confuse the models: an address found on its own line is lost or broken into
    single characters when the lines above it are in the same input."""
    lines = [m for m in LINE_RE.finditer(text) if m.group().strip()]
    spans = detect_pieces(model, lines)
    # A lone character is a fragment of a missed name, not an organization or place.
    return [s for s in spans if len(s.text.strip()) > 1 or s.label == PERSON]


def clause_names(model: Detector, text: str) -> list[Span]:
    """Names found by running the model on each clause alone, without its punctuation.
    The Chinese model misses some names in context ("這是何文明的報帳單，請...") that it
    finds in a shorter piece, so this second look only adds people."""
    clauses = [m for m in CLAUSE_RE.finditer(text) if m.group().strip()]
    if len(clauses) < 2 and (not clauses or clauses[0].group() == text):
        return []
    return [s for s in detect_pieces(model, clauses) if s.label == PERSON]


ORG = "ORG"


def trim_to_known_orgs(spans: list[Span], known_orgs: set[str]) -> list[Span]:
    """An organization followed by a unit ("羅東博愛醫院 家醫科") is cut back to the
    organization when that is also found on its own, so one hospital gets one code.
    Only organizations: cutting an address back would expose the house number."""
    orgs = known_orgs | {s.text for s in spans if s.label == ORG}
    out: list[Span] = []
    for s in spans:
        if s.label == ORG:
            heads = [o for o in orgs if len(o) < len(s.text) and s.text.startswith(o)
                     and s.text[len(o)].isspace()]
            if heads:
                head = max(heads, key=len)
                s = Span(s.start, s.start + len(head), ORG, head, s.score)
        out.append(s)
    return out


# After a lone surname, these start a title or a function word, not a given name.
NOT_GIVEN_NAME = set("經副先小老醫董總主教律博同太護的了是在和跟與及說把被給向對也都就還又而並但或會要請已再")


def extend_surnames(text: str, spans: list[Span]) -> list[Span]:
    """The Chinese model sometimes tags only the surname ("給[顧]秀"): take the given name
    too, one or two Chinese characters, unless a title or function word follows (王經理)."""
    out: list[Span] = []
    for s in spans:
        if s.label == PERSON and len(s.text) == 1 and s.text in COMMON_SURNAMES:
            end = s.end
            while end < min(s.end + 2, len(text)) and "\u3400" <= text[end] <= "\u9fff" \
                    and text[end] not in NOT_GIVEN_NAME:
                end += 1
            s = Span(s.start, end, PERSON, text[s.start:end], s.score)
        out.append(s)
    return out


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
               known: dict[str, str] | None = None,
               ignore: set[str] | frozenset[str] = frozenset()) -> tuple[Lang, list[Span], bool]:
        """`known`: values that already have a code (value -> label); `ignore`: values the
        user marked as not sensitive."""
        resolved: Lang = detect_language(text) if lang == "auto" else lang
        # Auto mode runs every language's model on mixed text ("請 John Smith 跟王小明...").
        langs = [resolved] + [x for x in languages_in(text) if x != resolved] if lang == "auto" \
            else [resolved]
        spans = self.rules.detect(text)
        for x in langs:
            model = self.models.get(x)
            if not model:
                continue
            found = line_entities(model, text)
            if x == "zh":
                found = extend_surnames(text, found + clause_names(model, text))
            if x != "zh":  # non-Chinese models only see Chinese characters as noise
                found = [s for s in found if not has_cjk(s.text)]
            spans += found
        model_used = resolved in self.models
        spans = [s for s in spans if s.text not in ignore]
        spans = trim_to_known_orgs(spans, {v for v, label in (known or {}).items() if label == ORG})
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
        return resolved, resolve_overlaps(spans), model_used

    def obfuscate(self, text: str, session: Session, lang: LangChoice = "auto") -> ObfuscateResult:
        known = {orig: code[1:].rsplit("_", 1)[0] for orig, code in session.to_code.items()}
        resolved, spans, model_used = self.detect(text, lang, known, set(session.ignored))
        out, code_spans = session.obfuscate(text, spans)
        originals = [s.text for s in sorted(spans, key=lambda s: s.start)]
        return ObfuscateResult(out, resolved, spans, code_spans, originals, model_used)

    @staticmethod
    def restore(text: str, session: Session) -> RestoreResult:
        return session.restore(text)

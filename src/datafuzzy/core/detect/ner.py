"""Named-entity detection with a BERT token-classification model exported to ONNX."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import numpy as np

from .base import Span

MAX_TOKENS = 512
STRIDE = 64
# Recall over precision: a token is an entity when its best entity type (B-X + I-X ...)
# reaches this probability, even if "O" is slightly higher. Missing a name leaks it;
# over-masking only costs readability.
ENTITY_THRESHOLD = 0.4
# Characters that join parts of one name: Wei-Chuang, O'Brien, 阿里·巴巴.
JOINERS = {"", "-", "\u2010", "'", "\u2019", "\u00b7", "\u30fb"}


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def decode_entities(
    text: str,
    word_ids: list[int | None],
    offsets: list[tuple[int, int]],
    tags: list[str],
    scores: list[float],
    labels: dict[str, str],
    min_score: float = ENTITY_THRESHOLD,
) -> list[Span]:
    """Turn per-token BIO / BIOES tags into character spans.

    Each word takes the tag of its first sub-token; consecutive words of the same entity
    type are merged (a stray I- after O also starts an entity). S- counts as B- and E- as
    I-. Only types present in `labels` are kept, renamed to our label names.
    """
    words: list[list] = []  # [start, end, tag, score]
    seen: dict[int, int] = {}
    for w, (start, end), tag, score in zip(word_ids, offsets, tags, scores):
        if w is None or end <= start:
            continue
        if w in seen:
            words[seen[w]][1] = end
        else:
            seen[w] = len(words)
            words.append([start, end, tag, score])

    spans: list[Span] = []
    current: list | None = None  # [type, start, end, [scores]]

    def flush() -> None:
        if current and current[0] in labels:
            mean = float(np.mean(current[3]))
            if mean >= min_score:
                s, e = current[1], current[2]
                spans.append(Span(s, e, labels[current[0]], text[s:e], mean))

    for start, end, tag, score in words:
        prefix, _, kind = tag.partition("-")
        prefix = {"S": "B", "E": "I"}.get(prefix, prefix)
        if prefix == "I" and current and current[0] == kind:
            current[2] = end
            current[3].append(score)
            continue
        flush()
        current = [kind, start, end, [score]] if prefix in ("B", "I") else None
    flush()
    return merge_joined(text, spans)


def merge_joined(text: str, spans: list[Span]) -> list[Span]:
    """Merge same-label neighbours separated only by a name joiner (the model often tags
    "Wei-Chuang" as two entities because "-" is its own word)."""
    merged: list[Span] = []
    for span in spans:
        prev = merged[-1] if merged else None
        if prev and prev.label == span.label and text[prev.end:span.start] in JOINERS:
            merged[-1] = Span(prev.start, span.end, span.label, text[prev.start:span.end],
                              min(prev.score, span.score))
        else:
            merged.append(span)
    return merged


class NerDetector:
    """Loads lazily (first detect) so an installed-but-unused model costs no memory."""

    def __init__(self, model_dir: Path, labels: dict[str, str], name: str = "ner",
                 min_score: float = ENTITY_THRESHOLD) -> None:
        self.name = name
        self.model_dir = Path(model_dir)
        self.labels = labels
        self.min_score = min_score
        self._lock = threading.Lock()
        self._session = None
        self._tokenizer = None
        self._id2tag: dict[int, str] = {}
        self._type_ids: dict[str, list[int]] = {}  # entity type ("PER", "" for O) -> tag ids
        self._begin_ids: dict[str, list[int]] = {}  # B-/S- tag ids per entity type
        self._cls = self._sep = 0

    @property
    def loaded(self) -> bool:
        return self._session is not None

    def load(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            import onnxruntime as ort
            from tokenizers import Tokenizer

            config = json.loads((self.model_dir / "config.json").read_text())
            self._id2tag = {int(k): v for k, v in config["id2label"].items()}
            self._type_ids = {}
            for i, tag in self._id2tag.items():
                self._type_ids.setdefault(tag.partition("-")[2], []).append(i)
            self._begin_ids = {}
            for i, tag in self._id2tag.items():
                if tag[:2] in ("B-", "S-"):
                    self._begin_ids.setdefault(tag[2:], []).append(i)
            tok = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
            tok.no_padding()
            tok.no_truncation()  # we window the full encoding ourselves
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = min(4, os.cpu_count() or 1)
            self._session = ort.InferenceSession(
                str(self.model_dir / "model.onnx"), opts, providers=["CPUExecutionProvider"]
            )
            self._tokenizer = tok
            self._cls = tok.token_to_id("[CLS]")
            self._sep = tok.token_to_id("[SEP]")

    def _tag(self, probs: np.ndarray) -> tuple[list[str], list[float]]:
        """Per token: (B-/I- tag, probability of its entity type)."""
        tags: list[str] = []
        scores: list[float] = []
        for row in probs:
            best_type, best_p = "", 0.0
            for kind, ids in self._type_ids.items():
                if kind and (p := float(row[ids].sum())) > best_p:
                    best_type, best_p = kind, p
            if best_p >= self.min_score:
                begin = float(row[self._begin_ids.get(best_type, [])].sum())
                tags.append(("B-" if begin >= best_p - begin else "I-") + best_type)
                scores.append(best_p)
            else:
                tags.append("O")
                scores.append(1.0 - best_p)
        return tags, scores

    def detect(self, text: str) -> list[Span]:
        if not text.strip():
            return []
        self.load()
        enc = self._tokenizer.encode(text, add_special_tokens=False)
        spans: list[Span] = []
        size = MAX_TOKENS - 2  # room for [CLS] and [SEP]
        start = 0
        while True:
            end = min(start + size, len(enc.ids))
            ids = [self._cls, *enc.ids[start:end], self._sep]
            feeds = {
                "input_ids": np.array([ids], dtype=np.int64),
                "attention_mask": np.ones((1, len(ids)), dtype=np.int64),
                "token_type_ids": np.zeros((1, len(ids)), dtype=np.int64),
            }
            names = {i.name for i in self._session.get_inputs()}
            logits = self._session.run(None, {k: v for k, v in feeds.items() if k in names})[0][0]
            tags, scores = self._tag(_softmax(logits[1:-1]))
            spans += decode_entities(text, enc.word_ids[start:end], enc.offsets[start:end], tags,
                                     scores, self.labels, self.min_score)
            if end >= len(enc.ids):
                break
            start = end - STRIDE
        # Chunks overlap (stride), so the same entity can appear twice.
        return list({(s.start, s.end, s.label): s for s in spans}.values())

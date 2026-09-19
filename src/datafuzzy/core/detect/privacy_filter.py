"""Personal data detection with openai/privacy-filter (ONNX): people, addresses, dates,
emails, phones, URLs, account numbers and secrets, in one pass.

The model gives per-token BIOES logits; spans come from a constrained Viterbi decode, as
in the model card. It finds personal data only, not organizations or places."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

import numpy as np

from .base import Span

# Added to the "O" log-probability before decoding. Below zero favours spans: missing a
# name leaks it, over-masking only costs readability.
BACKGROUND_BIAS = -2.0
# Longer inputs are cut at line breaks into pieces of about this many tokens; the model
# attends locally (128-token window), so nothing is lost at a line break.
MAX_TOKENS = 4096


class PrivacyFilterDetector:
    """Loads lazily (first detect) so an installed-but-unused model costs no memory."""

    def __init__(self, model_dir: Path, labels: dict[str, str], name: str = "privacy-filter",
                 bias: float = BACKGROUND_BIAS) -> None:
        self.name = name
        self.model_dir = Path(model_dir)
        self.labels = labels
        self.bias = bias
        self._lock = threading.Lock()
        self._session = None
        self._tokenizer = None
        self._tags: list[tuple[str, str]] = []  # (prefix, entity type) per tag id

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
            id2label = {int(k): v for k, v in config["id2label"].items()}
            self._tags = [id2label[i].partition("-")[::2] for i in range(len(id2label))]
            n = len(self._tags)
            allowed = np.zeros((n, n), bool)
            for i, (pa, ka) in enumerate(self._tags):
                for j, (pb, kb) in enumerate(self._tags):
                    allowed[i, j] = (pb in ("O", "B", "S") if pa in ("O", "E", "S")
                                     else pb in ("I", "E") and ka == kb)
            self._trans = np.where(allowed, 0.0, -np.inf)
            self._start = np.array([0.0 if p in ("O", "B", "S") else -np.inf for p, _ in self._tags])
            self._end = np.array([0.0 if p in ("O", "E", "S") else -np.inf for p, _ in self._tags])
            tok = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
            tok.no_padding()
            tok.no_truncation()
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = min(4, os.cpu_count() or 1)
            # Prepacking keeps a second, reordered copy of the 4-bit weights: ~1.1 GB more
            # on macOS and ~4 GB more on x86 Linux.
            opts.add_session_config_entry("session.disable_prepacking", "1")
            self._session = ort.InferenceSession(
                str(self.model_dir / "model.onnx"), opts, providers=["CPUExecutionProvider"]
            )
            self._inputs = {i.name for i in self._session.get_inputs()}
            self._tokenizer = tok

    def _viterbi(self, logp: np.ndarray) -> list[int]:
        """Best tag path that respects BIOES (B/I must continue with I/E of the same type)."""
        score = self._start + logp[0]
        back = np.zeros(logp.shape, np.int64)
        for t in range(1, len(logp)):
            cand = score[:, None] + self._trans
            back[t] = cand.argmax(0)
            score = cand.max(0) + logp[t]
        path = [int((score + self._end).argmax())]
        for t in range(len(logp) - 1, 0, -1):
            path.append(int(back[t][path[-1]]))
        return path[::-1]

    def _detect_piece(self, text: str, offset: int) -> list[Span]:
        enc = self._tokenizer.encode(text, add_special_tokens=False)
        if not enc.ids:
            return []
        feeds = {"input_ids": np.array([enc.ids], np.int64)}
        if "attention_mask" in self._inputs:
            feeds["attention_mask"] = np.ones((1, len(enc.ids)), np.int64)
        logits = self._session.run(None, feeds)[0][0].astype(np.float64)
        logp = logits - logits.max(-1, keepdims=True)
        logp -= np.log(np.exp(logp).sum(-1, keepdims=True))
        logp[:, 0] += self.bias  # tag 0 is "O"
        spans: list[Span] = []
        current: list | None = None  # [type, start, end]
        for (s, e), tag in zip(enc.offsets, self._viterbi(logp)):
            prefix, kind = self._tags[tag]
            if prefix in ("B", "S"):
                current = [kind, s, e]
            elif prefix in ("I", "E") and current:
                current[2] = max(current[2], e)
            if prefix in ("E", "S") and current:
                kind, s, e = current
                current = None
                # Tokens carry their leading space; spans don't.
                while s < e and text[s].isspace():
                    s += 1
                while e > s and text[e - 1].isspace():
                    e -= 1
                if e > s and kind in self.labels:
                    spans.append(Span(s + offset, e + offset, self.labels[kind], text[s:e]))
        return spans

    def detect(self, text: str) -> list[Span]:
        if not text.strip():
            return []
        self.load()
        spans: list[Span] = []
        start = 0
        for piece in _pieces(text, self._tokenizer):
            spans += self._detect_piece(piece, start)
            start += len(piece)
        return spans


def _pieces(text: str, tokenizer) -> list[str]:
    """`text` cut after line breaks into pieces of at most ~MAX_TOKENS tokens."""
    if len(text) <= MAX_TOKENS:  # a token covers at least one character
        return [text]
    pieces: list[str] = []
    current, size = "", 0
    for line in re.findall(r"[^\n]*\n|[^\n]+", text):
        n = len(tokenizer.encode(line, add_special_tokens=False).ids)
        if current and size + n > MAX_TOKENS:
            pieces.append(current)
            current, size = "", 0
        current += line
        size += n
    return pieces + [current] if current else pieces

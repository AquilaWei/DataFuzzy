"""Tests against the real English model; skipped when it isn't available locally."""

import os
import sys

import pytest

from conftest import real_model_dir
from datafuzzy.core.detect.ner import NerDetector
from datafuzzy.core.mapping import Session
from datafuzzy.core.pipeline import Pipeline

MODEL = real_model_dir()
if MODEL is None and os.environ.get("DATAFUZZY_REQUIRE_MODEL"):
    raise RuntimeError("DATAFUZZY_REQUIRE_MODEL is set but no English model was found")
pytestmark = pytest.mark.skipif(MODEL is None, reason="English model not available")
LABELS = {"PER": "PERSON", "ORG": "ORG", "LOC": "LOC"}


@pytest.fixture(scope="module")
def ner():
    return NerDetector(MODEL, LABELS)


def found(ner, text):
    return {(s.label, s.text) for s in ner.detect(text)}


def test_people_orgs_places(ner):
    got = found(ner, "Please send the contract to Alice Chen at Acme Corporation in San Francisco.")
    assert {("PERSON", "Alice Chen"), ("ORG", "Acme Corporation"), ("LOC", "San Francisco")} <= got


@pytest.mark.parametrize("text", [
    "Hi Maria, please ask John Smith.",
    "Hi Maria, please ask John Smith at Acme Corporation to send the Berlin report to "
    "john.smith@acme.com. Wei-Chuang Huang will review it.",
])
def test_greeting_name(ner, text):
    assert ("PERSON", "Maria") in found(ner, text)


def test_hyphenated_name(ner):
    got = found(ner, "Our project lead Wei-Chuang Huang will visit Taipei next week.")
    assert ("PERSON", "Wei-Chuang Huang") in got


def test_long_text_is_chunked(ner):
    filler = "The weather was fine and nothing happened. " * 150  # > 512 tokens
    got = found(ner, filler + "Then Satya Nadella arrived.")
    assert ("PERSON", "Satya Nadella") in got


def test_round_trip_with_model(ner):
    p = Pipeline()
    p.models["en"] = ner
    session = Session(label="t")
    text = "John Smith met Satya Nadella from Microsoft. Later, John emailed satya@microsoft.com."
    result = p.obfuscate(text, session, "en")
    for name in ("John Smith", "Satya Nadella", "Microsoft", "satya@microsoft.com"):
        assert name not in result.text
    # "John" shares John Smith's code, so it restores to the full name.
    assert session.restore(result.text).text == text.replace("Later, John", "Later, John Smith")


def test_memory_budget():
    """Measured in a fresh process: earlier tests (e.g. name recall) load both models into
    this one, which would count against the English model."""
    import subprocess

    script = f"""
import resource, sys
from pathlib import Path
from datafuzzy.core.detect.ner import NerDetector
NerDetector(Path({str(MODEL)!r}), {LABELS!r}).detect("Alice Chen met Bob at Google.")
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(rss / (1 << 20) if sys.platform == "darwin" else rss / 1024)  # bytes on macOS
"""
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    rss_mb = float(out.stdout.strip().splitlines()[-1])
    assert rss_mb < 600, rss_mb

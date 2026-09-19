"""Tests against the real privacy filter model; skipped when it isn't available locally."""

import os
import sys

import pytest

from conftest import real_model_dir
from datafuzzy.core.detect import privacy_filter
from datafuzzy.core.detect.privacy_filter import PrivacyFilterDetector
from datafuzzy.core.mapping import Session
from datafuzzy.core.models import load_manifest
from datafuzzy.core.pipeline import Pipeline

MODEL = real_model_dir("privacy-filter")
if MODEL is None and os.environ.get("DATAFUZZY_REQUIRE_MODEL"):
    raise RuntimeError("DATAFUZZY_REQUIRE_MODEL is set but the privacy filter model was not found")
pytestmark = pytest.mark.skipif(MODEL is None, reason="privacy filter model not available")
LABELS = next(s for s in load_manifest() if s.id == "privacy-filter").labels


@pytest.fixture(scope="module")
def pf():
    return PrivacyFilterDetector(MODEL, LABELS)


def found(pf, text):
    return {(s.label, s.text) for s in pf.detect(text)}


def test_personal_data(pf):
    got = found(pf, "Patient: Harold J. Whitmore    DOB: 1952-11-08    MRN: 7730-4412\n"
                    "Email harold.w@example.com or call 07700 900461.")
    assert {("PERSON", "Harold J. Whitmore"), ("DATE", "1952-11-08"),
            ("EMAIL", "harold.w@example.com"), ("PHONE", "07700 900461")} <= got
    assert "7730-4412" in {text for _, text in got}  # a record number, whatever its label


def test_organizations_places_and_diseases_are_not_personal(pf):
    text = ("Dr. Alan Hsu at St. Vincent Medical Center in Portland treats Parkinson's disease; "
            "the Platform team told Legal and the CISO.")
    assert found(pf, text) == {("PERSON", "Dr. Alan Hsu")}


@pytest.mark.parametrize("text, name", [
    ("Hi Maria, please ask John Smith.", "Maria"),
    ("Our project lead Wei-Chuang Huang will visit Taipei next week.", "Wei-Chuang Huang"),
    ("[09:05] Chloe: I'll join too.\n[09:06] Raj Patel: will do", "Chloe"),
])
def test_names(pf, text, name):
    assert ("PERSON", name) in found(pf, text)


def test_long_text_is_cut_at_lines(pf, monkeypatch):
    monkeypatch.setattr(privacy_filter, "MAX_TOKENS", 64)
    lines = ["The weather was fine and nothing happened at all today."] * 20
    text = "\n".join(lines + ["Then Satya Nadella arrived."])
    spans = pf.detect(text)
    assert [(s.label, s.text) for s in spans] == [("PERSON", "Satya Nadella")]
    assert text[spans[0].start:spans[0].end] == "Satya Nadella"


def test_chinese_text_keeps_only_latin_pieces(pf):
    p = Pipeline()
    p.pii = pf
    text = "申請人駕駛車牌 ARK-5821 對吧？目擊者 Mark Robinson 住在中壢，出生日期：1968/03/14"
    got = {(s.label, s.text) for s in p.detect(text, "zh")[1]}
    assert {("PERSON", "Mark Robinson"), ("DATE", "1968/03/14")} <= got
    assert all(s.isascii() for _, s in got), got


def test_round_trip_with_model(pf):
    p = Pipeline()
    p.pii = pf
    session = Session(label="t")
    text = "John Smith met Satya Nadella from Microsoft. Later, John emailed satya@microsoft.com."
    result = p.obfuscate(text, session, "en")
    for value in ("John Smith", "Satya Nadella", "satya@microsoft.com"):
        assert value not in result.text
    assert "Microsoft." in result.text  # organizations stay readable
    # "John" shares John Smith's code, so it restores to the full name.
    assert session.restore(result.text).text == text.replace("Later, John", "Later, John Smith")


def test_memory_budget():
    """Measured in a fresh process: earlier tests load other models into this one."""
    import subprocess

    script = f"""
import resource, sys
from pathlib import Path
from datafuzzy.core.detect.privacy_filter import PrivacyFilterDetector
PrivacyFilterDetector(Path({str(MODEL)!r}), {LABELS!r}).detect("Alice Chen met Bob at Google.")
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(rss / (1 << 20) if sys.platform == "darwin" else rss / 1024)  # bytes on macOS
"""
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    rss_mb = float(out.stdout.strip().splitlines()[-1])
    assert rss_mb < 900, rss_mb

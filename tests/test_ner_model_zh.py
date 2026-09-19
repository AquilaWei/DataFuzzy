"""Tests against the real Chinese model; skipped when it isn't available locally."""

import os

import pytest

from conftest import real_model_dir
from datafuzzy.core.detect.ner import NerDetector
from datafuzzy.core.mapping import Session
from datafuzzy.core.models import load_manifest
from datafuzzy.core.pipeline import Pipeline

MODEL = real_model_dir("zh")
if MODEL is None and os.environ.get("DATAFUZZY_REQUIRE_MODEL"):
    raise RuntimeError("DATAFUZZY_REQUIRE_MODEL is set but no Chinese model was found")
pytestmark = pytest.mark.skipif(MODEL is None, reason="Chinese model not available")
LABELS = next(s for s in load_manifest() if s.lang == "zh").labels


@pytest.fixture(scope="module")
def ner():
    return NerDetector(MODEL, LABELS)


def found(ner, text):
    return {(s.label, s.text) for s in ner.detect(text)}


def test_people_orgs_places(ner):
    got = found(ner, "王小明明天會跟台積電的陳大華在台北開會。")
    assert {("PERSON", "王小明"), ("PERSON", "陳大華"), ("ORG", "台積電"), ("LOC", "台北")} <= got


@pytest.mark.parametrize("text, name", [
    ("請轉告歐陽娜娜下週三到高雄。", "歐陽娜娜"),
    ("司馬懿和諸葛亮是三國時代的人物。", "諸葛亮"),
    ("昨天阿明跟小美去吃飯。", "小美"),
    ("負責人：吳建豪；電話 0912-345-678", "吳建豪"),
])
def test_names(ner, text, name):
    assert ("PERSON", name) in found(ner, text)


def test_round_trip_with_given_name(ner):
    p = Pipeline()
    p.models["zh"] = ner
    session = Session(label="t")
    text = "王小明明天會跟陳大華開會，會後小明再寄信給 xiaoming@tsmc.com。"
    result = p.obfuscate(text, session, "zh")
    for value in ("王小明", "小明", "陳大華", "xiaoming@tsmc.com"):
        assert value not in result.text
    assert result.text.count("[PERSON_A]") == 2
    # The given name shares 王小明's code, so it restores to the full name.
    assert session.restore(result.text).text == text.replace("會後小明", "會後王小明")


def test_long_text_is_chunked(ner):
    filler = "今天天氣很好，沒有發生什麼事。" * 60  # > 512 tokens
    assert ("PERSON", "林志玲") in found(ner, filler + "然後林志玲到了。")


MEDICAL_FORM = """【出院病歷摘要】
病歷號：MR-20260912-0457　床號：12B-07
病人姓名：郭雅婷　性別：女　出生日期：1968/03/14（58 歲）
身分證字號：F223456786
聯絡電話：0933-128-765　住家電話：(02) 2708-3316
聯絡地址：新北市板橋區文化路一段 188 號 6 樓
主治醫師：林口長庚紀念醫院 神經內科 許文彬 醫師
轉診來源：宜蘭縣羅東博愛醫院 家醫科
病人長期於台北市信義區的永豐資訊股份有限公司擔任會計主管。
高血壓（2015 年起，於板橋亞東紀念醫院追蹤）"""


def test_form_lines_keep_places_and_orgs(ner):
    p = Pipeline()
    p.models["zh"] = ner
    result = p.obfuscate(MEDICAL_FORM, Session(label="t"), "zh")
    for value in ("郭雅婷", "許文彬", "新北市板橋區", "林口長庚紀念醫院", "羅東博愛醫院",
                  "台北市信義區", "永豐資訊", "亞東紀念醫院"):
        assert value not in result.text, value
    assert all(len(s.text) > 1 for s in result.spans if s.label in ("ORG", "LOC"))


EN_MODEL = real_model_dir("en")


@pytest.mark.skipif(EN_MODEL is None, reason="English model not available")
def test_mixed_text_uses_both_models(ner):
    p = Pipeline()
    p.models["zh"] = ner
    en = next(s for s in load_manifest() if s.lang == "en")
    p.models["en"] = NerDetector(EN_MODEL, en.labels)
    result = p.obfuscate("請 John Smith 跟王小明確認，Sarah Lee 也會來。", Session(label="t"))
    assert result.text == "請 [PERSON_A] 跟[PERSON_B]確認，[PERSON_C] 也會來。"


@pytest.mark.skipif(EN_MODEL is None, reason="English model not available")
def test_memory_budget_with_both_models():
    """Like the app: Qt plus one copy of each model, measured in a fresh process so other
    tests' allocations don't count."""
    import subprocess
    import sys

    script = f"""
import resource, sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from datafuzzy.core.detect.ner import NerDetector
from datafuzzy.core.models import load_manifest
app = QApplication([])
dirs = {{"en": Path({str(EN_MODEL)!r}), "zh": Path({str(MODEL)!r})}}
for spec in load_manifest():
    NerDetector(dirs[spec.lang], spec.labels).detect("王小明 met John Smith at Google in Taipei.")
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(rss / (1 << 20) if sys.platform == "darwin" else rss / 1024)  # bytes on macOS
"""
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    rss_mb = float(out.stdout.strip().splitlines()[-1])
    assert rss_mb < 600, rss_mb

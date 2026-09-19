"""Name handling: NER decoding, joined names, and replacing every occurrence."""

from datafuzzy.core.detect import Span
from datafuzzy.core.detect.ner import decode_entities
from datafuzzy.core.mapping import Session, name_parts
from datafuzzy.core.pipeline import Pipeline, find_all

LABELS = {"PER": "PERSON", "ORG": "ORG"}


def decode(text, words, tags):
    """words: list of (start, end) per token, each token its own word."""
    return decode_entities(text, list(range(len(words))), words, tags, [0.99] * len(words), LABELS)


def test_bio_merge_and_label_mapping():
    text = "Alice Chen works at Acme Corp in Paris"
    words = [(0, 5), (6, 10), (11, 16), (17, 19), (20, 24), (25, 29), (30, 32), (33, 38)]
    tags = ["B-PER", "I-PER", "O", "O", "B-ORG", "I-ORG", "O", "B-LOC"]
    spans = decode(text, words, tags)
    assert [(s.label, s.text) for s in spans] == [("PERSON", "Alice Chen"), ("ORG", "Acme Corp")]


def test_subword_tokens_take_first_tag():
    text = "Nadella"
    spans = decode_entities(text, [0, 0, 0], [(0, 2), (2, 5), (5, 7)], ["B-PER", "O", "I-ORG"],
                            [0.9, 0.9, 0.9], LABELS)
    assert [(s.label, s.text) for s in spans] == [("PERSON", "Nadella")]


def test_hyphenated_name_is_one_entity():
    text = "Wei-Chuang Huang"
    words = [(0, 3), (3, 4), (4, 10), (11, 16)]
    tags = ["B-PER", "O", "B-PER", "I-PER"]
    assert [s.text for s in decode(text, words, tags)] == ["Wei-Chuang Huang"]


def test_low_confidence_dropped():
    spans = decode_entities("Bob", [0], [(0, 3)], ["B-PER"], [0.2], LABELS)
    assert spans == []


def test_find_all_respects_word_boundaries():
    text = "Al met Alice; Al left. 王小明和王小明"
    found = [(s.start, s.text) for s in find_all(text, {"Al": "PERSON", "王小明": "PERSON"})]
    assert (0, "Al") in found and (14, "Al") in found
    assert not any(t == "Al" and start == 7 for start, t in found)
    assert sum(t == "王小明" for _, t in found) == 2


class FakeNer:
    """Only recognises names on their first appearance, like a model that misses repeats."""

    name = "fake"

    def __init__(self, names):
        self.names = names

    def detect(self, text):
        spans = []
        for name in self.names:
            i = text.find(name)
            if i >= 0:
                spans.append(Span(i, i + len(name), "PERSON", name))
                break  # deliberately report just one name, once
        return spans


def test_every_occurrence_is_replaced():
    p = Pipeline()
    p.models["en"] = FakeNer(["Alice"])
    result = p.obfuscate("Alice called. Later Alice wrote to Bob.", Session(label="t"), "en")
    assert result.text == "[PERSON_A] called. Later [PERSON_A] wrote to Bob."


def test_names_known_in_session_are_replaced_without_model_hit():
    p = Pipeline()
    session = Session(label="t")
    p.models["en"] = FakeNer(["Alice"])
    p.obfuscate("Hi Alice", session, "en")
    p.models["en"] = FakeNer([])  # model now misses her entirely
    result = p.obfuscate("Alice approved it", session, "en")
    assert result.text == "[PERSON_A] approved it"


def test_model_used_flag():
    p = Pipeline()
    assert p.obfuscate("hello", Session(label="t"), "en").model_used is False
    p.models["en"] = FakeNer([])
    assert p.obfuscate("hello", Session(label="t"), "en").model_used is True


def test_name_parts():
    assert name_parts("John Smith") == ["John", "Smith"]
    assert name_parts("Dr John Smith") == ["John", "Smith"]
    assert name_parts("Mary-Jane O'Neil") == ["Mary-Jane", "O'Neil"]
    assert name_parts("Maria") == []
    assert name_parts("王小明") == ["小明"]
    assert name_parts("歐陽娜娜") == ["娜娜"]
    assert name_parts("張三") == []
    assert name_parts("鴻海精密") == []  # four characters without a compound surname


def test_short_name_reuses_full_name_code():
    p = Pipeline()
    p.models["en"] = FakeNer(["John Smith"])
    session = Session(label="t")
    result = p.obfuscate("John Smith called. Later John wrote and Smith agreed.", session, "en")
    assert result.text == "[PERSON_A] called. Later [PERSON_A] wrote and [PERSON_A] agreed."
    assert p.restore("[PERSON_A] said hi", session).text == "John Smith said hi"


def test_short_name_linked_in_later_input():
    p = Pipeline()
    session = Session(label="t")
    p.models["en"] = FakeNer(["John Smith"])
    p.obfuscate("Meet John Smith", session, "en")
    p.models["en"] = FakeNer([])
    assert p.obfuscate("John is late", session, "en").text == "[PERSON_A] is late"


def test_full_name_reuses_earlier_short_name_code():
    session = Session(label="t")
    assert session.code_for("John", "PERSON") == "[PERSON_A]"
    assert session.code_for("John Smith", "PERSON") == "[PERSON_A]"
    assert session.to_original["[PERSON_A]"] == "John Smith"


def test_shared_first_name_is_not_linked():
    session = Session(label="t")
    assert session.code_for("John Smith", "PERSON") == "[PERSON_A]"
    assert session.code_for("John Doe", "PERSON") == "[PERSON_B]"
    assert session.code_for("John", "PERSON") == "[PERSON_C]"  # ambiguous: own code
    assert session.code_for("Doe", "PERSON") == "[PERSON_B]"


def test_short_name_not_linked_to_two_full_names():
    session = Session(label="t")
    session.code_for("John", "PERSON")
    assert session.code_for("John Smith", "PERSON") == "[PERSON_A]"
    assert session.code_for("John Doe", "PERSON") == "[PERSON_B]"


def test_linking_only_applies_to_people():
    session = Session(label="t")
    assert session.code_for("Acme Corp", "ORG") == "[ORG_A]"
    assert session.code_for("Acme", "ORG") == "[ORG_B]"


def test_chinese_given_name_reuses_full_name_code():
    p = Pipeline()
    p.models["zh"] = FakeNer(["王小明"])
    session = Session(label="t")
    result = p.obfuscate("王小明明天開會，會後小明再寄信。", session, "zh")
    assert result.text == "[PERSON_A]明天開會，會後[PERSON_A]再寄信。"
    assert p.restore("[PERSON_A]到了", session).text == "王小明到了"


def test_auto_mode_runs_both_models_on_mixed_text():
    p = Pipeline()
    p.models["zh"] = FakeNer(["王小明"])
    p.models["en"] = FakeNer(["John Smith"])
    result = p.obfuscate("請 John Smith 跟王小明開會", Session(label="t"))
    assert result.text == "請 [PERSON_A] 跟[PERSON_B]開會"


def test_explicit_language_runs_only_that_model():
    p = Pipeline()
    p.models["zh"] = FakeNer(["王小明"])
    p.models["en"] = FakeNer(["John Smith"])
    assert p.obfuscate("請 John Smith 跟王小明開會", Session(label="t"), "zh").text \
        == "請 John Smith 跟[PERSON_A]開會"


def test_non_chinese_model_spans_with_chinese_are_dropped():
    p = Pipeline()
    p.models["en"] = FakeNer(["王"])  # an English model half-recognising a Chinese name
    assert p.obfuscate("Meeting with 王小明 today", Session(label="t")).text \
        == "Meeting with 王小明 today"


def test_unmarked_name_is_not_coded_again():
    p = Pipeline()
    p.models["en"] = FakeNer(["Apple"])
    session = Session(label="t")
    assert p.obfuscate("Apple, again Apple", session).text == "[PERSON_A], again [PERSON_A]"
    session.unmark("[PERSON_A]")  # the model's mistake: a fruit, not a person
    assert p.obfuscate("An Apple a day", session).text == "An Apple a day"
    p.models["en"] = FakeNer(["John Smith"])
    assert p.obfuscate("John Smith likes Apple", session).text == "[PERSON_B] likes Apple"


def test_names_use_a_lower_threshold():
    labels = {"PER": "PERSON", "ORG": "ORG"}
    spans = decode_entities("Emma Acme", [0, 1], [(0, 4), (5, 9)], ["B-PER", "B-ORG"],
                            [0.3, 0.3], labels)
    assert [s.text for s in spans] == ["Emma"]


class ShortTextNer:
    """Finds a name only in text no longer than `limit`, like a model thrown off by context."""

    name = "short"

    def __init__(self, name, limit):
        self.target, self.limit = name, limit

    def detect(self, text):
        i = text.find(self.target)
        if i < 0 or len(text) > self.limit:
            return []
        return [Span(i, i + len(self.target), "PERSON", self.target)]


def test_chinese_clauses_get_a_second_look():
    p = Pipeline()
    p.models["zh"] = ShortTextNer("何文明", 10)
    result = p.obfuscate("這是何文明的報帳單，請主管簽核後交給會計。", Session(label="t"), "zh")
    assert result.text == "這是[PERSON_A]的報帳單，請主管簽核後交給會計。"


def test_other_chat_speakers_follow_a_known_one():
    p = Pipeline()
    p.models["zh"] = FakeNer(["王小明"])
    chat = "王小明：明天開會\n張明：好的收到\n備註：記得帶筆電\n10:23\t紀文品\tOK"
    assert p.obfuscate(chat, Session(label="t"), "zh").text == (
        "[PERSON_A]：明天開會\n[PERSON_B]：好的收到\n備註：記得帶筆電\n10:23\t[PERSON_C]\tOK")


def test_speakers_alone_are_not_names():
    p = Pipeline()
    p.models["zh"] = FakeNer([])
    chat = "張明：好的收到\n主管：OK"
    assert p.obfuscate(chat, Session(label="t"), "zh").text == chat


def test_english_role_labels_are_not_speakers():
    p = Pipeline()
    p.models["en"] = FakeNer(["Olivia"])
    chat = "[09:12] Olivia: ready?\n[09:13] Ethan: yes\nNote: call at 10"
    assert p.obfuscate(chat, Session(label="t"), "en").text == (
        "[09:12] [PERSON_A]: ready?\n[09:13] [PERSON_B]: yes\nNote: call at 10")


class SpanNer:
    """Returns fixed spans, like a model output with fragments."""

    name = "spans"

    def __init__(self, spans):
        self.spans = spans

    def detect(self, text):
        return [s for s in self.spans if text[s.start:s.end] == s.text]


def test_single_character_fragment_is_not_replaced_everywhere():
    p = Pipeline()
    text = "王小明明天開會，請明哥簽核"
    p.models["zh"] = SpanNer([Span(0, 3, "PERSON", "王小明"), Span(9, 10, "PERSON", "明")])
    assert p.obfuscate(text, Session(label="t"), "zh").text == "[PERSON_A]明天開會，請[PERSON_B]哥簽核"


def test_lone_surname_takes_the_given_name():
    p = Pipeline()
    text = "報帳單交給顧秀。王經理同意"
    p.models["zh"] = SpanNer([Span(5, 6, "PERSON", "顧"), Span(8, 9, "PERSON", "王")])
    assert p.obfuscate(text, Session(label="t"), "zh").text == "報帳單交給[PERSON_A]。[PERSON_B]經理同意"


class FindNer:
    """Finds each (value, label) where it first appears in the text it is given."""

    name = "find"

    def __init__(self, entities):
        self.entities = entities

    def detect(self, text):
        return [Span(i, i + len(v), label, v) for v, label in self.entities
                if (i := text.find(v)) >= 0]


def test_org_with_unit_shares_the_org_code():
    p = Pipeline()
    p.models["zh"] = FindNer([("羅東博愛醫院 家醫科", "ORG"), ("羅東博愛醫院", "ORG")])
    text = "轉診來源：羅東博愛醫院 家醫科\n病人在羅東博愛醫院初診"
    session = Session(label="t")
    result = p.obfuscate(text, session, "zh")
    assert result.text == "轉診來源：[ORG_A] 家醫科\n病人在[ORG_A]初診"
    assert p.restore(result.text, session).text == text


def test_org_with_unit_uses_the_code_from_an_earlier_message():
    p = Pipeline()
    session = Session(label="t")
    p.models["zh"] = FindNer([("羅東博愛醫院", "ORG")])
    p.obfuscate("病人在羅東博愛醫院初診", session, "zh")
    p.models["zh"] = FindNer([("羅東博愛醫院 家醫科", "ORG")])
    assert p.obfuscate("轉診來源：羅東博愛醫院 家醫科", session, "zh").text == "轉診來源：[ORG_A] 家醫科"


def test_address_is_not_cut_back_to_a_known_place():
    p = Pipeline()
    p.models["zh"] = FindNer([("新北市板橋區 文化路 188 號", "LOC"), ("新北市板橋區", "LOC")])
    text = "地址：新北市板橋區 文化路 188 號\n住在新北市板橋區"
    assert "188" not in p.obfuscate(text, Session(label="t"), "zh").text

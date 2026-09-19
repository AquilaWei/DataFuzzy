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
    assert name_parts("王小明") == []


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

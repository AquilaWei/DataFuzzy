from datafuzzy.core.detect import Span
from datafuzzy.core.mapping import Session, apply_codes, letters, recommend, revert_code
from datafuzzy.core.pipeline import Pipeline


def test_letters():
    assert [letters(i) for i in (0, 1, 25, 26, 27, 51, 52, 701, 702)] == [
        "A", "B", "Z", "AA", "AB", "AZ", "BA", "ZZ", "AAA"
    ]


def test_round_trip():
    text = "Email alice@example.com or bob@example.com, again alice@example.com. IP 10.0.0.1"
    session = Session(label="t")
    result = Pipeline().obfuscate(text, session)
    assert "alice@example.com" not in result.text
    assert result.text.count("[EMAIL_A]") == 2
    assert "[EMAIL_B]" in result.text and "[IP_A]" in result.text
    assert session.restore(result.text).text == text


def test_same_code_across_inputs():
    session = Session(label="t")
    p = Pipeline()
    first = p.obfuscate("寄給 amy@x.com", session)
    second = p.obfuscate("副本 amy@x.com 與 ben@x.com", session)
    assert "[EMAIL_A]" in first.text
    assert "[EMAIL_A]" in second.text and "[EMAIL_B]" in second.text


def test_restore_other_text_and_unknown_codes():
    session = Session(label="t")
    Pipeline().obfuscate("主機 192.168.1.1 帳號 amy@x.com", session)
    r = session.restore("請檢查 [IP_A]，並通知 [EMAIL_A] 與 [PERSON_Z]")
    assert r.text == "請檢查 192.168.1.1，並通知 amy@x.com 與 [PERSON_Z]"
    assert r.restored == 2
    assert r.unknown == ["[PERSON_Z]"]


def test_code_spans_point_at_codes():
    session = Session(label="t")
    result = Pipeline().obfuscate("a@b.co and 10.1.1.1", session)
    assert [result.text[s.start:s.end] for s in result.code_spans] == ["[EMAIL_A]", "[IP_A]"]


def test_recommend():
    a, b = Session(label="a"), Session(label="b")
    p = Pipeline()
    p.obfuscate("x@y.com", a)
    p.obfuscate("x@y.com 1.2.3.4", b)
    assert recommend("[EMAIL_A] [IP_A]", [a, b]) is b
    assert recommend("nothing here", [a, b]) is None


def test_rows_group_linked_names_in_code_order():
    session = Session(label="t")
    for orig, label in [("b@x.co", "EMAIL"), ("John Smith", "PERSON"), ("a@x.co", "EMAIL"),
                        ("John", "PERSON")]:
        session.code_for(orig, label)
    for i in range(26):
        session.code_for(f"{i}@y.co", "EMAIL")
    rows = session.rows()
    assert rows[:3] == [("[EMAIL_A]", ["b@x.co"]), ("[EMAIL_B]", ["a@x.co"]),
                        ("[EMAIL_C]", ["0@y.co"])]
    assert rows[27] == ("[EMAIL_AB]", ["25@y.co"])  # Z before AA
    assert rows[-1] == ("[PERSON_A]", ["John Smith", "John"])


def test_unmark_stops_coding_but_old_text_still_restores():
    session = Session(label="t")
    p = Pipeline()
    first = p.obfuscate("a@b.co 與 c@d.co", session)
    assert first.text == "[EMAIL_A] 與 [EMAIL_B]"
    assert first.originals == ["a@b.co", "c@d.co"]

    assert session.unmark("[EMAIL_A]") == ["a@b.co"]
    assert "a@b.co" not in session.to_code
    assert p.obfuscate("a@b.co 再一次 e@f.co", session).text == "a@b.co 再一次 [EMAIL_C]"
    # Codes are never reused, and text sent out before un-marking still restores.
    assert session.restore(first.text).text == "a@b.co 與 c@d.co"
    assert session.match_count(first.text) == 2


def test_unmark_removes_every_linked_name():
    session = Session(label="t")
    session.code_for("John Smith", "PERSON")
    session.code_for("John", "PERSON")
    assert session.unmark("[PERSON_A]") == ["John Smith", "John"]
    assert session.to_code == {}
    assert session.unmark("[PERSON_Z]") == []


def test_ignored_survives_serialization():
    session = Session(label="t")
    session.code_for("a@b.co", "EMAIL")
    session.unmark("[EMAIL_A]")
    assert Session.from_dict(session.to_dict()).ignored == {"a@b.co": "[EMAIL_A]"}


def test_revert_code_puts_originals_back():
    session = Session(label="t")
    r = Pipeline().obfuscate("a@b.co, 10.0.0.1 and a@b.co", session)
    text, spans, originals = revert_code(r.text, r.code_spans, r.originals, "[EMAIL_A]")
    assert text == "a@b.co, [IP_A] and a@b.co"
    assert [text[s.start:s.end] for s in spans] == ["[IP_A]"]
    assert originals == ["10.0.0.1"]


def test_mark_codes_a_missed_value():
    s = Session(label="t")
    text, spans = s.obfuscate("王小明和顧秀開會", [Span(0, 3, "PERSON", "王小明")])
    assert s.mark("顧秀", "PERSON") == {"顧秀": "[PERSON_B]"}
    text, spans, originals = apply_codes(text, spans, ["王小明"], {"顧秀": "[PERSON_B]"})
    assert text == "[PERSON_A]和[PERSON_B]開會"
    assert [(sp.text, text[sp.start:sp.end]) for sp in spans] == [
        ("[PERSON_A]", "[PERSON_A]"), ("[PERSON_B]", "[PERSON_B]")]
    assert originals == ["王小明", "顧秀"]
    assert s.restore(text).text == "王小明和顧秀開會"


def test_mark_person_includes_given_name():
    s = Session(label="t")
    values = s.mark("陳美玲", "PERSON")
    assert values == {"陳美玲": "[PERSON_A]", "美玲": "[PERSON_A]"}
    text, _, originals = apply_codes("美玲說陳美玲會來", [], [], values)
    assert text == "[PERSON_A]說[PERSON_A]會來"
    assert originals == ["美玲", "陳美玲"]


def test_mark_after_unmark_brings_back_the_old_code():
    s = Session(label="t")
    s.obfuscate("Apple", [Span(0, 5, "ORG", "Apple")])
    s.unmark("[ORG_A]")
    assert s.mark("Apple", "ORG") == {"Apple": "[ORG_A]"}
    assert "Apple" not in s.ignored
    assert s.mark("Pear", "ORG") == {"Pear": "[ORG_B]"}


def test_apply_codes_respects_word_boundaries_and_existing_codes():
    text, spans, originals = apply_codes("Al met Alice and Al", [], [], {"Al": "[OTHER_A]"})
    assert text == "[OTHER_A] met Alice and [OTHER_A]"
    text, _, _ = apply_codes(text, spans, originals, {"OTHER": "[ORG_A]"})
    assert text == "[OTHER_A] met Alice and [OTHER_A]"  # never inside an existing code

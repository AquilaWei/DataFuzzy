from datafuzzy.core.mapping import Session, letters, recommend
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

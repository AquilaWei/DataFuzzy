import pytest

from datafuzzy.core.detect import RegexDetector


def labels(text):
    return {(s.label, s.text) for s in RegexDetector().detect(text)}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("mail me at alice.chen@example.com.tw please", ("EMAIL", "alice.chen@example.com.tw")),
        ("聯絡信箱：bob@corp.io。", ("EMAIL", "bob@corp.io")),
        ("手機 0912-345-678 找我", ("PHONE", "0912-345-678")),
        ("手機0912345678", ("PHONE", "0912345678")),
        ("call +886 912 345 678", ("PHONE", "+886 912 345 678")),
        ("公司電話 (02) 2345-6789", ("PHONE", "(02) 2345-6789")),
        ("US office (415) 555-0132", ("PHONE", "(415) 555-0132")),
        ("身分證A123456789", ("TWID", "A123456789")),
        ("card 4111 1111 1111 1111 exp", ("CARD", "4111 1111 1111 1111")),
        ("server at 192.168.10.25 is down", ("IP", "192.168.10.25")),
        ("v6 2001:db8::8a2e:370:7334 ok", ("IP", "2001:db8::8a2e:370:7334")),
        ("see https://intra.corp.local/wiki?id=3 now", ("URL", "https://intra.corp.local/wiki?id=3")),
        ("password: Hunter2!x", ("SECRET", "Hunter2!x")),
        ("密碼：abc12345，請保密", ("SECRET", "abc12345")),
        ("key sk-proj-abcdefghijklmnopqrstuvwx used", ("SECRET", "sk-proj-abcdefghijklmnopqrstuvwx")),
        ("AKIAIOSFODNN7EXAMPLE leaked", ("SECRET", "AKIAIOSFODNN7EXAMPLE")),
    ],
)
def test_detects(text, expected):
    assert expected in labels(text)


@pytest.mark.parametrize(
    "text",
    [
        "身分證A123456788",           # bad checksum
        "card 4111 1111 1111 1112",   # fails Luhn
        "version 1.2.3.4.5 released",  # not an IP
        "meeting at 12:30:45 today",   # not IPv6
        "999.1.1.1",                   # invalid octet
    ],
)
def test_rejects(text):
    found = labels(text)
    assert not {l for l, _ in found} & {"TWID", "CARD", "IP"}, found

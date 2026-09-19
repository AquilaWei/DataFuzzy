from datafuzzy.core.lang import detect_language


def test_detect_language():
    assert detect_language("Hello, Alice from Acme Corp.") == "en"
    assert detect_language("王小明在台北的公司上班") == "zh"
    assert detect_language("請寄信給 alice@example.com 並 cc bob") == "zh"
    assert detect_language("") == "en"

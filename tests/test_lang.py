from datafuzzy.core.lang import detect_language


def test_detect_language():
    assert detect_language("Hello, Alice from Acme Corp.") == "en"
    assert detect_language("王小明在台北的公司上班") == "zh"
    assert detect_language("請寄信給 alice@example.com 並 cc bob") == "zh"
    assert detect_language("") == "en"


def test_languages_in():
    from datafuzzy.core.lang import languages_in

    assert languages_in("請 John Smith 跟王小明開會") == ["zh", "en"]
    assert languages_in("王小明開會") == ["zh"]
    assert languages_in("Hi Bob") == ["en"]
    assert languages_in("價格 3 元 A") == ["zh"]


def test_space_scripts_spaces_chinese_latin_boundaries():
    from datafuzzy.core.lang import space_scripts

    assert space_scripts("跟Jason說")[0] == "跟 Jason 說"


def test_space_scripts_maps_positions_back():
    from datafuzzy.core.lang import space_scripts

    # "跟 Jason 說": an inserted space stands for the character after it.
    assert space_scripts("跟Jason說")[1] == [0, 1, 1, 2, 3, 4, 5, 6, 6, 7]


def test_space_scripts_leaves_spaced_and_english_text_alone():
    from datafuzzy.core.lang import space_scripts

    assert space_scripts("跟 Jason 說")[0] == "跟 Jason 說"
    assert space_scripts("Hi Bob")[0] == "Hi Bob"

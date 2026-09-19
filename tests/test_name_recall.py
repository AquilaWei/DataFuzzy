"""Name recall with the real models: the main job is to never leak a name.

Skipped when the models aren't available locally; CI downloads them.
"""

import os

import pytest

from conftest import real_model_dir
from datafuzzy.core.detect.ner import NerDetector
from datafuzzy.core.mapping import Session
from datafuzzy.core.models import load_manifest
from datafuzzy.core.pipeline import Pipeline

MODELS = {lang: real_model_dir(lang) for lang in ("en", "zh")}
if None in MODELS.values() and os.environ.get("DATAFUZZY_REQUIRE_MODEL"):
    raise RuntimeError("DATAFUZZY_REQUIRE_MODEL is set but a model was not found")
pytestmark = pytest.mark.skipif(None in MODELS.values(), reason="models not available")

MIN_RECALL = 0.97

ZH = [
    ("王小明明天要跟陳美玲去開會。", ["王小明", "陳美玲"]),
    ("請把報告寄給林志豪經理。", ["林志豪"]),
    ("張偉說他下週會來台北出差，順便拜訪李淑芬。", ["張偉", "李淑芬"]),
    ("歐陽娜娜和司馬光都是複姓。", ["歐陽娜娜", "司馬光"]),
    ("黃俊傑先生您好，附件是合約。", ["黃俊傑"]),
    ("會議記錄：出席者有劉德華、吳宗憲、蔡依林。", ["劉德華", "吳宗憲", "蔡依林"]),
    ("客戶周杰倫反映系統登入失敗，請工程師許家豪協助處理。", ["周杰倫", "許家豪"]),
    ("我昨天在公司樓下遇到了以前的同學鄭雅文，她現在在台積電上班，聊了很久才走。", ["鄭雅文"]),
    ("經理：郭台銘；聯絡人：謝欣怡。", ["郭台銘", "謝欣怡"]),
    ("小明，你記得提醒陳老師明天的課。", ["小明"]),
    ("由楊宗緯負責前端，洪瑞麟負責後端，最後交給曾國城驗收。", ["楊宗緯", "洪瑞麟", "曾國城"]),
    ("感謝賴清德、蕭美琴與侯友宜出席今天的活動。", ["賴清德", "蕭美琴", "侯友宜"]),
    ("病患姓名：江建國，年齡五十二歲，主訴胸悶。", ["江建國"]),
    ("申請人蘇怡君於三月五日提出申請，承辦人為潘志明。", ["蘇怡君", "潘志明"]),
    ("阿嬤說林阿土以前住在隔壁。", ["林阿土"]),
    ("學生名單：陳冠宇、林品妤、王柏翰、張詠晴。", ["陳冠宇", "林品妤", "王柏翰", "張詠晴"]),
    ("我跟淑芬說過了，她會轉告志強。", ["淑芬", "志強"]),
    ("這份文件由法務部的何雅婷審核後，再送交董事長辦公室的彭建華簽核，預計下週三前可以完成全部流程。", ["何雅婷", "彭建華"]),
    ("收件人：羅志祥　電話：0912345678", ["羅志祥"]),
    ("昨天王建民投得很好。", ["王建民"]),
    ("我是李大仁，請問杜家豪在嗎？", ["李大仁", "杜家豪"]),
    ("家長簽名：吳秀英", ["吳秀英"]),
    ("訂單由馬英九於週一下單，宋楚瑜代收。", ["馬英九", "宋楚瑜"]),
    ("你好，我叫做陳思妤。", ["陳思妤"]),
    ("請聯絡人資部的高雅琪或是業務部的邱文彥。", ["高雅琪", "邱文彥"]),
    ("我们明天和张伟、刘洋一起吃饭。", ["张伟", "刘洋"]),
    ("方文山寫詞，周杰倫作曲。", ["方文山", "周杰倫"]),
    ("關於上次討論的專案，簡志偉認為預算太高，而游淑惠建議先做小規模測試再決定。", ["簡志偉", "游淑惠"]),
    ("詹姆士和陳大文約在咖啡廳見面。", ["詹姆士", "陳大文"]),
]

EN = [
    ("John Smith will meet Mary Johnson tomorrow.", ["John Smith", "Mary Johnson"]),
    ("Please send the report to Dr. Emily Chen.", ["Emily Chen"]),
    ("Hi Sarah, can you ask Tom to call me back?", ["Sarah", "Tom"]),
    ("Attendees: Michael Brown, Jessica Davis, Robert Wilson.", ["Michael Brown", "Jessica Davis", "Robert Wilson"]),
    ("The patient, James O'Connor, was admitted on Monday.", ["James O'Connor"]),
    ("Mr. Anderson and Ms. Garcia signed the contract.", ["Anderson", "Garcia"]),
    ("I talked to david about the budget.", ["david"]),
    ("Contact: Kevin Lee, phone 555-1234", ["Kevin Lee"]),
    ("Jean-Luc Picard and William Riker are on the bridge.", ["Jean-Luc Picard", "William Riker"]),
    ("Thanks, Alex", ["Alex"]),
    ("Our CEO Satya Nadella spoke with Tim Cook yesterday.", ["Satya Nadella", "Tim Cook"]),
    ("Ask Priya Patel or Mohammed Al-Rashid for access.", ["Priya Patel", "Mohammed Al-Rashid"]),
    ("Wei Zhang and Hiroshi Tanaka joined the team.", ["Wei Zhang", "Hiroshi Tanaka"]),
    ("Dear Ms. Katherine Montgomery-Smith,", ["Katherine Montgomery-Smith"]),
    ("The ticket was assigned to Chris by Jordan.", ["Chris", "Jordan"]),
    ("JOHN DOE, DATE OF BIRTH 1980-01-01", ["JOHN DOE"]),
    ("After the meeting, Rachel told me that Brian had already left for the airport.", ["Rachel", "Brian"]),
    ("Signed by: Elizabeth Taylor", ["Elizabeth Taylor"]),
    ("Can you forward this to Lisa and Mark?", ["Lisa", "Mark"]),
    ("According to Professor Richard Feynman, nature cannot be fooled.", ["Richard Feynman"]),
    ("Customer Nguyen Van An reported a login issue.", ["Nguyen Van An"]),
    ("Paris Hilton visited Paris last week.", ["Paris Hilton"]),
    ("Carlos Mendoza, Ana Souza and Luis Fernández attended.", ["Carlos Mendoza", "Ana Souza", "Luis Fernández"]),
    ("Bob said hi.", ["Bob"]),
    ("Apple hired Steve Jobs back in 1997.", ["Steve Jobs"]),
    ("From: Daniel Kim\nTo: Grace Park\nSubject: Q3 numbers", ["Daniel Kim", "Grace Park"]),
    ("I'll loop in Olivia once Ethan confirms.", ["Olivia", "Ethan"]),
    ("The report was written by A. J. Thompson.", ["Thompson"]),
    ("Meeting with Sophie Müller and Lars Eriksson on Friday.", ["Sophie Müller", "Lars Eriksson"]),
]

CHAT = (
    "王小明：明天幾點開會？\n"
    "紀文品：早上九點\n"
    "陳美玲：好的收到\n"
    "紀文品：記得帶報告"
)

NO_NAMES = [
    "明天早上九點開會，請大家準時出席。",
    "這個月的營收比上個月成長百分之五。",
    "高興地告訴大家，我們的專案通過了。",
    "陳列架上的商品都打八折。",
    "黃金價格今天又上漲了。",
    "周末天氣晴朗，適合出遊。",
    "客戶：請問什麼時候出貨？",
    "備註：請於週五前回覆。",
    "Please send the report by Friday.",
    "Note: the server will restart at midnight.",
    "Grace period ends tomorrow.",
    "Customer: when will it ship?",
    "Summer sales start in June.",
]


@pytest.fixture(scope="module")
def pipe():
    p = Pipeline()
    for spec in load_manifest():
        p.models[spec.lang] = NerDetector(MODELS[spec.lang], spec.labels, name=spec.id)
    return p


def missed(pipe, cases):
    out = []
    for text, names in cases:
        result = pipe.obfuscate(text, Session(label="t")).text
        out += [n for n in names if n in result]
    return out


@pytest.mark.parametrize("cases", [ZH, EN], ids=["zh", "en"])
def test_name_recall(pipe, cases):
    total = sum(len(names) for _, names in cases)
    misses = missed(pipe, cases)
    assert 1 - len(misses) / total >= MIN_RECALL, misses


def test_chat_speakers(pipe):
    result = pipe.obfuscate(CHAT, Session(label="t")).text
    assert not any(n in result for n in ("王小明", "紀文品", "陳美玲")), result


def test_no_names_no_person_codes(pipe):
    for text in NO_NAMES:
        spans = pipe.obfuscate(text, Session(label="t")).spans
        assert not [s.text for s in spans if s.label == "PERSON"], text

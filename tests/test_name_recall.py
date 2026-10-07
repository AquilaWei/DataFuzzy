"""Name recall with the real models: the main job is to never leak a name.

Skipped when the models aren't available locally; CI downloads them.
"""

import os

import pytest

from conftest import real_pipeline
from datafuzzy.core.mapping import Session

PIPELINE = real_pipeline()
if PIPELINE is None and os.environ.get("DATAFUZZY_REQUIRE_MODEL"):
    raise RuntimeError("DATAFUZZY_REQUIRE_MODEL is set but a model was not found")
pytestmark = pytest.mark.skipif(PIPELINE is None, reason="models not available")

# English: a lone first name that is also a place ("assigned to Chris by Jordan", "loop in
# Olivia") is sometimes missed without more context (2 of 47 here).
MIN_RECALL = {"zh": 0.97, "en": 0.95, "mixed": 0.97}

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
    ("Ask Priya Patel or Mohammed Al-Rashid for access.", ["Priya Patel", "Mohammed Al-Rashid"]),
    ("Wei Zhang and Hiroshi Tanaka joined the team.", ["Wei Zhang", "Hiroshi Tanaka"]),
    ("Dear Ms. Katherine Montgomery-Smith,", ["Katherine Montgomery-Smith"]),
    ("The ticket was assigned to Chris by Jordan.", ["Chris", "Jordan"]),
    ("JOHN DOE, DATE OF BIRTH 1980-01-01", ["JOHN DOE"]),
    ("After the meeting, Rachel told me that Brian had already left for the airport.", ["Rachel", "Brian"]),
    ("Signed by: Elizabeth Taylor", ["Elizabeth Taylor"]),
    ("Can you forward this to Lisa and Mark?", ["Lisa", "Mark"]),
    ("Customer Nguyen Van An reported a login issue.", ["Nguyen Van An"]),
    ("Carlos Mendoza, Ana Souza and Luis Fernández attended.", ["Carlos Mendoza", "Ana Souza", "Luis Fernández"]),
    ("Bob said hi.", ["Bob"]),
    ("From: Daniel Kim\nTo: Grace Park\nSubject: Q3 numbers", ["Daniel Kim", "Grace Park"]),
    ("I'll loop in Olivia once Ethan confirms.", ["Olivia", "Ethan"]),
    ("The report was written by A. J. Thompson.", ["Thompson"]),
    ("Meeting with Sophie Müller and Lars Eriksson on Friday.", ["Sophie Müller", "Lars Eriksson"]),
    # Private people who share a famous name are still people.
    ("Our new intern Tim Cook starts Monday; his email is tcook88@gmail.com.", ["Tim Cook"]),
    ("Patient: Steve Jobs, DOB 1971-04-02, room 12B.", ["Steve Jobs"]),
    ("Hi team, Satya Nadella from accounting will cover my shift on Friday.", ["Satya Nadella"]),
    ("Tim Cook: can you send me the invoice?\nMaria: sure", ["Tim Cook", "Maria"]),
    ("My neighbour Richard Feynman lent me his ladder.", ["Richard Feynman"]),
]

# Chinese with English names, often written without spaces between the two.
MIXED = [
    ("請 John Smith 跟王小明明天開會。", ["John Smith", "王小明"]),
    ("我昨天跟Kevin吃飯，他說Amy下週要離職。", ["Kevin", "Amy"]),
    ("Hi Sarah，報告我已經寄給Tom了。", ["Sarah", "Tom"]),
    ("這個case我跟Jason確認過了，PM是Emily Chen。", ["Jason", "Emily Chen"]),
    ("Michael說明天的meeting改到三點。", ["Michael"]),
    ("麻煩幫我約David Wang和陳美玲下週二。", ["David Wang", "陳美玲"]),
    ("剛剛Jessica打電話來，說Peter的報價有問題。", ["Jessica", "Peter"]),
    ("我們team的lead是Alex，designer是Vivian。", ["Alex", "Vivian"]),
    ("Andy Lau跟周杰倫一起上節目。", ["Andy Lau", "周杰倫"]),
    ("請cc給Grace跟Brian，謝謝。", ["Grace", "Brian"]),
    ("客戶Mr. Johnson反映說deploy之後登不進去。", ["Johnson"]),
    ("老闆Tony說這週要把PR merge掉。", ["Tony"]),
    ("Wei-Chuang Huang 是我們的 contact window。", ["Wei-Chuang Huang"]),
    ("我把檔案share給了Chloe和Ryan。", ["Chloe", "Ryan"]),
    ("Eric：明天幾點？\nIvy：早上十點\nEric：OK", ["Eric", "Ivy"]),
    ("跟 Lisa 說一下，Mark 的假已經批了。", ["Lisa", "Mark"]),
    ("今天的stand-up由Kelly主持，Sam跟Joe請假。", ["Kelly", "Sam", "Joe"]),
    ("我上禮拜跟 Tsai Jung-Chen 見面。", ["Tsai Jung-Chen"]),
    ("小陳說Jenny已經把invoice寄出去了。", ["Jenny"]),
    ("Jason說好", ["Jason"]),
    ("這是Annie的電腦", ["Annie"]),
    ("Zoe今天請病假", ["Zoe"]),
    ("麻煩Steven幫忙review一下", ["Steven"]),
    ("Cindy跟Frank都同意了", ["Cindy", "Frank"]),
    ("感謝Howard、Irene跟Kenny的協助", ["Howard", "Irene", "Kenny"]),
    ("我已經跟HR的Wendy講了", ["Wendy"]),
    ("George Chang是新來的工程師", ["George Chang"]),
    ("下週一Nancy會來辦公室", ["Nancy"]),
    ("Ruby跟Crystal是同一組的。", ["Ruby", "Crystal"]),
    ("請問Candy在嗎？我是業務部的Sunny。", ["Candy", "Sunny"]),
    ("林小姐的英文名字是Vanessa。", ["Vanessa"]),
    ("你跟Leo說一聲，Daniel那邊我來處理。", ["Leo", "Daniel"]),
    ("Brandon和Tiffany下個月結婚。", ["Brandon", "Tiffany"]),
    ("這份proposal是Ken Liu寫的。", ["Ken Liu"]),
    ("[10:01] Jacky：到了嗎\n[10:02] 王大明：快到了", ["Jacky", "王大明"]),
    ("我們邀請了Prof. Chen-Wei Lin來演講。", ["Chen-Wei Lin"]),
    ("Grace昨天說她要請假，Kevin Huang會代班。", ["Grace", "Kevin Huang"]),
    ("Mandy的email我再寄給你。", ["Mandy"]),
    # Not in the given-name list, or written as an ordinary word: only the mixed model.
    ("Wei-Ting說好", ["Wei-Ting"]),
    ("請Yu-Chen確認一下報價", ["Yu-Chen"]),
    ("昨天Hsiao-Wen有來嗎", ["Hsiao-Wen"]),
    ("剛剛跟jason討論過了", ["jason"]),
    ("May說她五點會到", ["May"]),
    ("Yuki跟Kenji是日本同事", ["Yuki", "Kenji"]),
    ("Chia-Hao負責後端，Pei-Shan負責前端", ["Chia-Hao", "Pei-Shan"]),
]

MIXED_NO_NAMES = [
    "我用Python寫了一個script，跑在AWS上。",
    "iPhone跟MacBook都壞了。",
    "這個PR merge之後要重新deploy。",
    "今天的stand-up改到下午。",
    "我們用Slack跟Notion溝通，資料放Google Drive。",
    "請在May之前把Q3 report交出來。",
    "June跟May的報告",
    "這部分用React寫，後端是Django",
    "我們用Docker跟Kubernetes部署",
]

# Public figures in a public context are not personal data: the privacy filter leaves them
# readable in English (the Chinese model codes them anyway).
PUBLIC_FIGURES = [
    ("Our CEO Satya Nadella spoke with Tim Cook yesterday.", ["Satya Nadella", "Tim Cook"]),
    ("According to Professor Richard Feynman, nature cannot be fooled.", ["Richard Feynman"]),
    ("Apple hired Steve Jobs back in 1997.", ["Steve Jobs"]),
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
    return PIPELINE


def missed(pipe, cases):
    out = []
    for text, names in cases:
        result = pipe.obfuscate(text, Session(label="t")).text
        out += [n for n in names if n in result]
    return out


@pytest.mark.parametrize("lang", ["zh", "en", "mixed"])
def test_name_recall(pipe, lang):
    cases = {"zh": ZH, "en": EN, "mixed": MIXED}[lang]
    total = sum(len(names) for _, names in cases)
    misses = missed(pipe, cases)
    assert 1 - len(misses) / total >= MIN_RECALL[lang], misses


def test_public_figures_stay_readable(pipe):
    assert missed(pipe, PUBLIC_FIGURES) == [n for _, names in PUBLIC_FIGURES for n in names]


@pytest.mark.xfail(strict=True, reason="known limit: a very famous name is taken for the public "
                                        "figure even in a private context")
def test_private_person_with_a_very_famous_name(pipe):
    assert not missed(pipe, [("Please call Paris Hilton at 555-0142 about her claim #88213.",
                              ["Paris Hilton"])])


def test_chat_speakers(pipe):
    result = pipe.obfuscate(CHAT, Session(label="t")).text
    assert not any(n in result for n in ("王小明", "紀文品", "陳美玲")), result


def test_no_names_no_person_codes(pipe):
    for text in NO_NAMES + MIXED_NO_NAMES:
        spans = pipe.obfuscate(text, Session(label="t")).spans
        assert not [s.text for s in spans if s.label == "PERSON"], text

"""Speaker names in pasted chat logs ("張明：好的", "10:23\t張明\t好的", "[10:23] Emma: ok").

The model often misses a name standing alone at the start of a line. But when it does
recognise one speaker, the other line-start labels in the same position are very
likely people too.
"""

from __future__ import annotations

import re

from .detect import Span
from .mapping import COMPOUND_SURNAMES, PERSON

COMMON_SURNAMES = set(
    "陳林黃張李王吳劉蔡楊許鄭謝洪郭邱曾廖賴徐周葉蘇莊呂江何蕭羅高潘簡朱鍾彭游詹胡施沈余"
    "趙盧梁顏柯孫魏翁戴范宋方鄧杜傅侯曹薛丁卓阮馬董温溫唐藍石蔣古紀姚連馮歐程湯田康姜白"
    "汪鄒尤巫鐘黎涂龔嚴韓袁金童陸夏柳邵錢伍倪于譚駱熊任甘秦顧毛章史官萬俞雷粘饒闕凃崔孔"
    "包易武辛賈段岳常樊葛齊殷祝左牛聶申"
    "陈刘黄张吴赵孙杨郑谢许邓冯萧罗叶苏卢蒋钟韩严龚鲁钱汤陆顾邹闫贾"
)
# Line-start labels that name a role or a field, not a person.
NOT_SPEAKERS = {"Note", "Notes", "Subject", "From", "To", "Cc", "Re", "Date", "Time",
                "Customer", "Manager", "Admin", "System", "User", "Me", "Q", "A"}

_PREFIX = r"^[ \t]*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?[ \t]+)?"  # optional "10:23" / "[10:23]"
_LABEL = r"([㐀-鿿]{2,4}|[A-Z][a-z]+(?: [A-Z][a-z]+){0,2})"
SPEAKER_RE = re.compile(_PREFIX + _LABEL + r"(?:[ \t]*[:：]|\t)", re.MULTILINE)


def _looks_like_name(label: str) -> bool:
    if label[0].isascii():
        return label not in NOT_SPEAKERS
    return label[0] in COMMON_SURNAMES or label[:2] in COMPOUND_SURNAMES


def speaker_spans(text: str, persons: set[str]) -> list[Span]:
    """Line-start speaker labels, as PERSON spans, when at least one of them is already
    a known person (`persons`)."""
    labels = [(m.start(1), m.end(1), m.group(1)) for m in SPEAKER_RE.finditer(text)]
    if not any(label in persons for *_, label in labels):
        return []
    return [Span(s, e, PERSON, label) for s, e, label in labels
            if label in persons or _looks_like_name(label)]

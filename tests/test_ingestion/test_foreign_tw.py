"""law.moj.gov.tw bulk-record parsing. Records are trimmed from the live ChLaw/ChOrder JSON (2026-10-25)."""
import datetime

from app.ingestion.foreign import _zh_int, tw_enactment_date, tw_in_scope, tw_law_text

WASTE_DISPOSAL_ACT = {
    "LawName": "廢棄物清理法", "EngLawName": "Waste Disposal Act",
    "LawURL": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=O0050001",
    "LawCategory": "行政＞環境部＞資源循環目", "LawAbandonNote": "", "LawForeword": "",
    "LawHistories": "1.中華民國六十三年七月二十六日總統（63）台統（一）義字第 3300 號\r\n  令制定公布全文 28 條\r\n"
                    "2.中華民國六十九年四月九日總統（69）台統（一）義字第 1968 號令修",
    "LawArticles": [
        {"ArticleType": "C", "ArticleNo": "", "ArticleContent": "   第 一 章 總則"},
        {"ArticleType": "A", "ArticleNo": "第 1 條", "ArticleContent": "為有效清除、處理廢棄物，改善環境衛生，維護國民健康，特制定本法。"},
    ],
}


def test_chinese_numerals():
    assert [_zh_int(s) for s in ("六十三", "一百十四", "一百零二", "十二", "九", "26")] == [63, 114, 102, 12, 9, 26]


def test_enactment_is_the_first_roc_date_in_the_history():
    assert tw_enactment_date(WASTE_DISPOSAL_ACT["LawHistories"]) == datetime.date(1974, 7, 26)
    assert tw_enactment_date("1.中華民國一百十四年一月十七日環境部令訂定發布") == datetime.date(2025, 1, 17)
    assert tw_enactment_date("") is None


def test_text_keeps_chapter_headings_and_numbers_articles():
    text = tw_law_text(WASTE_DISPOSAL_ACT)
    assert text.splitlines() == ["第 一 章 總則", "第 1 條 為有效清除、處理廢棄物，改善環境衛生，維護國民健康，特制定本法。"]


def test_scope_filter():
    assert tw_in_scope(WASTE_DISPOSAL_ACT)
    other_ministry_reuse = {"LawName": "經濟部事業廢棄物再利用管理辦法", "LawCategory": "行政＞經濟部＞工業目", "LawAbandonNote": ""}
    assert tw_in_scope(other_ministry_reuse)
    fee_schedule = {**WASTE_DISPOSAL_ACT, "LawName": "公民營廢棄物清除處理機構申請許可案件收費標準"}
    assert not tw_in_scope(fee_schedule)
    repealed = {**WASTE_DISPOSAL_ACT, "LawAbandonNote": "廢"}
    assert not tw_in_scope(repealed)
    historic_building = {"LawName": "古蹟修復及再利用辦法", "LawCategory": "行政＞文化部＞文化資產目", "LawAbandonNote": ""}
    assert not tw_in_scope(historic_building)

"""law.go.kr DRF parsing. Fixtures are trimmed from the live DRF XML shape (checked 2026-10-25)."""
import datetime

from app.ingestion.foreign import _kr_norm, kr_parse_law, kr_parse_search

SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LawSearch><target>law</target><totalCnt>3</totalCnt>
<law id="1"><법령일련번호>253527</법령일련번호><현행연혁코드>현행</현행연혁코드>
<법령명한글><![CDATA[자원의 절약과 재활용촉진에 관한 법률]]></법령명한글><공포일자>20240110</공포일자></law>
<law id="2"><법령일련번호>253999</법령일련번호><현행연혁코드>현행</현행연혁코드>
<법령명한글><![CDATA[자원의 절약과 재활용촉진에 관한 법률 시행령]]></법령명한글><공포일자>20240305</공포일자></law>
<law id="3"><법령일련번호>100001</법령일련번호><현행연혁코드>연혁</현행연혁코드>
<법령명한글><![CDATA[자원의 절약과 재활용촉진에 관한 법률]]></법령명한글><공포일자>19921208</공포일자></law>
</LawSearch>"""

LAW_XML = """<?xml version="1.0" encoding="UTF-8"?>
<법령 법령키="0001"><기본정보><법령명_한글><![CDATA[전기ㆍ전자제품 및 자동차의 자원순환에 관한 법률]]></법령명_한글>
<공포일자>20070402</공포일자><제개정구분>제정</제개정구분></기본정보>
<조문><조문단위><조문번호>1</조문번호><조문내용><![CDATA[제1조(목적) 이 법은 전기ㆍ전자제품 및 자동차의 재활용을 촉진하여 자원순환체계를 구축함을 목적으로 한다. <개정 2013. 7. 16.>]]></조문내용></조문단위>
<조문단위><조문번호>12</조문번호><조문내용><![CDATA[제12조(제조업자의 회수ㆍ인계ㆍ재활용 의무)]]></조문내용>
<항><항내용><![CDATA[① 전기ㆍ전자제품 제조업자는 재활용의무량 이상을 회수하여야 한다.]]></항내용>
<호><호내용><![CDATA[1. 회수한 폐전기ㆍ전자제품을 재활용사업자에게 인계할 것]]></호내용></호></항></조문단위></조문>
<부칙><부칙단위><부칙내용><![CDATA[부칙 이 법은 2008년 1월 1일부터 시행한다.]]></부칙내용></부칙단위></부칙>
</법령>"""


def test_search_keeps_current_versions_only():
    hits = kr_parse_search(SEARCH_XML)
    assert [h["mst"] for h in hits] == ["253527", "253999"]
    assert hits[1]["title"] == "자원의 절약과 재활용촉진에 관한 법률 시행령"


def test_law_body_is_article_text_with_cdata_unwrapped():
    title, text, date = kr_parse_law(LAW_XML)
    assert title == "전기ㆍ전자제품 및 자동차의 자원순환에 관한 법률"
    assert text.startswith("제1조(목적)")
    assert "재활용의무량" in text and "인계할 것" in text and "2008년 1월 1일부터" in text
    assert "<개정" not in text and "CDATA" not in text
    assert date == datetime.date(2007, 4, 2)


def test_amended_version_is_not_dated_by_its_amendment():
    _, _, date = kr_parse_law(LAW_XML.replace("<제개정구분>제정", "<제개정구분>일부개정"))
    assert date is None


def test_seed_titles_match_across_middle_dot_variants():
    assert _kr_norm("전기·전자제품 및 자동차") == _kr_norm("전기ㆍ전자제품 및자동차")

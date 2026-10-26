"""ips.pravo.gov.ru search-result filtering. Records are trimmed from live search.json docs (2026-10-26)."""
import datetime

from app.ingestion.foreign import ru_adoption_date, ru_in_scope, ru_title

EPR_LIST = {
    "nd": "1000000000606291164", "state": "Действует без изменений", "name": "", "description":
    "Об утверждении перечней товаров, упаковки, отходы от использования которых подлежат утилизации",
    "adoption": "Постановление Правительства Российской Федерации от 29.12.2023 № 2414",
}
WASTE_LAW = {
    "nd": "1000000000102053807", "state": "Действует с изменениями", "name": "Об отходах производства и потребления",
    "description": "None", "adoption": "Федеральный закон от 24.06.1998 № 89-ФЗ",
}


def test_title_falls_back_to_description_for_decrees():
    assert ru_title(EPR_LIST).startswith("Об утверждении перечней товаров, упаковки")
    assert ru_title(WASTE_LAW) == "Об отходах производства и потребления"


def test_adoption_date():
    assert ru_adoption_date(EPR_LIST["adoption"]) == datetime.date(2023, 12, 29)
    assert ru_adoption_date(WASTE_LAW["adoption"]) == datetime.date(1998, 6, 24)
    assert ru_adoption_date("") is None


def test_scope_keeps_epr_core_and_drops_noise():
    assert ru_in_scope(EPR_LIST) and ru_in_scope(WASTE_LAW)
    amending = {**EPR_LIST, "description": "О внесении изменений в постановление об утилизации отходов"}
    marking = {**EPR_LIST, "description": "Об утверждении Правил маркировки упакованных в потребительскую упаковку товаров"}
    duma = {**WASTE_LAW, "adoption": "Постановление Совета Федерации от 10.06.1998 № 235-СФ"}
    repealed = {**WASTE_LAW, "state": "Утратил силу"}
    budget = {**WASTE_LAW, "name": "Об исполнении федерального бюджета за 2024 год (экологического сбора)"}
    for doc in (amending, marking, duma, repealed, budget):
        assert not ru_in_scope(doc), doc

"""Food-waste law seeds (packaging vs food-law split): the Planalto firewall guard and mirror seeds, the
Code de l'environnement seed articles resolved by number, and the seed rows for the other markets."""
import datetime

import httpx
import pytest

from app.config import settings
from app.ingestion import foreign
from app.ingestion.foreign import (
    BR_SEED_LAWS, DE_SEED_LAWS, FR_CODE_SEED_ARTICLES, FR_SEED_LAWS, IN_SEED_LAWS, MX_SEED_LAWS,
    PL_DISCOVERY_TERMS, BrazilPlanaltoClient, LegifranceCodeClient,
)

BLOCK_PAGE = ("<html><body><h1>Acesso Negado!</h1><p>Esta requisição foi bloqueada. Em caso de dúvida, "
              "envie o código 1234 para bloqueio.de.aplicacoes@presidencia.gov.br</p></body></html>")
LEGIN_PAGE = ("<html><header>Portal Câmara dos Deputados menu</header><main><h1>LEI Nº 15.224</h1>"
              "<p>Art. 1º Esta Lei institui a Política Nacional de Combate à Perda e ao Desperdício de "
              "Alimentos (PNCPDA), cria o Selo Doador de Alimentos.</p>"
              "<p>Art. 14. Poderão ser doados a bancos de alimentos os alimentos embalados.</p>"
              "<p>Este texto não substitui o original publicado no Diário Oficial.</p></main>"
              "<footer>Fale com a Câmara</footer></html>")


def _br_client(handler):
    client = BrazilPlanaltoClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.asyncio
async def test_planalto_firewall_page_is_never_stored():
    client = _br_client(lambda req: httpx.Response(200, html=BLOCK_PAGE))
    assert await client.fetch("_ato2023-2026/2025/decreto/D12688.htm", "Decree 12.688/2025") is None


@pytest.mark.asyncio
async def test_mirror_seed_reads_the_camara_copy_and_trims_the_site_chrome():
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(200, html=LEGIN_PAGE)

    law = await _br_client(handler).fetch("_ato2023-2026/2025/lei/L15224.htm", "Law 15.224/2025")
    assert seen and "camara.leg.br/legin" in seen[0]          # never asks Planalto
    assert law.full_text.startswith("Art. 1º")
    assert "Poderão ser doados" in law.full_text
    assert "Este texto não substitui" not in law.full_text and "Fale com" not in law.full_text
    assert law.source_url == seen[0]
    assert law.status_date == datetime.date(2025, 9, 30)
    assert law.foreign_id == "BR:planalto:_ato2023-2026/2025/lei/L15224.htm"


def _code_client(monkeypatch, calls):
    monkeypatch.setattr(settings, "legifrance_client_id", "id")
    monkeypatch.setattr(settings, "legifrance_client_secret", "secret")

    def handler(req: httpx.Request):
        calls.append(req)
        if req.url.host == "oauth.piste.gouv.fr":
            return httpx.Response(200, json={"access_token": "tok"})
        if req.url.path.endswith("/search"):
            body = req.read().decode()
            if '"NUM_ARTICLE"' in body:  # seed resolution by number
                num = "L541-15-7" if "L541-15-7" in body else "L541-21-1"
                return httpx.Response(200, json={"results": [{"sections": [
                    {"extracts": [{"num": num, "id": f"LEGIARTI-{num}"}]}]}]})
            return httpx.Response(200, json={"results": []})  # the REP term search finds nothing
        if req.url.path.endswith("/consult/getArticle"):
            return httpx.Response(200, json={"article": {
                "num": "L541-15-7", "etat": "VIGUEUR", "dateDebut": 1625097600000,
                "texte": "Les établissements de restauration commerciale mettent à la disposition de leurs "
                         "clients des contenants réutilisables ou recyclables permettant d'emporter."}})
        return httpx.Response(404)

    client = LegifranceCodeClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.asyncio
async def test_code_seed_articles_are_kept_outside_the_rep_prefix_and_labelled(monkeypatch):
    calls = []
    client = _code_client(monkeypatch, calls)
    found = dict(await client.discover())
    assert set(found) == {"cenv/L541-15-7", "cenv/L541-21-1"}
    assert "doggy bag" in found["cenv/L541-15-7"]
    law = await client.fetch("cenv/L541-15-7")
    assert law.title == ("Code de l'environnement, article L541-15-7 "
                         f"({FR_CODE_SEED_ARTICLES['L541-15-7'][0]})")
    assert "responsabilité élargie" not in law.title and "doggy bag" in law.english_label
    assert law.source_url.endswith("LEGIARTI-L541-15-7")
    assert law.status_date == datetime.date(2021, 7, 1)


def test_food_law_seed_rows_are_registered():
    assert any(s["path"].endswith("L15224.htm") and "camara.leg.br" in s["url"] for s in BR_SEED_LAWS)
    assert any(s["abbr"] == "LGAAS" and s["date"] == "2024-04-17" for s in MX_SEED_LAWS)
    assert "marnowaniu żywności" in PL_DISCOVERY_TERMS
    assert any(s["slug"] == "gewabfv_2017" for s in DE_SEED_LAWS)
    assert any(s["cid"] == "JORFTEXT000037547946" for s in FR_SEED_LAWS)
    swm = next(s for s in IN_SEED_LAWS if s["id"] == "swm-2026")
    assert swm["url"].startswith("https://static.pib.gov.in/") and swm["date"] == "2026-01-27"
    assert {"L541-15-7", "L541-21-1"} <= set(FR_CODE_SEED_ARTICLES)
    assert foreign.FOREIGN_CLIENTS["FR_CODE"] is LegifranceCodeClient

"""Brazil Senado adapter: the situation-code mapping, discovery's Senate-originated bill filter, the
classifier body, and the closed-process fallback (no current situation -> outcome from normaGerada)."""
import datetime

import httpx
import pytest

from app.config import settings
from app.ingestion.foreign import (
    BR_SENADO_TERMS, FOREIGN_CLIENTS, BrazilSenadoClient, br_senado_status,
)

SEARCH = [
    {"id": 8307137, "identificacao": "PL 2524/2022", "objetivo": "Iniciadora"},
    {"id": 1, "identificacao": "PL 1000/2024", "objetivo": "Revisora"},    # a Câmara bill under review
    {"id": 2, "identificacao": "REQ 108/2023", "objetivo": None},          # a request, not a bill
    {"id": 3, "identificacao": "PLS 93/2018", "objetivo": "Iniciadora"},
]

PL_2524 = {
    "id": 8307137, "codigoMateria": 154790, "identificacao": "PL 2524/2022", "sigla": "PL",
    "descricaoSigla": "Projeto de Lei", "tramitando": "Sim",
    "conteudo": {"ementa": "Estabelece regras relativas à economia circular do plástico."},
    "documento": {"dataApresentacao": "2022-09-27",
                  "indexacao": " ECONOMIA CIRCULAR ,  MATERIAL PLASTICO ,  RECICLAGEM "},
    "classificacoes": [{"descricaoHierarquia": "Meio Ambiente / Resíduos Sólidos"}],
    "autoriaIniciativa": [{"autor": "Jean-Paul Prates"}],
    "situacaoAtual": "PRONTA PARA A PAUTA NA COMISSÃO", "siglaSituacaoAtual": "PRONTPAUT",
    "dataSituacaoAtual": "2026-10-14", "deliberacao": {}, "normaGerada": {},
}

PLS_93 = {
    "id": 3, "codigoMateria": 999, "identificacao": "PLS 93/2018", "sigla": "PLS", "tramitando": "Não",
    "conteudo": {"ementa": "Altera a Lei nº 12.305, de 2010."}, "documento": {"dataApresentacao": "2018-03-01"},
    "situacaoAtual": None, "siglaSituacaoAtual": None, "dataSituacaoAtual": None,
    "deliberacao": {"data": "2022-12-21", "siglaTipo": "ARQUIVADO_FIM_LEGISLATURA"}, "normaGerada": {},
}


def _client(calls):
    def handler(req: httpx.Request):
        calls.append(req)
        if req.url.path.endswith("/processo"):
            return httpx.Response(200, json=SEARCH)
        if req.url.path.endswith("/processo/8307137"):
            return httpx.Response(200, json=PL_2524)
        if req.url.path.endswith("/processo/3"):
            return httpx.Response(200, json=PLS_93)
        return httpx.Response(404)

    client = BrazilSenadoClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def test_registered_live_and_tracked():
    assert FOREIGN_CLIENTS["BR_SENADO"] is BrazilSenadoClient
    assert "BR_SENADO" in settings.foreign_ingestion_regions
    assert BrazilSenadoClient.tracks_status
    assert BrazilSenadoClient().foreign_id_for("8307137") == "BR:senado:8307137"


def test_situation_codes_map_onto_the_canonical_statuses():
    assert br_senado_status("TNJR") == "enacted"
    assert br_senado_status("VTDA") == "vetoed"
    assert br_senado_status("RMSAN") == "passed"
    assert br_senado_status("RMCD") == "passed_chamber"     # sent to the Câmara
    assert br_senado_status("PRONTPAUT") == "in_committee"
    assert br_senado_status("ARQVD") == "failed"
    assert br_senado_status("AGDESP") == "introduced"       # awaiting dispatch: unlisted
    assert br_senado_status(None) == "introduced"


@pytest.mark.asyncio
async def test_discovery_keeps_only_senate_originated_bills():
    calls = []
    ids = [i for i, _ in await _client(calls).discover()]
    assert ids == ["8307137", "3"]
    assert len(calls) == len(BR_SENADO_TERMS)
    assert all("tramitouLegislaturaAtual=S" in str(c.url) for c in calls)


@pytest.mark.asyncio
async def test_fetch_builds_the_tracked_bill():
    law = await _client([]).fetch("8307137")
    assert law.title == "PL 2524/2022"
    assert law.status == "in_committee"
    assert law.status_date == datetime.date(2022, 9, 27)
    assert law.last_action_date == datetime.date(2026, 10, 14)
    assert law.source_url.endswith("/materia/154790")
    assert "Indexação: ECONOMIA CIRCULAR , MATERIAL PLASTICO , RECICLAGEM" in law.full_text
    assert "Meio Ambiente / Resíduos Sólidos" in law.full_text


@pytest.mark.asyncio
async def test_closed_process_without_a_situation_takes_its_outcome_from_the_deliberation():
    law = await _client([]).fetch("3")
    assert law.status == "failed"   # archived at the end of the legislature, no law generated
    assert law.last_action_date == datetime.date(2022, 12, 21)


@pytest.mark.asyncio
async def test_missing_ementa_or_unknown_id_is_skipped():
    assert await _client([]).fetch("404") is None

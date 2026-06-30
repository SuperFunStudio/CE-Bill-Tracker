"""Pluggable foreign national-law ingestion — the multi-country generalization of the EU spike.

EUR-Lex (app/ingestion/eurlex.py) proved the curated-enacted-law pattern: discover a relevant slice
of a national/supranational corpus, fetch each act's full text, upsert a region-tagged bill + bill_text,
and let the region-aware Haiku classifier judge relevance at the confidence floor (bypassing the
US-tuned keyword gate). This module factors that pattern into a reusable base so each new jurisdiction
is just a subclass that knows how to (a) discover candidate law ids and (b) fetch one law's text.

  ForeignSourceClient   — abstract async client: httpx lifecycle + `discover()` + `fetch()`.
  ForeignLaw            — normalized act (the cross-country analog of EurLexAct).
  sync_foreign()        — generic discover -> fetch -> upsert(bills+bill_texts) -> classify pipeline,
                          keyed on the generic `foreign_id` column, parameterized by the client's region.

First adapter: JapanEgovClient over the e-Gov 法令API (laws.e-gov.go.jp) — free, no key, full-text XML.
UK (legislation.gov.uk API) and South Korea (law.go.kr Open API) are the next intended subclasses.

Each act becomes a region=<XX>, state=<XX> bill keyed on foreign_id="<REGION>:<source>:<id>", with full
text in bill_texts. Driver: scripts/ingest_foreign.py. Not wired into the US IngestionCoordinator loop.
"""
from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
import structlog

log = structlog.get_logger()

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

_TAG_RE = re.compile(r"<[^>]+>")
# Collapse runs of horizontal whitespace, incl. the JP full-width space (　) and the non-breaking
# space (\xa0) that pervades European legal XML/HTML — otherwise tokens glue together oddly.
_WS_RE = re.compile(r"[ \t\xa0  　]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")
# Some sources embed binary attachments (PDFs/diagrams/forms) as base64 inside the document — e.g.
# Japan's e-Gov XML inlines 添付ファイル as base64, bloating one ELV ordinance to 1.75M chars of binary
# and blowing past Postgres's tsvector size limit on bill_texts. Legal prose never has 300-char unbroken
# base64 runs, so drop them; the actual statutory text is preserved.
_B64_BLOB_RE = re.compile(r"[A-Za-z0-9+/]{300,}={0,2}")


def _strip_tags(raw: str) -> str:
    """Strip XML/HTML tags to plain text and collapse whitespace (incl. the JP full-width space)."""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)  # decode &amp; &#211; &nbsp; etc. (tags already removed first)
    text = _B64_BLOB_RE.sub(" ", text)  # drop embedded base64 attachment blobs
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANKLINES_RE.sub("\n\n", text).strip()


# Postgres errors if a single string fed to to_tsvector exceeds 1048575 bytes. Large consolidated
# acts (e.g. Austria's Abfallwirtschaftsgesetz ~1.04M chars) can cross it once UTF-8 multibyte chars
# are counted, so cap stored full text below the limit (with margin) — the lost tail is statute detail
# the Haiku excerpt never reaches anyway; full-text search just won't index the very end of giant acts.
_TSVECTOR_BYTE_LIMIT = 1_000_000


def cap_for_tsvector(text: str) -> str:
    """Truncate text so its UTF-8 encoding stays under the Postgres tsvector byte limit."""
    if len(text.encode("utf-8")) <= _TSVECTOR_BYTE_LIMIT:
        return text
    # Trim by characters until under the byte budget (cheap: most text is near 1 byte/char).
    cut = _TSVECTOR_BYTE_LIMIT
    while len(text[:cut].encode("utf-8")) > _TSVECTOR_BYTE_LIMIT:
        cut = int(cut * 0.95)
    return text[:cut]


@dataclass
class ForeignLaw:
    """A normalized enacted national law — the cross-country analog of EurLexAct."""

    source_id: str          # the source's native law id (e.g. e-Gov LawId "424AC0000000057")
    region: str             # ISO-ish region code: "JP", "GB", "KR", …
    title: str              # native-language official title
    full_text: str          # cleaned plain text of the law body (stored in bill_texts)
    source_url: str         # human-facing page on the official source
    english_label: str = "" # optional curated English name (seed list) — strong classifier signal
    status: str = "enacted" # national law in force
    source: str = "foreign" # source-system tag, e.g. "egov"; namespaces the foreign_id

    @property
    def foreign_id(self) -> str:
        # Namespaced so ids never collide across regions/sources sharing one unique column.
        return f"{self.region}:{self.source}:{self.source_id}"

    @property
    def bill_number(self) -> str:
        return self.source_id

    @property
    def summary(self) -> str:
        """Description fed to the classifier. Lead with the English label (if curated) + native title —
        that carries the most signal — then a slice of the body."""
        head = " — ".join(p for p in (self.english_label, self.title) if p)
        return (head + "\n\n" + self.full_text[:1500]).strip()


class ForeignSourceClient(ABC):
    """Async base for a national-law source. Subclass + implement `discover()` and `fetch()`.

    Use as an async context manager (shares one httpx client across discover/fetch calls).
    """

    region: str = ""        # subclass sets, e.g. "JP"
    source: str = "foreign" # subclass sets, e.g. "egov"

    def __init__(self, timeout: float = 45.0):
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True, headers=_BROWSER_HEADERS
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def http(self) -> httpx.AsyncClient:
        assert self._client is not None, "use the client as an async context manager"
        return self._client

    @abstractmethod
    async def discover(self) -> list[tuple[str, str]]:
        """Return candidate (source_id, english_label) pairs for the EPR/circular-economy slice.

        Best-effort + over-inclusive by design (the Haiku confidence floor judges true relevance,
        exactly like the EUR-Lex SPARQL discovery). english_label is "" for keyword-discovered laws and
        a curated name for seed laws. A source hiccup must not raise — return what you have (or []).
        """

    @abstractmethod
    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        """Fetch one law's title + full text. Return None if the body can't be retrieved."""


# --------------------------------------------------------------------------------------------------
# Japan — e-Gov 法令API (https://laws.e-gov.go.jp/api/). Free, no key, full-text XML.
#   catalog:  GET /api/1/lawlists/1            -> every current law (LawId / LawName / LawNo)
#   law text: GET /api/1/lawdata/{LawId}       -> <LawFullText> with <LawTitle> + article text
# --------------------------------------------------------------------------------------------------

JP_API_BASE = "https://laws.e-gov.go.jp/api/1"
# Human-facing page for a law (LawId resolves directly on the e-Gov site).
JP_PAGE = "https://laws.e-gov.go.jp/law/{law_id}"

# Discovery keywords over the catalog's LawName — the JP analog of the US epr_keywords / EU EuroVoc
# pre-filter. Targets the resource-circulation / EPR cluster; broad terms (廃棄物=waste, 資源=resource)
# are intentionally included and the classifier sorts the noise (water/fishery/space "resources" etc.).
JP_DISCOVERY_KEYWORDS = [
    "リサイクル",       # recycling (katakana)
    "再資源化",         # re-resourcing / recycling
    "再生利用",         # recycled use
    "再生資源",         # recycled resources
    "資源循環",         # resource circulation
    "再商品化",         # re-commercialization (EPR take-back term)
    "容器包装",         # containers & packaging
    "使用済",           # used / end-of-life
    "資源の有効",       # effective use of resources
    "循環型社会",       # sound material-cycle society
]

# Curated canonical EPR / circular-economy acts — matched by exact LawName against the catalog so we
# carry an English label (strong classifier + UI signal) and guarantee inclusion regardless of keyword
# drift. The classifier still assigns instrument_type / material_categories itself.
JP_SEED_LAWS: list[dict] = [
    {"name": "使用済小型電子機器等の再資源化の促進に関する法律",
     "en": "Small Home Appliance Recycling Act (electronics)", "material": "electronics"},
    {"name": "特定家庭用機器再商品化法",
     "en": "Home Appliance Recycling Act (AC/TV/fridge/washer)", "material": "electronics"},
    {"name": "資源の有効な利用の促進に関する法律",
     "en": "Act on Promotion of Effective Utilization of Resources", "material": "multi"},
    {"name": "容器包装に係る分別収集及び再商品化の促進等に関する法律",
     "en": "Containers and Packaging Recycling Act", "material": "packaging"},
    {"name": "プラスチックに係る資源循環の促進等に関する法律",
     "en": "Plastic Resource Circulation Act", "material": "plastics"},
    {"name": "使用済自動車の再資源化等に関する法律",
     "en": "End-of-Life Vehicle Recycling Act", "material": "vehicles"},
    {"name": "食品循環資源の再生利用等の促進に関する法律",
     "en": "Food Recycling Act", "material": "organics"},
    {"name": "建設工事に係る資材の再資源化等に関する法律",
     "en": "Construction Material Recycling Act", "material": "construction"},
    {"name": "太陽電池廃棄物の再資源化等の推進に関する法律",
     "en": "Solar Panel Waste Recycling Act", "material": "solar_panels"},
    {"name": "資源循環の促進のための再資源化事業等の高度化に関する法律",
     "en": "Resource Circulation Promotion Act (2024)", "material": "multi"},
    {"name": "廃棄物の処理及び清掃に関する法律",
     "en": "Waste Management and Public Cleansing Act", "material": "waste"},
]

# e-Gov LawId = era(1) + year(2) + type(2) + number. The type code at [3:5] is "AC" for a primary Act
# (法律), "CO" for a Cabinet Order (政令), "M5"/"M6"… for a Ministerial Ordinance (省令). We track only
# primary Acts — the JP analog of EUR-Lex ACT_TYPES="RLD" (top-level instruments, not the hundreds of
# implementing ordinances, which are a future obligations-layer detail, not statute-level tracking).
def _jp_is_act(law_id: str) -> bool:
    return len(law_id) >= 5 and law_id[3:5] == "AC"


def _jp_is_ordinance(law_id: str) -> bool:
    """Ministerial Ordinance (省令, type 'M…') or Cabinet Order (政令, 'CO') — the implementing
    obligations layer below the Acts (the JP analog of France's codified articles / EU implementing acts)."""
    return len(law_id) >= 5 and (law_id[3] == "M" or law_id[3:5] == "CO")


# Drop obvious off-topic matches that share an EPR keyword: nuclear spent-fuel / reprocessing (使用済燃料,
# 原子力, 再処理, 廃炉) ride in on 使用済 ("used"); water/marine/space/mineral/genetic "resources" ride in
# on 資源. The seed list pins the statutes we always want regardless.
_JP_NAME_EXCLUDE = re.compile(
    r"(水産資源|海洋|宇宙資源|鉱物資源|遺伝資源|放射性|原子力|使用済燃料|再処理|廃炉)"
)
# Extra exclude for the ordinance layer: drop the purely procedural ordinances (inspection-officer ID
# card forms, report/registration form layouts) that match EPR keywords but carry no producer
# obligation — keep the product-specific 判断の基準 / 自主回収・再資源化 ordinances.
_JP_ORD_EXCLUDE = re.compile(r"(様式|身分を示す証明書|立入検査|証明書)")
_JP_LAWLIST_ITEM = re.compile(
    r"<LawId>([^<]+)</LawId>\s*<LawName>([^<]+)</LawName>", re.S
)
_JP_TITLE_RE = re.compile(r"<LawTitle\b[^>]*>([^<]+)</LawTitle>")


class JapanEgovClient(ForeignSourceClient):
    """e-Gov 法令API adapter. Enacted Japanese law, full-text XML, no API key required."""

    region = "JP"
    source = "egov"

    async def _catalog(self) -> list[tuple[str, str]]:
        """Return (LawId, LawName) for every current law (lawlists category 1)."""
        resp = await self.http.get(f"{JP_API_BASE}/lawlists/1")
        resp.raise_for_status()
        return _JP_LAWLIST_ITEM.findall(resp.text)

    async def discover(self) -> list[tuple[str, str]]:
        try:
            catalog = await self._catalog()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("jp_catalog_failed", error=str(e))
            return []

        # Resolve seed names -> ids from the catalog (carry English labels), then add keyword hits.
        by_name = {name: law_id for law_id, name in catalog}
        out: dict[str, str] = {}  # law_id -> english_label ("" for keyword-only)
        for seed in JP_SEED_LAWS:
            law_id = by_name.get(seed["name"])
            if law_id:
                out[law_id] = seed["en"]
            else:
                log.warning("jp_seed_not_in_catalog", name=seed["name"])

        for law_id, name in catalog:
            if law_id in out:
                continue
            if not _jp_is_act(law_id):  # primary Acts (法律) only — skip ordinances/cabinet orders
                continue
            if _JP_NAME_EXCLUDE.search(name):
                continue
            if any(kw in name for kw in JP_DISCOVERY_KEYWORDS):
                out.setdefault(law_id, "")

        log.info("jp_discovered", total=len(out), seeded=sum(1 for v in out.values() if v))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            resp = await self.http.get(f"{JP_API_BASE}/lawdata/{source_id}")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("jp_fetch_failed", law_id=source_id, error=str(e))
            return None

        raw = resp.text
        # The API wraps the result; Code != 0 means the law id wasn't served.
        if "<Code>0</Code>" not in raw:
            log.warning("jp_fetch_nonzero", law_id=source_id)
            return None

        title_m = _JP_TITLE_RE.search(raw)
        title = title_m.group(1).strip() if title_m else (english_label or source_id)
        # Body text: strip XML from the <LawBody> region (fall back to whole payload).
        body_start = raw.find("<LawBody")
        body = raw[body_start:] if body_start != -1 else raw
        full_text = _strip_tags(body)
        if len(full_text) < 100:
            log.warning("jp_thin_text", law_id=source_id, chars=len(full_text))
            return None

        return ForeignLaw(
            source_id=source_id,
            region=self.region,
            source=self.source,
            title=title,
            full_text=full_text,
            source_url=JP_PAGE.format(law_id=source_id),
            english_label=english_label,
        )


class JapanEgovOrdinanceClient(JapanEgovClient):
    """The Japanese implementing-obligations layer: ministerial ordinances (省令) + cabinet orders (政令)
    that carry the product-specific take-back / recycling criteria (mobile batteries, PCs, TVs, washers,
    …). Region="JP", source="egov" (composes with the Acts; foreign_id keyed on the unique LawId).
    Inherits _catalog()/fetch(); only discovery differs (ordinance types + the procedural-noise filter)."""

    async def discover(self) -> list[tuple[str, str]]:
        try:
            catalog = await self._catalog()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("jp_catalog_failed", error=str(e))
            return []
        out: dict[str, str] = {}
        for law_id, name in catalog:
            if not _jp_is_ordinance(law_id):
                continue
            if _JP_NAME_EXCLUDE.search(name) or _JP_ORD_EXCLUDE.search(name):
                continue
            if any(kw in name for kw in JP_DISCOVERY_KEYWORDS):
                out.setdefault(law_id, "")
        log.info("jp_ord_discovered", total=len(out))
        return list(out.items())


# --------------------------------------------------------------------------------------------------
# France — Légifrance API via PISTE (https://api.piste.gouv.fr/dila/legifrance/lf-engine-app).
# Unlike Japan's open API, Légifrance requires OAuth2 client-credentials (free PISTE registration);
# the public HTML is a 403-walled JS SPA, so the API is the only viable path. We track France's
# national circular-economy statutes that go BEYOND the EU directives (the AGEC law's repairability /
# durability index, anti-planned-obsolescence, French REP filières) — region="FR", distinct from the
# EU acts (region="EU"). Seed-first like EUR-Lex; /search-based discovery is the next enhancement.
# --------------------------------------------------------------------------------------------------

LF_OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
LF_API_BASE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
# Human-facing page for a JORF text (loi/décret published in the Journal Officiel).
LF_PAGE = "https://www.legifrance.gouv.fr/jorf/id/{cid}"

# Curated French national circular-economy texts, keyed by JORFTEXT cid (the consult/jorf input). These
# are the statutes/décrets layered ON TOP of EU law — AGEC is the flagship (repairability index →
# durability index, REP scheme expansion, anti-obsolescence). The seed guarantees the marquee texts;
# discover() (the /search path below) finds the rest of the REP-filière décrets dynamically. All cids
# below were verified live via the Légifrance /search API. Bad/expired cids simply skip on fetch.
FR_SEED_LAWS: list[dict] = [
    {"cid": "JORFTEXT000041553759",
     "en": "Loi AGEC (anti-waste & circular economy, 2020-105) — repairability/durability index"},
    {"cid": "JORFTEXT000042837821",
     "en": "Décret 2020-1757 — indice de réparabilité (repairability index)"},
    {"cid": "JORFTEXT000042575740",
     "en": "Décret 2020-1455 — réforme de la responsabilité élargie du producteur (REP reform)"},
    {"cid": "JORFTEXT000047483124",
     "en": "Loi 2023-305 — fusion des filières REP (REP scheme consolidation)"},
    {"cid": "JORFTEXT000050749111",
     "en": "Décret 2024-1166 — institution d'une filière REP"},
]

# Circular-economy / EPR search phrases for /search discovery — the FR analog of EUR-Lex's EuroVoc
# concepts. typeRecherche TOUS_LES_MOTS_DANS_UN_CHAMP (all words present in the field = AND) keeps
# precision high (~15 hits/phrase vs ~450 for any-word); champ TITLE narrows to texts whose TITLE is
# about the topic (vs full-text mentions). Over-discovers; Haiku judges relevance at the confidence
# floor (curated-source path). (phrase, typeChamp).
FR_DISCOVERY_TERMS: list[tuple[str, str]] = [
    ("économie circulaire", "TITLE"),
    ("responsabilité élargie", "TITLE"),     # REP filières
    ("lutte contre le gaspillage", "TITLE"),
    ("réemploi", "TITLE"),
    ("recyclage", "TITLE"),
    ("déchets", "TITLE"),                     # waste (broad; Haiku judges)
    ("valorisation", "TITLE"),               # recovery
    ("consigne", "TITLE"),                    # deposit-return
    ("obsolescence", "TITLE"),
    ("indice de réparabilité", "ALL"),
    ("indice de durabilité", "ALL"),
    ("pièces détachées", "ALL"),             # spare parts / right-to-repair
]
LF_LODA_FOND = "LODA_DATE"          # Lois/Ordonnances/Décrets/Arrêtés corpus
LF_SEARCH_NATURES = ["LOI", "DECRET"]   # statute + implementing-decree level (skip the many arrêtés)
LF_SEARCH_PAGESIZE = 50

# Article/section text in the consult/jorf response lives under these keys (HTML content). We collect
# them recursively rather than hard-coding the nesting, so the parser survives schema drift.
_LF_TEXT_KEYS = ("content", "texte", "texteHtml")


def _lf_collect_text(node, out: list[str]) -> None:
    """Recursively gather article/section text from a Légifrance consult response (any nesting)."""
    if isinstance(node, dict):
        num = node.get("num")
        for key in _LF_TEXT_KEYS:
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                out.append((f"Article {num}\n" if num else "") + _strip_tags(val))
        for v in node.values():
            if isinstance(v, (dict, list)):
                _lf_collect_text(v, out)
    elif isinstance(node, list):
        for item in node:
            _lf_collect_text(item, out)


class LegifranceClient(ForeignSourceClient):
    """Légifrance/PISTE adapter. France national law, OAuth2 client-credentials (free PISTE account)."""

    region = "FR"
    source = "legifrance"

    def __init__(self, timeout: float = 45.0):
        super().__init__(timeout)
        self._token: str | None = None

    async def _ensure_token(self) -> str | None:
        """Fetch (and cache) a PISTE bearer token. Returns None if credentials aren't configured."""
        from app.config import settings

        if self._token:
            return self._token
        cid, secret = settings.legifrance_client_id, settings.legifrance_client_secret
        if not (cid and secret):
            log.warning("legifrance_no_credentials")  # FR ingest disabled until creds are set
            return None
        try:
            resp = await self.http.post(
                LF_OAUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": cid,
                    "client_secret": secret,
                    "scope": "openid",
                },
            )
            resp.raise_for_status()
            self._token = resp.json().get("access_token")
        except (httpx.HTTPError, ValueError) as e:
            log.warning("legifrance_token_failed", error=str(e))
            return None
        return self._token

    async def _search(self, phrase: str, champ: str) -> list[str]:
        """Run one /search query, return the JORFTEXT cids of LOI/DECRET hits (consult/jorf-compatible)."""
        from datetime import datetime, timezone

        token = await self._ensure_token()
        if not token:
            return []
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        body = {
            "fond": LF_LODA_FOND,
            "recherche": {
                "champs": [{
                    "typeChamp": champ,
                    "criteres": [{"typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP", "valeur": phrase,
                                  "operateur": "ET"}],
                    "operateur": "ET",
                }],
                "filtres": [
                    {"facette": "NATURE", "valeurs": LF_SEARCH_NATURES},
                    {"facette": "DATE_VERSION", "singleDate": now_ms},
                ],
                "pageNumber": 1,
                "pageSize": LF_SEARCH_PAGESIZE,
                "operateur": "ET",
                "sort": "PERTINENCE",
                "typePagination": "DEFAUT",
            },
        }
        try:
            resp = await self.http.post(
                f"{LF_API_BASE}/search", json=body,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("legifrance_search_failed", phrase=phrase, error=str(e))
            return []
        cids: list[str] = []
        for res in data.get("results") or []:
            for t in res.get("titles") or []:
                cid = t.get("cid")
                if cid and cid.startswith("JORFTEXT"):
                    cids.append(cid)
        return cids

    async def discover(self) -> list[tuple[str, str]]:
        """Seed (curated, English-labelled) UNION /search discovery across the CE phrase set.
        Mirrors EUR-Lex (SEED_ACTS ∪ SPARQL). Returns (cid, english_label) — label is "" for
        search-discovered texts; Haiku judges their relevance at the confidence floor."""
        out: dict[str, str] = {s["cid"]: s["en"] for s in FR_SEED_LAWS}
        for phrase, champ in FR_DISCOVERY_TERMS:
            for cid in await self._search(phrase, champ):
                out.setdefault(cid, "")
        log.info("fr_discovered", total=len(out), seeded=sum(1 for v in out.values() if v))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        token = await self._ensure_token()
        if not token:
            return None
        try:
            resp = await self.http.post(
                f"{LF_API_BASE}/consult/jorf",
                json={"textCid": source_id},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("legifrance_fetch_failed", cid=source_id, error=str(e))
            return None

        title = (data.get("title") or "").strip() or english_label or source_id
        parts: list[str] = []
        _lf_collect_text(data, parts)
        full_text = "\n\n".join(parts).strip()
        if len(full_text) < 100:
            log.warning("legifrance_thin_text", cid=source_id, chars=len(full_text))
            return None

        return ForeignLaw(
            source_id=source_id,
            region=self.region,
            source=self.source,
            title=title,
            full_text=full_text,
            source_url=LF_PAGE.format(cid=source_id),
            english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# United Kingdom — legislation.gov.uk API (open, no key, crawling explicitly permitted; 3000 req/5min).
# RESTful URI scheme: append /data.feed (Atom search results) or /data.xml (CLML full text) to any
# legislation URI. We track UK-ORIGIN law only (ukpga = Public General Acts, uksi = Statutory
# Instruments) and deliberately exclude `eur` (retained/assimilated EU law) — that's already covered by
# EUR-Lex. Region="UK" (matches REGION_LABELS). Seed ∪ title-search discovery, mirroring FR.
# --------------------------------------------------------------------------------------------------

UK_BASE = "https://www.legislation.gov.uk"
# UK-origin primary law + statutory instruments, INCLUDING the devolved nations (Scotland's Deposit
# Return Scheme & Circular Economy (Scotland) Act, Welsh packaging/waste law, NI). Excludes `eur`
# (retained EU law — covered by EUR-Lex). asp/asc/anaw/nia = devolved Acts; ssi/wsi/nisr = devolved SIs.
UK_ALLOWED_TYPES = ("ukpga", "uksi", "asp", "ssi", "asc", "anaw", "wsi", "nia", "nisr")
UK_TYPE_FILTER = "+".join(UK_ALLOWED_TYPES)
UK_MAX_PAGES = 3  # Atom feed returns 20/page; walk a few pages so high-volume terms aren't truncated.

# Seed: marquee UK circular-economy instruments by {type}/{year}/{number} path (verified live).
UK_SEED_LAWS: list[dict] = [
    {"path": "ukpga/2021/30", "en": "Environment Act 2021 (EPR/DRS/packaging framework)"},
    {"path": "uksi/2024/1332", "en": "Producer Responsibility Obligations (Packaging & Packaging Waste) Regs 2024"},
    {"path": "uksi/2013/3113", "en": "Waste Electrical and Electronic Equipment (WEEE) Regs 2013"},
    {"path": "uksi/2009/890", "en": "Waste Batteries and Accumulators Regs 2009"},
    {"path": "uksi/2003/2635", "en": "End-of-Life Vehicles Regs 2003"},
]

# Title-search phrases (precise, title-scoped) — the UK analog of FR_DISCOVERY_TERMS / EuroVoc.
UK_DISCOVERY_TERMS = [
    "producer responsibility",
    "extended producer responsibility",
    "circular economy",
    "waste electrical and electronic",
    "packaging waste",
    "packaging and packaging waste",
    "waste batteries",
    "batteries and accumulators",
    "end-of-life vehicles",
    "single use plastic",
    "deposit and return scheme",
    "deposit return scheme",
    "recycling",
    "waste and resources",
]

_UK_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
_UK_ID_RE = re.compile(r"<id>https?://www\.legislation\.gov\.uk/id/([a-z]+/\d+/\d+)</id>")
_UK_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_UK_DCTITLE_RE = re.compile(r"<dc:title>(.*?)</dc:title>", re.S)


class UKLegislationClient(ForeignSourceClient):
    """legislation.gov.uk adapter. UK enacted law/SIs, open API, CLML full-text XML, no key."""

    region = "UK"
    source = "leggov"

    async def _search_titles(self, phrase: str) -> list[tuple[str, str]]:
        """Title-search one phrase over UK_ALLOWED_TYPES (paginated); return (path, title) for
        non-revoked hits."""
        from urllib.parse import quote

        out: list[tuple[str, str]] = []
        for page in range(1, UK_MAX_PAGES + 1):
            url = f"{UK_BASE}/{UK_TYPE_FILTER}/data.feed?title={quote(phrase)}&page={page}"
            try:
                resp = await self.http.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("uk_search_failed", phrase=phrase, page=page, error=str(e))
                break
            entries = _UK_ENTRY_RE.findall(resp.text)
            if not entries:
                break  # no more results
            for entry in entries:
                m = _UK_ID_RE.search(entry)
                if not m:
                    continue
                path = m.group(1)
                if path.split("/")[0] not in UK_ALLOWED_TYPES:
                    continue
                tm = _UK_TITLE_RE.search(entry)
                title = _strip_tags(tm.group(1)) if tm else ""
                if "(revoked)" in title.lower():  # skip repealed instruments
                    continue
                out.append((path, title))
            if len(entries) < 20:
                break  # last page (feed page size is 20)
        return out

    async def discover(self) -> list[tuple[str, str]]:
        """Seed (English-labelled) ∪ title-search discovery. Returns (path, english_label); label is
        "" for search-discovered laws (Haiku judges relevance at the confidence floor)."""
        out: dict[str, str] = {s["path"]: s["en"] for s in UK_SEED_LAWS}
        for phrase in UK_DISCOVERY_TERMS:
            for path, _title in await self._search_titles(phrase):
                out.setdefault(path, "")
        log.info("uk_discovered", total=len(out), seeded=sum(1 for v in out.values() if v))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            resp = await self.http.get(f"{UK_BASE}/{source_id}/data.xml")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("uk_fetch_failed", path=source_id, error=str(e))
            return None

        raw = resp.text
        tm = _UK_DCTITLE_RE.search(raw)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        # Strip from the <Body> onward (skip the heavy CLML metadata header); fall back to whole doc.
        body_start = raw.find("<Body")
        full_text = _strip_tags(raw[body_start:] if body_start != -1 else raw)
        if len(full_text) < 100:
            log.warning("uk_thin_text", path=source_id, chars=len(full_text))
            return None

        return ForeignLaw(
            source_id=source_id,
            region=self.region,
            source=self.source,
            title=title,
            full_text=full_text,
            source_url=f"{UK_BASE}/{source_id}",
            english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# France — codified layer. The REP filières' substance lives in the Code de l'environnement (articles
# L541-10 et seq.), NOT just the standalone décrets the LegifranceClient above captures. This is the
# legislative core a French producer's obligations rest on. Same PISTE API/auth; different consult path
# (/search over the CODE_DATE fond → /consult/getArticle per article). Region="FR" (composes with the
# décrets), source="legifrance-code" (separate foreign_id namespace).
# --------------------------------------------------------------------------------------------------

CENV_NAME = "Code de l'environnement"
# Search phrases (within the Code de l'environnement) that surface the REP / circular-economy cluster.
FR_CODE_TERMS = ["responsabilité élargie producteur", "éco-organisme", "économie circulaire"]
# Article-number prefixes to keep — L541-10* is the REP filière core ("et seq."). Broaden later to the
# rest of the L541 chapter (objectives, prevention, consumer info/labeling) if desired.
FR_CODE_PREFIXES = ("L541-10",)
FR_CODE_PAGESIZE = 50
FR_CODE_MAX_PAGES = 6


def _walk_extracts(node, out: dict[str, str]) -> None:
    """Recursively collect {article_number: LEGIARTI} from a CODE /search result (nested sections)."""
    if isinstance(node, dict):
        for a in (node.get("extracts") or node.get("articles") or []):
            num = a.get("title") or a.get("num")
            aid = a.get("id") or a.get("cid")
            if num and aid:
                out[num] = aid
        for s in (node.get("sections") or []):
            _walk_extracts(s, out)
    elif isinstance(node, list):
        for x in node:
            _walk_extracts(x, out)


class LegifranceCodeClient(LegifranceClient):
    """Légifrance code-article adapter (Code de l'environnement REP articles). Inherits PISTE OAuth."""

    region = "FR"
    source = "legifrance-code"

    async def _search_code(self, term: str, page: int) -> dict:
        from datetime import datetime, timezone

        token = await self._ensure_token()
        if not token:
            return {}
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        body = {
            "fond": "CODE_DATE",
            "recherche": {
                "champs": [{"typeChamp": "ALL", "criteres": [
                    {"typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP", "valeur": term, "operateur": "ET"}],
                    "operateur": "ET"}],
                "filtres": [{"facette": "NOM_CODE", "valeurs": [CENV_NAME]},
                            {"facette": "DATE_VERSION", "singleDate": now_ms}],
                "pageNumber": page, "pageSize": FR_CODE_PAGESIZE, "operateur": "ET",
                "sort": "PERTINENCE", "typePagination": "DEFAUT",
            },
        }
        try:
            r = await self.http.post(
                f"{LF_API_BASE}/search", json=body,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("fr_code_search_failed", term=term, page=page, error=str(e))
            return {}

    async def discover(self) -> list[tuple[str, str]]:
        self._artid: dict[str, str] = {}  # source_id -> LEGIARTI (for fetch)
        nums: dict[str, str] = {}          # article number -> LEGIARTI
        for term in FR_CODE_TERMS:
            for page in range(1, FR_CODE_MAX_PAGES + 1):
                data = await self._search_code(term, page)
                if not (data.get("results") or []):
                    break
                before = len(nums)
                for res in data["results"]:
                    _walk_extracts(res, nums)
                if len(nums) == before and page > 1:
                    break  # no new articles on this page — extracts exhausted
        out: dict[str, str] = {}
        for num, aid in nums.items():
            if any(num.startswith(p) for p in FR_CODE_PREFIXES):
                sid = f"cenv/{num}"
                self._artid[sid] = aid
                out[sid] = ""
        log.info("fr_code_discovered", kept=len(out), scanned=len(nums))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        aid = getattr(self, "_artid", {}).get(source_id)
        if not aid:
            log.warning("fr_code_no_artid", source_id=source_id)
            return None
        token = await self._ensure_token()
        if not token:
            return None
        try:
            r = await self.http.post(
                f"{LF_API_BASE}/consult/getArticle", json={"id": aid},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            r.raise_for_status()
            article = (r.json() or {}).get("article") or {}
        except (httpx.HTTPError, ValueError) as e:
            log.warning("fr_code_fetch_failed", source_id=source_id, error=str(e))
            return None
        if article.get("etat") not in (None, "VIGUEUR"):  # in-force articles only
            return None
        text = _strip_tags(article.get("texteHtml") or article.get("texte") or "")
        if len(text) < 50:
            log.warning("fr_code_thin", source_id=source_id, chars=len(text))
            return None
        num = article.get("num") or source_id
        return ForeignLaw(
            source_id=source_id,
            region=self.region,
            source=self.source,
            title=f"Code de l'environnement, article {num} (responsabilité élargie du producteur)",
            full_text=text,
            source_url=f"https://www.legifrance.gouv.fr/codes/article_lc/{aid}",
            # Consistent English EPR framing so Haiku has signal even on short codified articles.
            english_label="France Code de l'environnement — Extended Producer Responsibility (REP) provision",
        )


# --------------------------------------------------------------------------------------------------
# Germany — gesetze-im-internet.de (Bundesamt für Justiz / juris). Free, no key. A single TOC sitemap
# lists every federal law; each law's full text is a per-law XML inside a .zip (gii-norm DTD). Same
# curated-enacted-law pattern as JP/UK — the wrinkle is the ZIP-per-law fetch.
#   catalog:  GET /gii-toc.xml          -> <item><title>..</title><link>../{slug}/xml.zip</link></item>
#   law text: GET /{slug}/xml.zip       -> one <dokumente> XML (norms = the §§ articles)
# --------------------------------------------------------------------------------------------------

DE_BASE = "https://www.gesetze-im-internet.de"
DE_TOC = f"{DE_BASE}/gii-toc.xml"
DE_PAGE = DE_BASE + "/{slug}/"

# Marquee German EPR / circular-economy statutes, pinned by slug with an English label (guaranteed
# inclusion + strong classifier/UI signal), exactly like the JP/UK seed lists.
DE_SEED_LAWS: list[dict] = [
    {"slug": "verpackg", "en": "Packaging Act (VerpackG — EPR for packaging)"},
    {"slug": "elektrog_2015", "en": "Electrical and Electronic Equipment Act (ElektroG — WEEE)"},
    {"slug": "battg", "en": "Batteries Act (BattG)"},
    {"slug": "battdg", "en": "Batteries Implementation Act (BattDG — EU 2023/1542)"},
    {"slug": "krwg", "en": "Circular Economy Act (KrWG — Closed Substance Cycle Waste Management)"},
    {"slug": "altautov", "en": "End-of-Life Vehicles Ordinance (AltfahrzeugV)"},
    {"slug": "ewkfondsg", "en": "Single-Use Plastics Fund Act (EWKFondsG)"},
    {"slug": "ewkverbotsv", "en": "Single-Use Plastics Ban Ordinance (EWKVerbotsV)"},
    {"slug": "ewkkennzv", "en": "Single-Use Plastics Marking Ordinance (EWKKennzV)"},
    {"slug": "elektrostoffv", "en": "Hazardous Substances in EEE Ordinance (ElektroStoffV — RoHS)"},
    {"slug": "altholzv", "en": "Waste Wood Ordinance (AltholzV)"},
    {"slug": "bioabfv", "en": "Bio-Waste Ordinance (BioAbfV)"},
]

# TOC title sweep (German analog of UK_DISCOVERY_TERMS): precise EPR/circular-economy compound terms.
# "elektro" alone is unusable — the federal corpus is full of "elektronische Akte(nführung)"
# e-government law — so match the full compounds and exclude that cluster + other keyword riders
# (radioactive-waste "Verpackung", BEV fast-charging "Batterie", tomato-seed "Verpackung").
DE_DISCOVERY_TERMS = [
    "verpackung", "elektro- und elektronik", "elektro-altger", "elektroaltger",
    "batterien und akkumulatoren", "batterien und altbatterien", "kreislaufwirtschaft",
    "altfahrzeug", "einwegkunststoff", "produktverantwortung", "herstellerverantwortung",
    "altholz", "bioabf",
]
DE_NAME_EXCLUDE = re.compile(
    r"(elektronische[nr]? Akt|elektromagnet|Elektrizit|Besoldung|radioaktiv|Kernkraft|"
    r"Schnelllad|Saatgut|Tomaten)", re.I
)
_DE_ITEM_RE = re.compile(r"<item>\s*<title>(.*?)</title>\s*<link>(.*?)</link>\s*</item>", re.S)
_DE_KURZUE_RE = re.compile(r"<kurzue>(.*?)</kurzue>", re.S)
_DE_LANGUE_RE = re.compile(r"<langue>(.*?)</langue>", re.S)
_DE_JURABK_RE = re.compile(r"<jurabk>(.*?)</jurabk>", re.S)
_DE_TEXTDATEN_RE = re.compile(r"<textdaten>(.*?)</textdaten>", re.S)


class GermanyGiiClient(ForeignSourceClient):
    """gesetze-im-internet.de adapter. German federal enacted law, full-text XML (zipped), no key."""

    region = "DE"
    source = "gii"

    async def _toc(self) -> list[tuple[str, str]]:
        """Return (slug, title) for every federal law in the TOC sitemap."""
        resp = await self.http.get(DE_TOC)
        resp.raise_for_status()
        # The TOC is mislabeled UTF-8 but is actually ISO-8859-1 — decode as latin-1 so the German
        # keyword sweep sees real umlauts. (The per-law XML inside the zips IS valid UTF-8.)
        text = resp.content.decode("latin-1")
        out: list[tuple[str, str]] = []
        for title, link in _DE_ITEM_RE.findall(text):
            slug = link.rstrip("/").split("/")[-2]  # .../{slug}/xml.zip
            out.append((slug, title.strip()))
        return out

    async def discover(self) -> list[tuple[str, str]]:
        try:
            toc = await self._toc()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("de_toc_failed", error=str(e))
            return []
        out: dict[str, str] = {s["slug"]: s["en"] for s in DE_SEED_LAWS}
        for slug, title in toc:
            if slug in out:
                continue
            if DE_NAME_EXCLUDE.search(title):
                continue
            low = title.lower()
            if any(term in low for term in DE_DISCOVERY_TERMS):
                out.setdefault(slug, "")
        log.info("de_discovered", total=len(out), seeded=sum(1 for v in out.values() if v))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        import io
        import zipfile

        try:
            resp = await self.http.get(f"{DE_BASE}/{source_id}/xml.zip")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("de_fetch_failed", slug=source_id, error=str(e))
            return None
        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            xml_name = next((n for n in zf.namelist() if n.endswith(".xml")), None)
            if xml_name is None:
                log.warning("de_no_xml_in_zip", slug=source_id)
                return None
            raw = zf.read(xml_name).decode("utf-8", "replace")
        except (zipfile.BadZipFile, ValueError, KeyError) as e:
            log.warning("de_unzip_failed", slug=source_id, error=str(e))
            return None

        tm = _DE_KURZUE_RE.search(raw) or _DE_LANGUE_RE.search(raw) or _DE_JURABK_RE.search(raw)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        # Body: the long title (<langue>) leads, then every <textdaten> block (the §§ article text +
        # preamble). Fall back to the whole doc if the structure is unexpected.
        lm = _DE_LANGUE_RE.search(raw)
        parts = [lm.group(1)] if lm else []
        parts.extend(_DE_TEXTDATEN_RE.findall(raw))
        full_text = _strip_tags("\n\n".join(parts)) if parts else _strip_tags(raw)
        if len(full_text) < 100:
            log.warning("de_thin_text", slug=source_id, chars=len(full_text))
            return None

        return ForeignLaw(
            source_id=source_id,
            region=self.region,
            source=self.source,
            title=title,
            full_text=full_text,
            source_url=DE_PAGE.format(slug=source_id),
            english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Netherlands — wetten.overheid.nl / KOOP. Open, no key. SRU catalog (BWB collection) + a per-law
# manifest that points at the latest consolidated "toestand" XML. Archetype A.
#   discover: GET {SRU}?x-connection=BWB&query=overheidbwb.titel=<term>  -> BWBR ids + titles
#   law text: GET {REPO}/{BWBR}/manifest.xml (_latestItem) -> GET that toestand XML
# --------------------------------------------------------------------------------------------------

NL_SRU = "https://zoekservice.overheid.nl/sru/Search"
NL_REPO = "https://repository.officiele-overheidspublicaties.nl/bwb"
NL_PAGE = "https://wetten.overheid.nl/{bwb}"
NL_MAXREC = 30  # per discovery term

NL_SEED_LAWS: list[dict] = [
    {"bwb": "BWBR0035711", "en": "Packaging Management Decree 2014 (Besluit beheer verpakkingen — EPR)"},
]
# Dutch title-search terms (the NL analog of UK_DISCOVERY_TERMS). EPR lives in AMvBs/regelingen under
# the Wet milieubeheer; these compound terms keep the slice tight (Haiku judges the rest).
NL_DISCOVERY_TERMS = [
    "producentenverantwoordelijkheid",          # (extended) producer responsibility
    "verpakkingen",                             # packaging
    "elektrische en elektronische apparatuur",  # WEEE
    "batterijen",                               # batteries
    "autobanden",                               # tyres
    "autowrakken",                              # end-of-life vehicles
    "kunststofproducten voor eenmalig gebruik", # single-use plastics
    "textiel",                                  # textiles
]
_NL_REC_RE = re.compile(
    r"<dcterms:identifier>(BWBR\d+)</dcterms:identifier>\s*<dcterms:title>(.*?)</dcterms:title>", re.S
)
_NL_LATEST_RE = re.compile(r'_latestItem="([^"]+)"')
# The citeertitel element holds the short title but inlines a <meta-data> block after it.
_NL_CITEER_RE = re.compile(r"<citeertitel[^>]*>(.*?)(?:<meta-data>|</citeertitel>)", re.S)


class NetherlandsBwbClient(ForeignSourceClient):
    """wetten.overheid.nl adapter. Dutch consolidated law (BWB), SRU discovery + toestand XML, no key."""

    region = "NL"
    source = "bwb"

    async def discover(self) -> list[tuple[str, str]]:
        from urllib.parse import quote

        out: dict[str, str] = {s["bwb"]: s["en"] for s in NL_SEED_LAWS}
        for term in NL_DISCOVERY_TERMS:
            url = (f"{NL_SRU}?version=1.2&operation=searchRetrieve&x-connection=BWB"
                   f"&maximumRecords={NL_MAXREC}&query=overheidbwb.titel={quote(term)}")
            try:
                resp = await self.http.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("nl_search_failed", term=term, error=str(e))
                continue
            for bwb, _title in _NL_REC_RE.findall(resp.text):
                out.setdefault(bwb, "")
        log.info("nl_discovered", total=len(out), seeded=sum(1 for v in out.values() if v))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        base = f"{NL_REPO}/{source_id}"
        try:
            m = await self.http.get(f"{base}/manifest.xml")
            m.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("nl_manifest_failed", bwb=source_id, error=str(e))
            return None
        lm = _NL_LATEST_RE.search(m.text)
        if not lm:
            log.warning("nl_no_latest", bwb=source_id)
            return None
        try:
            x = await self.http.get(f"{base}/{lm.group(1)}")
            x.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("nl_text_failed", bwb=source_id, error=str(e))
            return None
        cm = _NL_CITEER_RE.search(x.text)
        title = _strip_tags(cm.group(1)) if cm else (english_label or source_id)
        full_text = _strip_tags(x.text)
        if len(full_text) < 100:
            log.warning("nl_thin_text", bwb=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=NL_PAGE.format(bwb=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Spain — BOE "Legislación Consolidada" open-data API. Open, no key. Per-norm REST (structured XML).
# Curated seed of the marquee EPR Royal Decrees (no clean full-text search endpoint). Archetype A.
#   law text: GET {API}/{BOE-A-id}/texto  (full consolidated XML);  /metadatos -> <titulo>
# --------------------------------------------------------------------------------------------------

ES_API = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{id}"
ES_PAGE = "https://www.boe.es/buscar/act.php?id={id}"
ES_SEED_LAWS: list[dict] = [
    {"id": "BOE-A-2022-5809", "en": "Law 7/2022 on waste and contaminated soil for a circular economy"},
    {"id": "BOE-A-2022-22690", "en": "Royal Decree 1055/2022 on packaging and packaging waste (EPR)"},
    {"id": "BOE-A-2015-1762", "en": "Royal Decree 110/2015 on waste electrical and electronic equipment"},
    {"id": "BOE-A-2008-2387", "en": "Royal Decree 106/2008 on batteries and accumulators"},
    {"id": "BOE-A-2021-5868", "en": "Royal Decree 265/2021 on end-of-life vehicles"},
    {"id": "BOE-A-2025-17186", "en": "Royal Decree 712/2025 on end-of-life tyres"},
    {"id": "BOE-A-2006-9832", "en": "Royal Decree 679/2006 on the management of used industrial oils"},
    {"id": "BOE-A-2024-21709", "en": "Royal Decree 1093/2024 on single-use tobacco-filter product waste (EPR)"},
]
_ES_TITULO_RE = re.compile(r"<titulo>(.*?)</titulo>", re.S)


class SpainBoeClient(ForeignSourceClient):
    """BOE Legislación Consolidada adapter. Spanish national EPR law, structured XML, no key."""

    region = "ES"
    source = "boe"

    async def discover(self) -> list[tuple[str, str]]:
        # No clean full-text search endpoint — curated marquee EPR set (framework + packaging/WEEE/
        # batteries Royal Decrees). Broaden by adding BOE-A ids as new stream decrees land.
        log.info("es_discovered", total=len(ES_SEED_LAWS), seeded=len(ES_SEED_LAWS))
        return [(s["id"], s["en"]) for s in ES_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        hdr = {"Accept": "application/xml"}
        title = english_label or source_id
        try:
            meta = await self.http.get(f"{ES_API.format(id=source_id)}/metadatos", headers=hdr)
            if meta.status_code == 200:
                tm = _ES_TITULO_RE.search(meta.text)
                if tm:
                    title = _strip_tags(tm.group(1))
            txt = await self.http.get(f"{ES_API.format(id=source_id)}/texto", headers=hdr)
            txt.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("es_fetch_failed", id=source_id, error=str(e))
            return None
        full_text = _strip_tags(txt.text)
        if len(full_text) < 100:
            log.warning("es_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=ES_PAGE.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Chile — Ley Chile (Biblioteca del Congreso Nacional). Open, no key. Per-norm structured XML by
# idNorma. Ley 20.920 (Ley REP) is the LatAm flagship; it enumerates all six priority products.
#   law text: GET {API}?opt=7&idNorma=<id>  (Norma XML; <TituloNorma>, derogado attr)
# --------------------------------------------------------------------------------------------------

CL_API = "https://www.leychile.cl/Consulta/obtxml?opt=7&idNorma={id}"
CL_PAGE = "https://www.bcn.cl/leychile/navegar?idNorma={id}"
CL_SEED_LAWS: list[dict] = [
    {"id": "1090894", "en": "Law 20.920 — Framework for Waste Management, EPR and Recycling (Ley REP)"},
    {"id": "1154847", "en": "Decree 8/2019 — EPR collection/recovery targets for tyres"},
    {"id": "1157019", "en": "Decree 12/2020 — EPR collection/recovery targets for packaging"},
    {"id": "1223902", "en": "Decree 22/2025 — EPR targets for batteries and electrical/electronic equipment"},
    {"id": "1208163", "en": "Decree 47/2023 — EPR collection/recovery targets for lubricant oils"},
    {"id": "1109335", "en": "Decree 7/2017 — Recycling Fund regulation (Fondo para el Reciclaje)"},
]
_CL_TITULO_RE = re.compile(r"<TituloNorma>(.*?)</TituloNorma>", re.S)
_CL_DEROGADO_RE = re.compile(r'derogado="([^"]+)"')


class ChileLeychileClient(ForeignSourceClient):
    """Ley Chile (BCN) adapter. Chilean national law, structured XML by idNorma, no key."""

    region = "CL"
    source = "leychile"

    async def discover(self) -> list[tuple[str, str]]:
        # Curated seed (the comprehensive Ley REP framework). Expand with the stream-specific REP
        # supreme decrees' idNormas as they're confirmed.
        log.info("cl_discovered", total=len(CL_SEED_LAWS), seeded=len(CL_SEED_LAWS))
        return [(s["id"], s["en"]) for s in CL_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(CL_API.format(id=source_id))
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("cl_fetch_failed", id=source_id, error=str(e))
            return None
        dm = _CL_DEROGADO_RE.search(r.text)
        if dm and dm.group(1) != "no derogado":  # skip repealed norms
            log.warning("cl_derogado", id=source_id)
            return None
        tm = _CL_TITULO_RE.search(r.text)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("cl_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=CL_PAGE.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Sweden — Riksdagen open data (SFS). Open, no key. Documented REST: a dokumentlista catalog + a
# per-document text endpoint. Archetype A.
#   discover: GET {LIST}?sok=<term>&doktyp=sfs&utformat=json  -> sfs ids + titles
#   law text: GET {DOC}/{id}.html  (-> <title> + body)
# --------------------------------------------------------------------------------------------------

SE_LIST = "https://data.riksdagen.se/dokumentlista/"
SE_DOC = "https://data.riksdagen.se/dokument/{id}.html"
SE_PAGE = "https://data.riksdagen.se/dokument/{id}"
SE_MAXREC = 40

SE_SEED_LAWS: list[dict] = [
    {"id": "sfs-2022-1274", "en": "Ordinance (2022:1274) on producer responsibility for packaging"},
    {"id": "sfs-2022-1276", "en": "Ordinance (2022:1276) on producer responsibility for electrical and electronic equipment (WEEE)"},
    {"id": "sfs-2023-133", "en": "Ordinance (2023:133) on producer responsibility for tyres"},
    {"id": "sfs-2023-132", "en": "Ordinance (2023:132) on producer responsibility for cars (ELV)"},
]
SE_DISCOVERY_TERMS = ["producentansvar"]  # producer responsibility (precise Swedish compound)
_SE_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


class SwedenRiksdagenClient(ForeignSourceClient):
    """Riksdagen open-data adapter. Swedish SFS ordinances, REST catalog + per-doc HTML, no key."""

    region = "SE"
    source = "sfs"

    async def discover(self) -> list[tuple[str, str]]:
        from urllib.parse import quote

        out: dict[str, str] = {s["id"]: s["en"] for s in SE_SEED_LAWS}
        for term in SE_DISCOVERY_TERMS:
            url = f"{SE_LIST}?sok={quote(term)}&doktyp=sfs&utformat=json&sz={SE_MAXREC}"
            try:
                resp = await self.http.get(url)
                resp.raise_for_status()
                docs = (resp.json().get("dokumentlista") or {}).get("dokument") or []
            except (httpx.HTTPError, ValueError) as e:
                log.warning("se_search_failed", term=term, error=str(e))
                continue
            for d in docs:
                did = d.get("id")
                if did:
                    out.setdefault(did, "")
        log.info("se_discovered", total=len(out), seeded=sum(1 for v in out.values() if v))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(SE_DOC.format(id=source_id))
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("se_fetch_failed", id=source_id, error=str(e))
            return None
        tm = _SE_TITLE_RE.search(r.text)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("se_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=SE_PAGE.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Ireland — electronic Irish Statute Book (eISB). Open, no key, English. No catalog API: address acts
# by their ELI URI with a format suffix. EPR lives in Statutory Instruments (transposing EU dirs).
#   law text: GET {BASE}/{eli-path}/print  (full HTML; <title> = official name)
# --------------------------------------------------------------------------------------------------

IE_BASE = "https://www.irishstatutebook.ie"
IE_PAGE = IE_BASE + "/{path}"
IE_SEED_LAWS: list[dict] = [
    {"path": "eli/2024/si/33/made/en", "en": "Separate Collection (Deposit Return Scheme) Regulations 2024"},
    {"path": "eli/2014/si/149/made/en", "en": "EU (Waste Electrical and Electronic Equipment) Regulations 2014"},
    {"path": "eli/2014/si/283/made/en", "en": "EU (Batteries and Accumulators) Regulations 2014"},
    {"path": "eli/2014/si/282/made/en", "en": "EU (Packaging) Regulations 2014"},
    {"path": "eli/2014/si/281/made/en", "en": "EU (End-of-Life Vehicles) Regulations 2014"},
    {"path": "eli/2007/si/798/made/en", "en": "Waste Management (Tyres and Waste Tyres) Regulations 2007"},
]
_IE_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


class IrelandEisbClient(ForeignSourceClient):
    """electronic Irish Statute Book adapter. Irish enacted law/SIs, full-text HTML via ELI URIs, no key."""

    region = "IE"
    source = "eisb"

    async def discover(self) -> list[tuple[str, str]]:
        # Seed-only (no catalog API): the marquee EPR Statutory Instruments by ELI path. fetch() drops
        # any that 404. Discover more SI numbers via gov.ie/EPA EPR pages, then add here.
        log.info("ie_discovered", total=len(IE_SEED_LAWS), seeded=len(IE_SEED_LAWS))
        return [(s["path"], s["en"]) for s in IE_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{IE_BASE}/{source_id}/print")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("ie_fetch_failed", path=source_id, error=str(e))
            return None
        tm = _IE_TITLE_RE.search(r.text)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("ie_thin_text", path=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=IE_PAGE.format(path=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Austria — RIS (Rechtsinformationssystem). Open, no key. The OGD REST API indexes consolidated
# federal law at the §-fragment level (each § is a "BrKons" doc), so we don't crawl fragments — we
# seed each EPR law's Gesetzesnummer (looked up once via the API) and fetch the whole consolidated act
# in one GET via GeltendeFassung.wxe. Archetype A.
#   law text: GET GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=<gn>  (whole consolidated HTML)
# --------------------------------------------------------------------------------------------------

AT_FASSUNG = "https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer={gn}"
AT_PAGE = AT_FASSUNG  # the GeltendeFassung page is also the human-facing view
AT_SEED_LAWS: list[dict] = [
    {"gn": "20002086", "en": "Waste Management Act 2002 (Abfallwirtschaftsgesetz — framework)"},
    {"gn": "20008902", "en": "Packaging Ordinance 2014 (Verpackungsverordnung — EPR)"},
    {"gn": "20004052", "en": "Waste Electrical and Electronic Equipment Ordinance (Elektroaltgeräteverordnung)"},
    {"gn": "20005815", "en": "Batteries Ordinance (Batterienverordnung)"},
    {"gn": "20002302", "en": "End-of-Life Vehicles Ordinance (Altfahrzeugeverordnung)"},
]
# The GeltendeFassung HTML is RIS-chrome-wrapped; the consolidated law body lives in the content div.
_AT_BODY_RE = re.compile(r'<div[^>]*id="[Cc]ontent[^"]*"[^>]*>(.*)', re.S)


class AustriaRisClient(ForeignSourceClient):
    """RIS adapter. Austrian consolidated federal EPR law, whole-act HTML via GeltendeFassung, no key."""

    region = "AT"
    source = "ris"

    async def discover(self) -> list[tuple[str, str]]:
        # Seed-only: each EPR law's Gesetzesnummer (from the RIS OGD API). Broaden by looking up more
        # Gesetzesnummern (Altölverordnung, Deponieverordnung, …) and adding them here.
        log.info("at_discovered", total=len(AT_SEED_LAWS), seeded=len(AT_SEED_LAWS))
        return [(s["gn"], s["en"]) for s in AT_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(AT_FASSUNG.format(gn=source_id))
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("at_fetch_failed", gn=source_id, error=str(e))
            return None
        # Strip the RIS page chrome to the content region when identifiable; else strip the whole page.
        bm = _AT_BODY_RE.search(r.text)
        full_text = _strip_tags(bm.group(1) if bm else r.text)
        if len(full_text) < 100:
            log.warning("at_thin_text", gn=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or f"RIS Bundesrecht {source_id}",
            full_text=full_text, source_url=AT_PAGE.format(gn=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Brazil — Planalto (Casa Civil) ccivil_03 consolidated federal law. Open, no key. No live SRU
# (LexML's SRU moved/retired), so seed the marquee EPR instruments by their ccivil_03 path and fetch
# the consolidated HTML. NOTE: Planalto serves ISO-8859-1 (mislabeled), so decode latin-1. Archetype A.
#   law text: GET planalto.gov.br/ccivil_03/{path}  (consolidated HTML, latin-1)
# --------------------------------------------------------------------------------------------------

BR_BASE = "https://www.planalto.gov.br/ccivil_03"
BR_SEED_LAWS: list[dict] = [
    {"path": "_ato2007-2010/2010/lei/l12305.htm",
     "en": "Law 12.305/2010 — National Solid Waste Policy (PNRS; reverse logistics / shared responsibility)"},
    {"path": "_ato2019-2022/2022/decreto/D10936.htm",
     "en": "Decree 10.936/2022 — regulation of the National Solid Waste Policy"},
    {"path": "_ato2023-2026/2023/decreto/D11413.htm",
     "en": "Decree 11.413/2023 — reverse logistics systems"},
    {"path": "_ato2023-2026/2025/decreto/D12688.htm",
     "en": "Decree 12.688/2025 — reverse logistics & recycled content for plastic packaging"},
    {"path": "_ato2019-2022/2021/lei/L14260.htm",
     "en": "Law 14.260/2021 — incentives for recycling"},
]


class BrazilPlanaltoClient(ForeignSourceClient):
    """Planalto ccivil_03 adapter. Brazilian consolidated federal EPR law, HTML (latin-1), no key."""

    region = "BR"
    source = "planalto"

    async def discover(self) -> list[tuple[str, str]]:
        # Seed-only (no live catalog API). Broaden by adding ccivil_03 paths for new EPR decrees.
        log.info("br_discovered", total=len(BR_SEED_LAWS), seeded=len(BR_SEED_LAWS))
        return [(s["path"], s["en"]) for s in BR_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{BR_BASE}/{source_id}")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("br_fetch_failed", path=source_id, error=str(e))
            return None
        # Planalto is ISO-8859-1 but often mislabeled — latin-1 decode never raises and is correct here.
        full_text = _strip_tags(r.content.decode("latin-1", "replace"))
        if len(full_text) < 100:
            log.warning("br_thin_text", path=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=f"{BR_BASE}/{source_id}", english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Switzerland — Fedlex. Open, no key, but the website is a JS SPA (plain GET returns the no-script
# shell). The machine path is the LINDAS SPARQL endpoint (JOLux ontology) → resolve an act's ELI to
# its latest in-force consolidated Akoma Ntoso XML file, then fetch that. CH is not in the EU, so its
# WEEE/packaging/deposit regime is its own (not EUR-Lex transposition). Archetype A.
#   discover: seed ELI cc-ids of the EPR ordinances (precise — the corpus is full of "elektr…" noise)
#   law text: SPARQL {cc} -> latest de/xml file URL -> GET that XML
# --------------------------------------------------------------------------------------------------

CH_SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
CH_PAGE = "https://www.fedlex.admin.ch/eli/{cc}/de"
CH_SEED_LAWS: list[dict] = [
    {"cc": "cc/2021/633", "en": "Ordinance on the Return, Take-Back and Disposal of Electrical and Electronic Equipment (VREG — WEEE)"},
    {"cc": "cc/2005/551", "en": "Ordinance on Movements of Waste (VeVA)"},
    {"cc": "cc/2015/891", "en": "Ordinance on the Avoidance and Disposal of Waste (VVEA)"},
    {"cc": "cc/2000/299", "en": "Ordinance on Beverage Containers (VGV — deposit/recycling)"},
    {"cc": "cc/2001/359", "en": "Ordinance on the Advance Disposal Fee (VEG — EPR financing)"},
]
# JOLux: a ConsolidationAbstract's in-force versions (Consolidation) realize/embody manifestations,
# each exemplified by a file URL; pick the latest-dated German XML.
_CH_FILE_QUERY = (
    "PREFIX jolux:<http://data.legilux.public.lu/resource/ontology/jolux#> "
    "SELECT ?file WHERE {{ "
    "?cons jolux:isMemberOf <https://fedlex.data.admin.ch/eli/{cc}> ; "
    "jolux:dateApplicability ?date ; jolux:isRealizedBy/jolux:isEmbodiedBy ?manif . "
    "?manif jolux:isExemplifiedBy ?file ; jolux:userFormat ?fmt . "
    'FILTER(CONTAINS(STR(?fmt),"xml") && CONTAINS(STR(?file),"/de/xml/")) '
    "}} ORDER BY DESC(?date) LIMIT 1"
)


class SwitzerlandFedlexClient(ForeignSourceClient):
    """Fedlex adapter. Swiss consolidated federal EPR law via LINDAS SPARQL → Akoma Ntoso XML, no key."""

    region = "CH"
    source = "fedlex"

    async def discover(self) -> list[tuple[str, str]]:
        # Seed-only: ELI cc-ids of the EPR ordinances (broad title search returns electricity-law noise).
        log.info("ch_discovered", total=len(CH_SEED_LAWS), seeded=len(CH_SEED_LAWS))
        return [(s["cc"], s["en"]) for s in CH_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            q = await self.http.get(
                CH_SPARQL, params={"query": _CH_FILE_QUERY.format(cc=source_id), "format": "json"}
            )
            q.raise_for_status()
            bindings = q.json().get("results", {}).get("bindings", [])
        except (httpx.HTTPError, ValueError) as e:
            log.warning("ch_sparql_failed", cc=source_id, error=str(e))
            return None
        if not bindings:
            log.warning("ch_no_xml", cc=source_id)
            return None
        file_url = bindings[0]["file"]["value"]
        try:
            x = await self.http.get(file_url)
            x.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("ch_file_failed", cc=source_id, error=str(e))
            return None
        full_text = _strip_tags(x.text)
        if len(full_text) < 100:
            log.warning("ch_thin_text", cc=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=CH_PAGE.format(cc=source_id), english_label=english_label,
        )


# Registry of available foreign adapters, by region code. New countries: add the subclass + register.
# Note: a registry key is just a lookup handle (e.g. "FR_CODE"); the client's own `.region` drives the
# row's region (LegifranceCodeClient writes region="FR"), so JORF + codified FR data co-exist.
FOREIGN_CLIENTS: dict[str, type[ForeignSourceClient]] = {
    "JP": JapanEgovClient,
    "JP_ORD": JapanEgovOrdinanceClient,
    "FR": LegifranceClient,
    "FR_CODE": LegifranceCodeClient,
    "UK": UKLegislationClient,
    "DE": GermanyGiiClient,
    "NL": NetherlandsBwbClient,
    "ES": SpainBoeClient,
    "CL": ChileLeychileClient,
    "SE": SwedenRiksdagenClient,
    "IE": IrelandEisbClient,
    "AT": AustriaRisClient,
    "BR": BrazilPlanaltoClient,
    "CH": SwitzerlandFedlexClient,
}


async def sync_foreign(
    region: str,
    *,
    classify: bool = True,
    only_new: bool = False,
    max_laws: int | None = None,
) -> dict:
    """End-to-end ingest for one foreign region: discover -> fetch -> upsert(bills+bill_texts) ->
    classify. The generic analog of sync_eurlex, keyed on the `foreign_id` column.

    - only_new: skip foreign_ids already in the DB (cheap refresh mode).
    - max_laws: cap laws processed this run (bounds a backfill / runaway).
    Foreign acts bypass the US keyword gate (curated source); the Haiku confidence floor decides
    ce_relevant. Commits every CHECKPOINT laws so a long run is checkpointed and re-runnable.
    """
    from sqlalchemy import func, select

    from app.classification.pipeline import ClassificationPipeline
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models import Bill, BillText

    client_cls = FOREIGN_CLIENTS.get(region)
    if client_cls is None:
        raise ValueError(f"no foreign adapter registered for region {region!r}")

    async with client_cls() as client:
        candidates = await client.discover()
        if only_new:
            async with AsyncSessionLocal() as db:
                existing = set(
                    (
                        await db.execute(
                            select(Bill.foreign_id).where(Bill.foreign_id.is_not(None))
                        )
                    ).scalars().all()
                )
            prefix = f"{client.region}:{client.source}:"
            candidates = [(sid, lbl) for sid, lbl in candidates if prefix + sid not in existing]
        if max_laws is not None:
            candidates = candidates[:max_laws]

        log.info("foreign_sync_start", region=region, to_process=len(candidates), only_new=only_new)

        ingested: list[int] = []
        fetched = skipped = 0
        CHECKPOINT = 25
        total = len(candidates)
        async with AsyncSessionLocal() as db:
            for idx, (source_id, english_label) in enumerate(candidates, 1):
                law = await client.fetch(source_id, english_label)
                if law is None:
                    skipped += 1
                    continue
                fetched += 1
                bill = (
                    await db.execute(select(Bill).where(Bill.foreign_id == law.foreign_id))
                ).scalar_one_or_none()
                if bill is None:
                    bill = Bill(foreign_id=law.foreign_id, region=law.region, state=law.region)
                    db.add(bill)
                bill.region = law.region
                bill.state = law.region
                bill.bill_number = law.bill_number
                bill.title = law.english_label or law.title
                bill.description = law.summary
                bill.status = law.status
                bill.source_url = law.source_url
                await db.flush()

                bt = (
                    await db.execute(select(BillText).where(BillText.bill_id == bill.id))
                ).scalar_one_or_none()
                if bt is None:
                    bt = BillText(bill_id=bill.id)
                    db.add(bt)
                bt.text = cap_for_tsvector(law.full_text)
                bt.char_len = len(bt.text)
                ingested.append(bill.id)
                if idx % CHECKPOINT == 0:
                    await db.commit()
                    log.info("foreign_fetch_progress", region=region, done=idx, total=total,
                             fetched=fetched, skipped=skipped)
            await db.commit()

    summary = {"region": region, "discovered": len(candidates), "fetched": fetched,
               "skipped": skipped, "ingested": len(ingested), "classified": 0, "relevant": 0}

    if classify and ingested:
        chunk = max(1, settings.max_haiku_calls_per_run)
        for i in range(0, len(ingested), chunk):
            chunk_ids = ingested[i : i + chunk]
            async with AsyncSessionLocal() as db:
                bills = list(
                    (await db.execute(select(Bill).where(Bill.id.in_(chunk_ids)))).scalars().all()
                )
                res = await ClassificationPipeline().run(db, bills, skip_keyword_filter=True)
                summary["classified"] += res.classified_haiku
        async with AsyncSessionLocal() as db:
            # Tally on the client's DATA region (client_cls.region), not the registry key — they differ
            # for code-layer adapters (key "FR_CODE" writes region="FR").
            summary["relevant"] = (
                await db.execute(
                    select(func.count()).select_from(Bill)
                    .where(Bill.region == client_cls.region, Bill.ce_relevant.is_(True))
                )
            ).scalar_one()

    log.info("foreign_sync_done", **summary)
    return summary

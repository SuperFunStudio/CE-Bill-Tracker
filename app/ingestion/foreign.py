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

import datetime
import html
import io
import re
import zipfile
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

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
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


# A DOCX is a zip whose word/document.xml holds the body as OOXML. Paragraphs are <w:p>, text runs
# <w:t>, tabs <w:tab/>, line breaks <w:br/>. Naively stripping every tag glues paragraphs together,
# so map the structural elements to whitespace FIRST, then reuse _strip_tags. Used by sources that
# only expose body text as a Word download (China flk, and — later — AU Victoria/ACT).
_DOCX_PARA_RE = re.compile(r"</w:p>", re.I)
_DOCX_BREAK_RE = re.compile(r"<w:(?:br|tab)\b[^>]*/?>", re.I)


def docx_to_text(data: bytes) -> str:
    """Extract plain text from DOCX bytes (word/document.xml only; ignores headers/footnotes)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError, OSError) as e:
        log.warning("docx_parse_failed", error=str(e))
        return ""
    xml = _DOCX_BREAK_RE.sub(" ", xml)
    xml = _DOCX_PARA_RE.sub("\n", xml)
    return _strip_tags(xml)


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
    # Explicit enactment date, ONLY when the adapter obtains a real one from the source (most don't).
    # Left None, `resolved_status_date` derives a year-only date from the id/title so every law — incl.
    # future regions — still lands dated. Set this to override with a precise date. See law_dates.
    status_date: datetime.date | None = None

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

    @property
    def resolved_status_date(self) -> datetime.date | None:
        """Enactment date for the bill: the adapter's explicit date if it set one, else a year-only
        date derived from the id/title (same logic as the one-time backfill, so dates stay consistent).
        Derives from the English label first, then native title — the DB `title` sync_foreign stores."""
        from app.ingestion.law_dates import derive_status_date
        return self.status_date or derive_status_date(
            self.source_id, self.english_label or self.title)


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


# Japanese era -> Gregorian base year (era year N = base + N - 1). e-Gov <Law> tags name the era; the
# LawId's leading digit is the era CODE (1=Meiji … 5=Reiwa), used as a fallback when the tag is absent.
_JP_ERA_BASE = {"Meiji": 1868, "Taisho": 1912, "Showa": 1926, "Heisei": 1989, "Reiwa": 2019}
_JP_ERA_DIGIT = {"1": 1868, "2": 1912, "3": 1926, "4": 1989, "5": 2019}
_JP_LAW_TAG_RE = re.compile(r"<Law\b[^>]*>")


def jp_promulgation_date(raw_xml: str, law_id: str = "") -> "datetime.date | None":
    """Real promulgation date from the e-Gov <Law> root tag — <Law Era="Heisei" Year="24"
    PromulgateMonth="8" PromulgateDay="1"> -> 2012-08-01. Degrades to the era code + year encoded in the
    LawId (year-only, Jan 1) when the tag/day is missing. Gregorian year = era base + era year - 1."""
    base = jyear = mon = day = None
    m = _JP_LAW_TAG_RE.search(raw_xml or "")
    if m:
        tag = m.group(0)
        if e := re.search(r'Era="([^"]+)"', tag):
            base = _JP_ERA_BASE.get(e.group(1))
        if y := re.search(r'Year="(\d+)"', tag):
            jyear = int(y.group(1))
        if mo := re.search(r'PromulgateMonth="(\d+)"', tag):
            mon = int(mo.group(1))
        if da := re.search(r'PromulgateDay="(\d+)"', tag):
            day = int(da.group(1))
    if (base is None or jyear is None) and len(law_id) >= 3:  # fallback: era code + year in the LawId
        base = base or _JP_ERA_DIGIT.get(law_id[0])
        if jyear is None and law_id[1:3].isdigit():
            jyear = int(law_id[1:3])
    if not (base and jyear):
        return None
    g = base + jyear - 1
    for mm, dd in ((mon, day), (mon, 1), (1, 1)):  # degrade day -> month -> year on any invalid part
        try:
            return datetime.date(g, mm or 1, dd or 1)
        except ValueError:
            continue
    return None


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
            status_date=jp_promulgation_date(raw, source_id),  # real promulgation date from <Law> tag
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


# --------------------------------------------------------------------------------------------------
# Poland — Sejm ELI API (api.sejm.gov.pl/eli). Open, no key, OpenAPI 3.0.3. Catalog search + per-act
# metadata + text.html / text.pdf. Modern acts serve structured HTML; older consolidated texts
# (obwieszczenia jednolity tekst) are PDF-only — we ingest the HTML-available ones and skip PDF
# (no extraction layer). Archetype A.
#   discover: GET /acts/search?title=<term>  -> {publisher, year, pos, textHTML}
#   law text: GET /acts/{pub}/{year}/{pos}        (JSON metadata: title, textHTML)
#             GET /acts/{pub}/{year}/{pos}/text.html
# --------------------------------------------------------------------------------------------------

PL_API = "https://api.sejm.gov.pl/eli/acts"
PL_PAGE = "https://api.sejm.gov.pl/eli/acts/{id}/text.html"
PL_MAXREC = 25  # per term
# Polish title-search terms for the EPR / waste cluster.
PL_DISCOVERY_TERMS = [
    "odpadach",                                  # on waste (framework)
    "gospodarce opakowaniami",                   # packaging management (EPR)
    "zużytym sprzęcie elektrycznym",             # WEEE
    "bateriach i akumulatorach",                 # batteries & accumulators
    "pojazdach wycofanych z eksploatacji",       # end-of-life vehicles
    "rozszerzonej odpowiedzialności producenta", # extended producer responsibility
]


class PolandEliClient(ForeignSourceClient):
    """Sejm ELI API adapter. Polish consolidated law, REST catalog + per-act HTML, no key.
    Skips PDF-only consolidated texts (no extraction layer)."""

    region = "PL"
    source = "eli"
    _JSON = {"Accept": "application/json"}

    async def discover(self) -> list[tuple[str, str]]:
        from urllib.parse import quote

        out: dict[str, str] = {}
        for term in PL_DISCOVERY_TERMS:
            url = f"{PL_API}/search?title={quote(term)}&limit={PL_MAXREC}"
            try:
                resp = await self.http.get(url, headers=self._JSON)
                resp.raise_for_status()
                items = resp.json().get("items", [])
            except (httpx.HTTPError, ValueError) as e:
                log.warning("pl_search_failed", term=term, error=str(e))
                continue
            for it in items:
                if not it.get("textHTML"):  # skip PDF-only consolidated texts
                    continue
                pub, year, pos = it.get("publisher"), it.get("year"), it.get("pos")
                if pub and year and pos:
                    out.setdefault(f"{pub}/{year}/{pos}", "")
        log.info("pl_discovered", total=len(out))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            meta = await self.http.get(f"{PL_API}/{source_id}", headers=self._JSON)
            meta.raise_for_status()
            md = meta.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("pl_meta_failed", id=source_id, error=str(e))
            return None
        if not md.get("textHTML"):
            log.warning("pl_no_html", id=source_id)
            return None
        title = md.get("title") or english_label or source_id
        try:
            h = await self.http.get(f"{PL_API}/{source_id}/text.html")
            h.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("pl_text_failed", id=source_id, error=str(e))
            return None
        full_text = _strip_tags(h.text)
        if len(full_text) < 100:
            log.warning("pl_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=PL_PAGE.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# South Korea — law.go.kr DRF Open API. Requires a free "OC" id (registered email prefix at
# open.law.go.kr) AND the calling IP/domain registered there — so this stays dormant until
# settings.lawgokr_oc is set (mirrors the FR PISTE account-side setup). Korean full text (XML).
# NOTE: written to the documented DRF contract but UNVERIFIED end-to-end (no OC during build); the
# first real run should confirm the Korean response tag names below.
#   discover: GET lawSearch.do?OC=&target=law&type=XML&query=<term>  -> 법령일련번호 (MST) list
#   law text: GET lawService.do?OC=&target=law&type=XML&MST=<mst>    -> full law XML
# --------------------------------------------------------------------------------------------------

KR_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
KR_SERVICE = "https://www.law.go.kr/DRF/lawService.do"
KR_PAGE = "https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={mst}"
KR_MAXREC = 20
KR_DISCOVERY_TERMS = ["자원순환", "재활용", "순환경제", "포장재", "전기·전자제품 및 자동차"]
_KR_MST_RE = re.compile(r"<법령일련번호>(\d+)</법령일련번호>")
_KR_NAME_RE = re.compile(r"<법령명_?한글>(.*?)</법령명_?한글>", re.S)
_KR_FAIL = "검증에 실패"  # "verification failed" — bad/unregistered OC


class KoreaLawGoKrClient(ForeignSourceClient):
    """law.go.kr DRF adapter. Korean national EPR law, XML. Dormant until lawgokr_oc is configured."""

    region = "KR"
    source = "lawgokr"

    @staticmethod
    def _oc() -> str:
        from app.config import settings
        return settings.lawgokr_oc

    async def discover(self) -> list[tuple[str, str]]:
        oc = self._oc()
        if not oc:
            log.warning("kr_no_oc", hint="set lawgokr_oc in .env (register at open.law.go.kr)")
            return []
        out: dict[str, str] = {}
        for term in KR_DISCOVERY_TERMS:
            params = {"OC": oc, "target": "law", "type": "XML", "query": term, "display": KR_MAXREC}
            try:
                resp = await self.http.get(KR_SEARCH, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("kr_search_failed", term=term, error=str(e))
                continue
            if _KR_FAIL in resp.text:
                log.warning("kr_oc_invalid", hint="OC or calling IP/domain not registered at open.law.go.kr")
                return []
            for mst in _KR_MST_RE.findall(resp.text):
                out.setdefault(mst, "")
        log.info("kr_discovered", total=len(out))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        oc = self._oc()
        if not oc:
            return None
        params = {"OC": oc, "target": "law", "type": "XML", "MST": source_id}
        try:
            r = await self.http.get(KR_SERVICE, params=params)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("kr_fetch_failed", mst=source_id, error=str(e))
            return None
        if _KR_FAIL in r.text:
            return None
        tm = _KR_NAME_RE.search(r.text)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("kr_thin_text", mst=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=KR_PAGE.format(mst=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Laws.Africa (Indigo Content API) — pan-African Akoma Ntoso. ONE API/format covers many African
# jurisdictions (FRBR-URI document model). Archetype B: every content endpoint is token-gated (free
# token at platform.laws.africa; sandbox = 100 calls/day, 1 country). Per-country subclasses set the
# region + FRBR place code + seed URIs. Stays dormant until settings.lawsafrica_token is set.
# **LICENSING**: commons content is CC-BY-NC-SA (non-commercial) — clear commercial licensing with
# Laws.Africa before ingesting full text into the paid product (metadata + link-out is the safe mode).
# UNVERIFIED end-to-end (no token during build); confirm response shape on first authenticated run.
#   law text: GET api.laws.africa/v2/{frbr_uri}/eng.xml  (Bearer token) ; /eng.json for the title
# --------------------------------------------------------------------------------------------------

LAWSAFRICA_API = "https://api.laws.africa/v2"
AFRICA_EPR_TERMS = ("waste", "packaging", "extended producer", "plastic", "e-waste",
                    "recycling", "circular economy", "deposit")


class LawsAfricaClient(ForeignSourceClient):
    """Indigo Content API base. Subclass per country: set region, place (FRBR code), reader, SEEDS."""

    source = "lawsafrica"
    place: str = ""          # FRBR place code, e.g. "za"
    reader: str = "https://lawlibrary.org.za"
    SEEDS: list[dict] = []

    @staticmethod
    def _token() -> str:
        from app.config import settings
        return settings.lawsafrica_token

    def _hdr(self) -> dict:
        return {**_BROWSER_HEADERS, "Authorization": f"Bearer {self._token()}"}

    async def discover(self) -> list[tuple[str, str]]:
        if not self._token():
            log.warning("lawsafrica_no_token",
                        hint="set lawsafrica_token (platform.laws.africa); clear CC-BY-NC-SA commercial licensing")
            return []
        out: dict[str, str] = {s["uri"]: s["en"] for s in self.SEEDS}
        # Best-effort: enumerate the country's works and keyword-filter titles for the EPR cluster.
        try:
            r = await self.http.get(f"{LAWSAFRICA_API}/akn/{self.place}/.json", headers=self._hdr())
            if r.status_code == 200:
                for w in r.json().get("results", []):
                    uri = (w.get("frbr_uri") or "").lstrip("/")
                    title = (w.get("title") or "").lower()
                    if uri and any(t in title for t in AFRICA_EPR_TERMS):
                        out.setdefault(uri, "")
        except (httpx.HTTPError, ValueError) as e:
            log.warning("lawsafrica_list_failed", place=self.place, error=str(e))
        log.info("lawsafrica_discovered", place=self.place, total=len(out))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        if not self._token():
            return None
        hdr = self._hdr()
        title = english_label or source_id
        try:
            j = await self.http.get(f"{LAWSAFRICA_API}/{source_id}/eng.json", headers=hdr)
            if j.status_code == 200:
                title = j.json().get("title") or title
            x = await self.http.get(f"{LAWSAFRICA_API}/{source_id}/eng.xml", headers=hdr)
            x.raise_for_status()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("lawsafrica_fetch_failed", uri=source_id, error=str(e))
            return None
        full_text = _strip_tags(x.text)
        if len(full_text) < 100:
            log.warning("lawsafrica_thin_text", uri=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=f"{self.reader}/{source_id}", english_label=english_label,
        )


class LawsAfricaZAClient(LawsAfricaClient):
    region = "ZA"
    place = "za"
    reader = "https://lawlibrary.org.za"
    SEEDS = [
        {"uri": "akn/za/act/2008/59", "en": "National Environmental Management: Waste Act 59 of 2008"},
        {"uri": "akn/za/act/gn/2020/1184", "en": "Extended Producer Responsibility Regulations, 2020"},
    ]


class LawsAfricaKEClient(LawsAfricaClient):
    region = "KE"
    place = "ke"
    reader = "https://new.kenyalaw.org"
    SEEDS = [
        {"uri": "akn/ke/act/2022/31", "en": "Sustainable Waste Management Act, No. 31 of 2022"},
    ]


# --------------------------------------------------------------------------------------------------
# Denmark — retsinformation.dk. Open, no key. No search API (SPA filters client-side), so seed ELI
# ids and fetch the server-rendered LexDania XML. Archetype A.
#   law text: GET /eli/lta/{year}/{number}/xml   (LexDania XML; <DocumentTitle> in <Meta>)
# --------------------------------------------------------------------------------------------------

DK_BASE = "https://www.retsinformation.dk/eli"
DK_SEED_LAWS: list[dict] = [
    {"id": "lta/2025/1146", "en": "Packaging Ordinance — EPR for packaging (Emballagebekendtgørelsen)"},
    {"id": "lta/2025/882", "en": "Extended Producer Responsibility for certain single-use plastic products"},
    {"id": "lta/2014/130", "en": "Waste Electrical and Electronic Equipment (WEEE) Ordinance"},
    {"id": "lta/2015/1453", "en": "Batteries and Accumulators Ordinance"},
    {"id": "lta/2019/1337", "en": "End-of-Life Vehicles Ordinance"},
    {"id": "lta/2019/1218", "en": "Environmental Protection Act (framework)"},
]
_DK_TITLE_RE = re.compile(r"<DocumentTitle[^>]*>(.*?)</DocumentTitle>", re.S)


class DenmarkRetsinfoClient(ForeignSourceClient):
    """retsinformation.dk adapter. Danish consolidated law, LexDania XML, no key (curated seeds)."""

    region = "DK"
    source = "retsinfo"

    async def discover(self) -> list[tuple[str, str]]:
        log.info("dk_discovered", total=len(DK_SEED_LAWS))
        return [(s["id"], s["en"]) for s in DK_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{DK_BASE}/{source_id}/xml")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("dk_fetch_failed", id=source_id, error=str(e))
            return None
        tm = _DK_TITLE_RE.search(r.text)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("dk_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=f"{DK_BASE}/{source_id}", english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Finland — opendata.finlex.fi (new 2024 Finlex). Open, no key. Akoma Ntoso 3.0 (same family as CH).
# Fetch-by-id (no clean enumeration), so seed statute ids. Request /fin@ for clean Finnish text.
#   law text: GET /finlex/avoindata/v1/akn/fi/act/statute/{year}/{number}/fin@  (AKN; <docTitle>)
# --------------------------------------------------------------------------------------------------

FI_BASE = "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute"
FI_SEED_LAWS: list[dict] = [
    {"id": "2011/646", "en": "Waste Act (Jätelaki — framework)"},
    {"id": "2021/714", "en": "Act amending the Waste Act (EPR / single-use plastics)"},
    {"id": "2014/519", "en": "Government Decree on Waste Electrical and Electronic Equipment (WEEE)"},
    {"id": "2014/520", "en": "Government Decree on Batteries and Accumulators"},
    {"id": "2021/1029", "en": "Government Decree on Packaging and Packaging Waste (EPR)"},
    {"id": "2015/123", "en": "Government Decree on End-of-Life Vehicles"},
    {"id": "2021/771", "en": "Government Decree on Certain (single-use) Plastic Products"},
]
_FI_TITLE_RE = re.compile(r"<docTitle[^>]*>(.*?)</docTitle>", re.S)


class FinlandFinlexClient(ForeignSourceClient):
    """opendata.finlex.fi adapter. Finnish statutes, Akoma Ntoso XML, no key (curated seeds)."""

    region = "FI"
    source = "finlex"

    async def discover(self) -> list[tuple[str, str]]:
        log.info("fi_discovered", total=len(FI_SEED_LAWS))
        return [(s["id"], s["en"]) for s in FI_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{FI_BASE}/{source_id}/fin@")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("fi_fetch_failed", id=source_id, error=str(e))
            return None
        tm = _FI_TITLE_RE.search(r.text)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("fi_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=f"{FI_BASE}/{source_id}/fin@", english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Luxembourg — legilux / data.legilux.public.lu. Open, no key. SAME JOLux + Akoma Ntoso stack as CH
# Fedlex. The ELI is an RDF id (content-neg 404s); fetch the explicit /fr/xml manifestation. Seed the
# ELI expression paths (SPARQL title search also works). Archetype A. French only.
#   law text: GET http://data.legilux.public.lu/{eli}/xml   (Akoma Ntoso 3.0)
# --------------------------------------------------------------------------------------------------

LU_BASE = "http://data.legilux.public.lu"  # http:// on the data host (https manifestation 404s)
LU_SEED_LAWS: list[dict] = [
    {"eli": "eli/etat/leg/loi/2017/03/21/a330/jo/fr", "en": "Law on packaging and packaging waste"},
    {"eli": "eli/etat/leg/loi/2022/06/09/a266/jo/fr", "en": "Law on waste electrical and electronic equipment (WEEE)"},
    {"eli": "eli/etat/leg/loi/2022/06/09/a269/jo/fr", "en": "Law on single-use plastic products (SUP)"},
    {"eli": "eli/etat/leg/loi/1994/06/17/n4/jo/fr", "en": "Waste management framework law"},
    {"eli": "eli/etat/leg/rgd/2018/07/02/a562/jo/fr", "en": "Grand-ducal regulation on end-of-life vehicles"},
]
_LU_TITLE_RE = re.compile(r"<docTitle[^>]*>(.*?)</docTitle>", re.S)


class LuxembourgLegiluxClient(ForeignSourceClient):
    """legilux adapter. Luxembourg consolidated law, Akoma Ntoso XML (JOLux), no key (curated seeds)."""

    region = "LU"
    source = "legilux"

    async def discover(self) -> list[tuple[str, str]]:
        log.info("lu_discovered", total=len(LU_SEED_LAWS))
        return [(s["eli"], s["en"]) for s in LU_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{LU_BASE}/{source_id}/xml")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("lu_fetch_failed", eli=source_id, error=str(e))
            return None
        tm = _LU_TITLE_RE.search(r.text)
        title = _strip_tags(tm.group(1)) if tm else (english_label or source_id)
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("lu_thin_text", eli=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=f"https://legilux.public.lu/{source_id}", english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Estonia — Riigi Teataja public-api. Open, no key (the Angular site calls this REST API). Seed
# numeric akt ids; fetch the consolidated HTML (or /xml). Archetype A. English exists for headline
# acts under separate EN ids (we ingest Estonian; classifier is region-aware).
#   law text: GET /public-api/api/v1/akt/{id}/blob-html
# --------------------------------------------------------------------------------------------------

EE_BASE = "https://www.riigiteataja.ee/public-api/api/v1"
EE_PAGE = "https://www.riigiteataja.ee/akt/{id}"
EE_SEED_LAWS: list[dict] = [
    {"id": "749804", "en": "Waste Act (Jäätmeseadus — framework: WEEE, batteries, ELV, tyres)"},
    {"id": "113032019103", "en": "Packaging Act (Pakendiseadus)"},
    {"id": "918053", "en": "Packaging Excise Duty Act (Pakendiaktsiisi seadus — EPR fiscal instrument)"},
]


class EstoniaRiigiClient(ForeignSourceClient):
    """Riigi Teataja adapter. Estonian consolidated law via the public REST API, no key (seeds)."""

    region = "EE"
    source = "riigiteataja"

    async def discover(self) -> list[tuple[str, str]]:
        log.info("ee_discovered", total=len(EE_SEED_LAWS))
        return [(s["id"], s["en"]) for s in EE_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{EE_BASE}/akt/{source_id}/blob-html")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("ee_fetch_failed", id=source_id, error=str(e))
            return None
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("ee_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=EE_PAGE.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Latvia — likumi.lv. Open (robots allows /ta/id/, Crawl-delay 1). The JSON API is metadata-only, so
# scrape the server-rendered HTML full text (clean, UTF-8, no OCR). Seed ids; cut to the content div.
# Archetype C (no search API) but seed-fetchable like the A adapters.
#   law text: GET https://likumi.lv/ta/id/{id}   (HTML; body in div.doc / div.text)
# --------------------------------------------------------------------------------------------------

LV_BASE = "https://likumi.lv/ta/id"
LV_SEED_LAWS: list[dict] = [
    {"id": "221378", "en": "Waste Management Law (batteries/ELV/SUP/WEEE umbrella)"},
    {"id": "57207", "en": "Packaging Law"},
    {"id": "124707", "en": "Natural Resources Tax Law (packaging/EPR fiscal instrument)"},
    {"id": "267716", "en": "Waste Electrical and Electronic Equipment regulation"},
]


class LatviaLikumiClient(ForeignSourceClient):
    """likumi.lv adapter. Latvian consolidated law, server-rendered HTML, no key (curated seeds)."""

    region = "LV"
    source = "likumi"

    async def discover(self) -> list[tuple[str, str]]:
        log.info("lv_discovered", total=len(LV_SEED_LAWS))
        return [(s["id"], s["en"]) for s in LV_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{LV_BASE}/{source_id}")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("lv_fetch_failed", id=source_id, error=str(e))
            return None
        # Cut leading site nav: start at the law-body container.
        raw = r.text
        i = raw.find('class="doc"')
        if i == -1:
            i = raw.find('class="text"')
        full_text = _strip_tags(raw[i:] if i != -1 else raw)
        if len(full_text) < 100:
            log.warning("lv_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=f"{LV_BASE}/{source_id}", english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Slovakia — Slov-Lex. Open, no key. The site is a React SPA, but its <noscript> static full-text
# mirror serves consolidated HTML in a dated directory tree. Seed act ids; pick the newest version
# file ≤ today. Archetype A.
#   index:    GET static.slov-lex.sk/static/SK/ZZ/{year}/{num}/   (lists {YYYYMMDD}.html versions)
#   law text: GET static.slov-lex.sk/static/SK/ZZ/{year}/{num}/{YYYYMMDD}.html
# --------------------------------------------------------------------------------------------------

SK_BASE = "https://static.slov-lex.sk/static/SK/ZZ"
SK_PAGE = "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/{id}/"
SK_SEED_LAWS: list[dict] = [
    {"id": "2015/79", "en": "Waste Act (umbrella EPR: packaging, WEEE, batteries, ELV, tyres)"},
    {"id": "2015/373", "en": "Decree on Extended Producer Responsibility (core EPR implementing decree)"},
    {"id": "2015/366", "en": "Decree on EPR record-keeping and reporting obligations"},
    {"id": "2019/302", "en": "Deposit-return scheme for single-use beverage packaging"},
]
_SK_DATE_RE = re.compile(r"(\d{8})\.html")


class SlovakiaSlovLexClient(ForeignSourceClient):
    """Slov-Lex adapter. Slovak consolidated law via the static HTML mirror, no key (curated seeds)."""

    region = "SK"
    source = "slovlex"

    async def discover(self) -> list[tuple[str, str]]:
        log.info("sk_discovered", total=len(SK_SEED_LAWS))
        return [(s["id"], s["en"]) for s in SK_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        import datetime

        base = f"{SK_BASE}/{source_id}"
        try:
            idx = await self.http.get(f"{base}/")
            idx.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("sk_index_failed", id=source_id, error=str(e))
            return None
        today = datetime.date.today().strftime("%Y%m%d")
        dates = sorted(d for d in set(_SK_DATE_RE.findall(idx.text)) if d <= today)
        if not dates:
            log.warning("sk_no_version", id=source_id)
            return None
        try:
            doc = await self.http.get(f"{base}/{dates[-1]}.html")
            doc.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("sk_doc_failed", id=source_id, error=str(e))
            return None
        full_text = _strip_tags(doc.text)
        if len(full_text) < 100:
            log.warning("sk_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=SK_PAGE.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Lithuania — e-seimas.lrs.lt (Seimas legal acts register / TAR). Open, no key. The `/rs/legalact/`
# machine path returns the full document directly (the `/portal/` path is a JSF SPA; e-tar.lt 403s).
# Seed act ids (TAIS.* or 32-hex GUID). Archetype A. Browser UA required.
#   law text: GET /rs/legalact/TAD/{id}/   (HTML)
# --------------------------------------------------------------------------------------------------

LT_BASE = "https://e-seimas.lrs.lt/rs/legalact/TAD"
LT_PAGE = "https://e-seimas.lrs.lt/portal/legalAct/lt/TAD/{id}"
LT_SEED_LAWS: list[dict] = [
    {"id": "TAIS.59267", "en": "Law on Waste Management (framework, incl. EPR)"},
    {"id": "TAIS.161216", "en": "Law on Management of Packaging and Packaging Waste"},
    {"id": "TAIS.80721", "en": "Law on Pollution Tax (EPR fee instrument)"},
    {"id": "TAIS.325345", "en": "Producer-responsibility waste rules (WEEE / batteries / ELV)"},
]


class LithuaniaESeimasClient(ForeignSourceClient):
    """e-seimas.lrs.lt adapter. Lithuanian law via the /rs/ machine path, no key (curated seeds)."""

    region = "LT"
    source = "eseimas"

    async def discover(self) -> list[tuple[str, str]]:
        log.info("lt_discovered", total=len(LT_SEED_LAWS))
        return [(s["id"], s["en"]) for s in LT_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{LT_BASE}/{source_id}/")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("lt_fetch_failed", id=source_id, error=str(e))
            return None
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("lt_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=LT_PAGE.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Slovenia — PISRS / Uradni list. Open, no key. PISRS has a JSON filter API, but full text lives on
# the official journal uradni-list.si addressed by the `sop` id. Seed sop ids. Archetype A.
#   law text: GET uradni-list.si/glasilo-uradni-list-rs/vsebina/{sop}   (HTML)
# --------------------------------------------------------------------------------------------------

SI_BASE = "https://www.uradni-list.si/glasilo-uradni-list-rs/vsebina"
SI_SEED_LAWS: list[dict] = [
    {"id": "2021-01-1053", "en": "Decree on packaging and packaging waste"},
    {"id": "2015-01-1513", "en": "Decree on waste (framework)"},
    {"id": "2010-01-0111", "en": "Decree on batteries and accumulators"},
    {"id": "2024-01-2498", "en": "Decree implementing the EU Batteries Regulation"},
    {"id": "2021-01-2724", "en": "Decree banning certain single-use plastic products"},
]


class SloveniaUradniClient(ForeignSourceClient):
    """Uradni list adapter. Slovenian consolidated law by sop id, no key (curated seeds)."""

    region = "SI"
    source = "uradnilist"

    async def discover(self) -> list[tuple[str, str]]:
        log.info("si_discovered", total=len(SI_SEED_LAWS))
        return [(s["id"], s["en"]) for s in SI_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{SI_BASE}/{source_id}")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("si_fetch_failed", id=source_id, error=str(e))
            return None
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("si_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=f"{SI_BASE}/{source_id}", english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Czechia — e-Sbírka open data (Virtuoso SPARQL). Open, no key. The act's latest consolidated text is
# assembled from text-fragments. Quirks: send a NON-browser UA (Mozilla → HTTP 500) and the vocab
# IRI carries literal Czech accents. Archetype A.
#   law text: POST opendata.eselpoint.gov.cz/sparql (fragments of má-poslední-znění) -> concat ?txt
# --------------------------------------------------------------------------------------------------

CZ_SPARQL = "https://opendata.eselpoint.gov.cz/sparql"
CZ_PAGE = "https://www.e-sbirka.cz/sb/{year}/{num}"
CZ_SEED_LAWS: list[dict] = [
    {"id": "2001/477", "en": "Packaging Act (zákon o obalech)"},
    {"id": "2020/541", "en": "Waste Act (zákon o odpadech)"},
    {"id": "2020/542", "en": "End-of-Life Products Act — WEEE, batteries, ELV, tyres"},
]
# Latest-consolidated full text: the version path on the fragment URLs drops the "/cz" segment that
# the version IRI carries, so strip through "/eli/cz" to build the "/sb/{year}/{num}/{date}" prefix.
_CZ_QUERY = (
    "PREFIX s: <https://slovník.gov.cz/datový/sbírka/pojem/> "
    "SELECT ?u ?txt WHERE {{ "
    "<https://opendata.eselpoint.gov.cz/esel-esb/eli/cz/sb/{year}/{num}> s:má-poslední-znění ?v . "
    'BIND(REPLACE(STR(?v),"^.*/eli/cz","") AS ?vp) '
    "?frag s:url-fragmentu-znění ?u . "
    "?frag s:obsahuje-fragment ?obs . ?obs s:text-fragmentu ?txt . "
    "FILTER(STRSTARTS(STR(?u), ?vp)) }} ORDER BY ?u"
)


class CzechiaESbirkaClient(ForeignSourceClient):
    """e-Sbírka adapter. Czech consolidated law assembled via SPARQL text-fragments, no key (seeds)."""

    region = "CZ"
    source = "esbirka"
    _HDR = {"User-Agent": "curl/8.0", "Accept": "application/sparql-results+json"}

    async def discover(self) -> list[tuple[str, str]]:
        log.info("cz_discovered", total=len(CZ_SEED_LAWS))
        return [(s["id"], s["en"]) for s in CZ_SEED_LAWS]

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        year, num = source_id.split("/")
        try:
            r = await self.http.post(
                CZ_SPARQL, data={"query": _CZ_QUERY.format(year=year, num=num)}, headers=self._HDR
            )
            r.raise_for_status()
            bindings = r.json()["results"]["bindings"]
        except (httpx.HTTPError, ValueError) as e:
            log.warning("cz_fetch_failed", id=source_id, error=str(e))
            return None
        if not bindings:
            log.warning("cz_no_fragments", id=source_id)
            return None
        full_text = _strip_tags("\n".join(b["txt"]["value"] for b in bindings))
        if len(full_text) < 100:
            log.warning("cz_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=CZ_PAGE.format(year=year, num=num), english_label=english_label,
        )


# ==================================================================================================
# China (PRC) — 国家法律法规数据库 flk.npc.gov.cn (National Laws & Regulations Database, official).
# Grade A-: no auth, no captcha on the read path, no US geo-block, no UA requirement (verified live
# 2026-07-03). The site is a Vue SPA rebuilt ~2025 — all pre-2025 scraping prior art is dead; the
# endpoints below were reverse-engineered from the current JS bundle + confirmed end-to-end:
#   discover: POST /law-search/search/list  {searchContent, searchRange:1, searchType:1, pageNum, pageSize}
#             -> {total, rows:[{bbbs, title(<em>-highlighted), sxx(status), gbrq, sxrq, flxz, ...}]}
#             (omit orderByParam entirely — an empty string 500s on the server's Jackson coercion)
#   detail:   GET  /law-search/search/flfgDetails?bbbs=<id>  -> {data:{bbbs, ossFile, lsyg:[{title,...}]}}
#             (lsyg[0].title = clean current title + amendment lineage; the body text is NOT here)
#   docx url: GET  /law-search/download/pc?format=docx&bbbs=<id>&fileId=  -> {data:{url:<presigned OBS>}}
#             (use data.url — the public https://flkoss.obs-bj2.cucloud.cn/... link; data.urlIn is an
#              internal 172.16.x address. Presigned ~1h expiry: fetch immediately.)
# Body text is available ONLY as the Word download -> docx_to_text(). PRC Copyright Law art.5(1)
# excludes laws/regulations from copyright, so commercial reuse is clear; Chinese full text is fine
# (region-aware classifier, JP precedent). Risk: the site was rebuilt once already, killing all prior
# scrapers — keep <=1 rps and treat any non-JSON response as a backoff/alarm signal.
# ==================================================================================================

CN_FLK_BASE = "https://flk.npc.gov.cn/law-search"
CN_FLK_PAGE = "https://flk.npc.gov.cn/detail2.html?{bbbs}"  # human SPA deep-link (best-effort)

# Curated marquee CE/EPR statutes, keyed by bbbs (verified present 2026-07-03). Guarantees inclusion
# + carries an English label regardless of search drift; the classifier still assigns instrument/material.
CN_SEED_LAWS: list[dict] = [
    {"bbbs": "ff808081729c65d801729d455fad04be",
     "en": "Law on the Prevention & Control of Environmental Pollution by Solid Waste (2020 rev — EPR mandate)"},
    {"bbbs": "ff8080816f135f46016f1d06082912c2",
     "en": "Circular Economy Promotion Law (2018 rev)"},
    {"bbbs": "2c909fdd678bf17901678bf737800631",
     "en": "Cleaner Production Promotion Law"},
    {"bbbs": "ff8080816f3e9784016f424f1b4a04d9",
     "en": "Regulations on the Recycling & Disposal of Waste Electrical & Electronic Products (WEEE)"},
]

# Chinese CE/EPR search phrases — the CN analog of the EUR-Lex EuroVoc / FR discovery terms. Precise
# search (searchType:1) keeps the hit list tight; the Haiku confidence floor judges true relevance.
CN_DISCOVERY_TERMS = [
    "循环经济",        # circular economy
    "生产者责任延伸",   # extended producer responsibility
    "固体废物",        # solid waste
    "再生资源",        # recycled/renewable resources
    "清洁生产",        # cleaner production
    "包装",           # packaging
    "电器电子产品",     # electrical & electronic products
    "塑料污染",        # plastic pollution
]

# flk `sxx` status codes (inferred from data): 3=in force, 2=superseded by amendment, 4=adopted
# not-yet-effective, 1=repealed/expired. Ingest 3 + 4 (current + upcoming); skip 1/2 in discovery.
_CN_STATUS = {3: "enacted", 4: "adopted", 2: "superseded", 1: "repealed"}

_CN_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def cn_date(raw: str | None) -> "datetime.date | None":
    """Parse a flk date string (公布日期 gbrq / 施行日期 sxrq), format 'YYYY-MM-DD', into a date."""
    m = _CN_ISO_DATE_RE.match((raw or "").strip())
    if not m:
        return None
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


class ChinaFlkClient(ForeignSourceClient):
    """flk.npc.gov.cn adapter. PRC national laws + State Council/provincial regs; body via DOCX."""

    region = "CN"
    source = "flk"

    def __init__(self, timeout: float = 60.0):
        super().__init__(timeout)
        # bbbs -> {"title", "status"} captured in discover() so fetch() avoids a re-search.
        self._meta: dict[str, dict] = {}

    async def discover(self) -> list[tuple[str, str]]:
        out: dict[str, str] = {seed["bbbs"]: seed["en"] for seed in CN_SEED_LAWS}
        for term in CN_DISCOVERY_TERMS:
            body = {"searchContent": term, "searchRange": 1, "searchType": 1,
                    "pageNum": 1, "pageSize": 20}
            try:
                resp = await self.http.post(f"{CN_FLK_BASE}/search/list", json=body)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                log.warning("cn_search_failed", term=term, error=str(e))
                continue
            for row in data.get("rows", []):
                bbbs = row.get("bbbs")
                if not bbbs or row.get("sxx") in (1, 2):  # skip repealed / superseded editions
                    continue
                self._meta[bbbs] = {
                    "title": _strip_tags(row.get("title", "")),  # drop the <em> highlight tags
                    "status": _CN_STATUS.get(row.get("sxx"), "enacted"),
                    "gbrq": row.get("gbrq"),  # 公布日期 (promulgation date) — the real status_date
                }
                out.setdefault(bbbs, "")
        log.info("cn_discovered", total=len(out), seeded=sum(1 for v in out.values() if v))
        return list(out.items())

    async def _details(self, bbbs: str) -> dict:
        """flfgDetails -> the `data` object (clean title via lsyg[0], ossFile paths, lineage)."""
        try:
            r = await self.http.get(f"{CN_FLK_BASE}/search/flfgDetails", params={"bbbs": bbbs})
            r.raise_for_status()
            return r.json().get("data") or {}
        except (httpx.HTTPError, ValueError) as e:
            log.warning("cn_details_failed", bbbs=bbbs, error=str(e))
            return {}

    async def _docx_url(self, bbbs: str) -> str | None:
        """download/pc -> the public presigned OBS url (data.url, NOT the internal data.urlIn)."""
        try:
            r = await self.http.get(f"{CN_FLK_BASE}/download/pc",
                                    params={"format": "docx", "bbbs": bbbs, "fileId": ""})
            r.raise_for_status()
            return (r.json().get("data") or {}).get("url")
        except (httpx.HTTPError, ValueError) as e:
            log.warning("cn_docx_url_failed", bbbs=bbbs, error=str(e))
            return None

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        meta = self._meta.get(source_id, {})
        title = meta.get("title", "")
        status = meta.get("status", "enacted")
        gbrq = meta.get("gbrq")
        if not title or not gbrq:  # a seed not seen in a search — resolve title/date from flfgDetails
            det = await self._details(source_id)
            lsyg = det.get("lsyg") or []
            if not title and lsyg:
                title = _strip_tags(lsyg[0].get("title", ""))
            if not gbrq:  # top-level gbrq, else the earliest lineage entry's
                gbrq = det.get("gbrq") or (lsyg[0].get("gbrq") if lsyg else None)
        url = await self._docx_url(source_id)
        if not url:
            return None
        try:
            r = await self.http.get(url)  # presigned OBS link, fetch immediately (~1h expiry)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("cn_docx_fetch_failed", bbbs=source_id, error=str(e))
            return None
        full_text = docx_to_text(r.content)
        if len(full_text) < 100:
            log.warning("cn_thin_text", bbbs=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=title or english_label or source_id, full_text=full_text,
            source_url=CN_FLK_PAGE.format(bbbs=source_id), english_label=english_label, status=status,
            status_date=cn_date(gbrq),  # real 公布日期 (promulgation date) from flk
        )


# --------------------------------------------------------------------------------------------------
# China State Council policy library — www.gov.cn. Server-rendered UTF-8 HTML (body in
# <div id="UCAP-CONTENT">) + a JSON title-search at sousuo.www.gov.cn. Covers the State Council /
# ministry INSTRUMENTS that flk omits (国发/国办发 opinions & plans — e.g. the 2016 EPR implementation
# plan). Verified live 2026-07-03. region="CN", source="govcn".
# --------------------------------------------------------------------------------------------------

CN_GOV_SEARCH = "https://sousuo.www.gov.cn/search-gov/data"
CN_GOV_SEED: list[dict] = [
    {"url": "https://www.gov.cn/zhengce/content/2017-01/03/content_5156043.htm",
     "en": "Extended Producer Responsibility (EPR) Implementation Plan (国办发〔2016〕99号)"},
]
CN_GOV_TERMS = ["生产者责任延伸", "循环经济", "塑料污染治理", "再生资源回收"]
_CN_GOV_URL_RE = re.compile(r'"url"\s*:\s*"(https?:[^"]*?gov\.cn/[^"]*?content_\d+\.htm)"')
_CN_GOV_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
# Trim the trailing site chrome that follows the article body on gov.cn content pages.
_CN_GOV_FOOTER_RE = re.compile(r"责任编辑|扫一扫在手机|【我要纠错】|相关稿件|分享到")


class ChinaGovCnClient(ForeignSourceClient):
    """www.gov.cn State Council policy-library adapter (opinions / plans / implementation measures)."""

    region = "CN"
    source = "govcn"

    @staticmethod
    def _path(url: str) -> str:
        return url.split("gov.cn/", 1)[-1]

    async def discover(self) -> list[tuple[str, str]]:
        out: dict[str, str] = {self._path(s["url"]): s["en"] for s in CN_GOV_SEED}
        for term in CN_GOV_TERMS:
            params = {"t": "zhengcelibrary_gw", "q": term, "searchfield": "title",
                      "type": "gwyzcwjk", "p": 1, "n": 10}
            try:
                r = await self.http.get(CN_GOV_SEARCH, params=params,
                                        headers={"Referer": "https://sousuo.www.gov.cn/"})
                r.raise_for_status()
                payload = r.text
            except httpx.HTTPError as e:
                log.warning("cn_gov_search_failed", term=term, error=str(e))
                continue
            for m in _CN_GOV_URL_RE.finditer(payload):
                out.setdefault(self._path(m.group(1).replace("\\/", "/")), "")
        log.info("cn_gov_discovered", total=len(out))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        url = source_id if source_id.startswith("http") else f"https://www.gov.cn/{source_id}"
        try:
            r = await self.http.get(url)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("cn_gov_fetch_failed", url=url, error=str(e))
            return None
        raw = r.text
        tm = _CN_GOV_TITLE_RE.search(raw)
        title = _strip_tags(tm.group(1)).split("_")[0].strip() if tm else (english_label or source_id)
        idx = raw.find('id="UCAP-CONTENT"')
        body = raw[idx:] if idx != -1 else raw
        body = _CN_GOV_FOOTER_RE.split(body)[0]
        full_text = _strip_tags(body)
        if len(full_text) < 100:
            log.warning("cn_gov_thin_text", url=url, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=title, full_text=full_text, source_url=url, english_label=english_label,
        )


# ==================================================================================================
# Canada — federal + provinces (EPR is largely provincial; see docs/FEDERATED_EXPANSION_PLAN.md).
# All region="CA"; the province is carried in `source` (the UK-devolved precedent), so foreign_id
# stays unique as CA:<source>:<id> while the row's region/state is "CA".
# --------------------------------------------------------------------------------------------------
# Federal: Justice Laws (laws-lois.justice.gc.ca). Grade A — per-doc structured XML + a full catalog.
#   discover: GET /eng/XML/Legis.xml  -> repeating <UniqueId>/<LinkToXML>/<Title> blocks (EN + FR
#             interleaved; keep the /eng/ block). fetch: GET /eng/XML/<id>.xml -> <Statute> | <Regulation>
#             root (regulation XML carries a UTF-8 BOM). Licence: Reproduction of Federal Law Order
#             SI/97-5 — commercial reuse permitted.
# ==================================================================================================

CA_JUSTICE_BASE = "https://laws-lois.justice.gc.ca/eng/XML"
CA_JUSTICE_PAGE = "https://laws-lois.justice.gc.ca/eng/{kind}/{id}/"
CA_FED_SEED: list[dict] = [
    {"id": "C-15.31", "en": "Canadian Environmental Protection Act, 1999 (CEPA)"},
    {"id": "SOR-2022-138", "en": "Single-use Plastics Prohibition Regulations"},
    {"id": "SOR-2021-25", "en": "Cross-border Movement of Hazardous Waste and Hazardous Recyclable Material Regs"},
]
# EPR / circular-economy title keywords for scanning the federal catalog (English titles).
CA_FED_KEYWORDS = re.compile(
    r"(recycl|\bwaste\b|plastic|packaging|hazardous|stewardship|environmental protection|"
    r"deposit|single-use|end-of-life|circular economy)", re.I
)


class CanadaJusticeClient(ForeignSourceClient):
    """Justice Laws federal adapter. Enacted Canadian federal Acts + Regulations, structured XML."""

    region = "CA"
    source = "justice"

    def __init__(self, timeout: float = 60.0):
        super().__init__(timeout)

    async def discover(self) -> list[tuple[str, str]]:
        out: dict[str, str] = {seed["id"]: seed["en"] for seed in CA_FED_SEED}
        try:
            r = await self.http.get(f"{CA_JUSTICE_BASE}/Legis.xml")
            r.raise_for_status()
            catalog = r.text
        except httpx.HTTPError as e:
            log.warning("ca_fed_catalog_failed", error=str(e))
            return list(out.items())
        # Each <UniqueId>…</UniqueId> block holds this entry's own LinkToXML + Title; the EN + FR
        # mirrors are separate blocks with the same id (the FR LinkToXML points at /fra/XML/).
        for chunk in catalog.split("<UniqueId>")[1:]:
            uid = chunk[: chunk.find("</UniqueId>")].strip()
            if not uid or uid in out:
                continue
            link_m = re.search(r"<LinkToXML>([^<]+)</LinkToXML>", chunk)
            title_m = re.search(r"<Title>([^<]+)</Title>", chunk)
            if not link_m or not title_m or "/eng/XML/" not in link_m.group(1):
                continue  # skip the FR mirror block (and malformed rows)
            if CA_FED_KEYWORDS.search(title_m.group(1)):
                out.setdefault(uid, "")
        log.info("ca_fed_discovered", total=len(out), seeded=sum(1 for v in out.values() if v))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(f"{CA_JUSTICE_BASE}/{source_id}.xml")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("ca_fed_fetch_failed", id=source_id, error=str(e))
            return None
        raw = r.text.lstrip("﻿")  # regulation XML carries a UTF-8 BOM
        is_reg = "<Regulation" in raw[:400]
        title_m = re.search(r"<(LongTitle|ShortTitle)\b[^>]*>(.*?)</\1>", raw, re.S)
        title = _strip_tags(title_m.group(2)) if title_m else (english_label or source_id)
        full_text = _strip_tags(raw)
        if len(full_text) < 100:
            log.warning("ca_fed_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, english_label=english_label,
            source_url=CA_JUSTICE_PAGE.format(kind="regulations" if is_reg else "acts", id=source_id),
        )


# --------------------------------------------------------------------------------------------------
# British Columbia: BC Laws CiviX. Grade A — append /xml to a document id for structured XML.
#   fetch:    GET /civix/document/id/complete/statreg/<id>/xml   (single-file reg/act part)
#   discover: GET /civix/search/complete/fullsearch?q=<term>&s=0&e=N -> <doc><CIVIX_DOCUMENT_ID>/<..TITLE>
#             (default search is OR + very broad, so keep only hits whose TITLE looks EPR-relevant).
# Multi-part acts expose <id>_00 as an HTML TOC with parts at <id>_01.._NN; we seed the single-file
# regs (BC's core EPR levers) — multi-part act assembly is a later enhancement. Licence: BC Crown
# (Queen's Printer) licence — commercial use permitted.
# --------------------------------------------------------------------------------------------------

CA_BC_BASE = "https://www.bclaws.gov.bc.ca/civix"
CA_BC_DOC = CA_BC_BASE + "/document/id/complete/statreg/{id}"
CA_BC_SEED: list[dict] = [
    {"id": "449_2004", "en": "Recycling Regulation (B.C. Reg. 449/2004) — BC's core EPR regulation"},
]
CA_BC_TERMS = ["recycling regulation", "extended producer responsibility", "product stewardship"]
_BC_DOC_ID_RE = re.compile(r"<CIVIX_DOCUMENT_ID>([^<]+)</CIVIX_DOCUMENT_ID>")
_BC_DOC_TITLE_RE = re.compile(r"<CIVIX_DOCUMENT_TITLE>([^<]+)</CIVIX_DOCUMENT_TITLE>")
_BC_RELEVANT = re.compile(
    r"(recycl|stewardship|producer responsibilit|deposit|packaging|beverage container|circular)", re.I
)
_BC_TITLE_RE = re.compile(r"<bcl:title\b[^>]*>(.*?)</bcl:title>", re.S | re.I)


class CanadaBcLawsClient(ForeignSourceClient):
    """BC Laws CiviX adapter. British Columbia statutes/regulations, structured XML."""

    region = "CA"
    source = "bclaws"

    def __init__(self, timeout: float = 45.0):
        super().__init__(timeout)
        self._titles: dict[str, str] = {}

    async def discover(self) -> list[tuple[str, str]]:
        out: dict[str, str] = {seed["id"]: seed["en"] for seed in CA_BC_SEED}
        for term in CA_BC_TERMS:
            params = {"q": term, "s": 0, "e": 25, "nFrag": 1, "lFrag": 80}
            try:
                r = await self.http.get(f"{CA_BC_BASE}/search/complete/fullsearch", params=params)
                r.raise_for_status()
                payload = r.text
            except httpx.HTTPError as e:
                log.warning("ca_bc_search_failed", term=term, error=str(e))
                continue
            for block in re.split(r"<doc\b", payload)[1:]:
                idm = _BC_DOC_ID_RE.search(block)
                tm = _BC_DOC_TITLE_RE.search(block)
                if not idm or not tm:
                    continue
                title = tm.group(1).strip()
                if not _BC_RELEVANT.search(title):  # tighten the broad OR search to EPR-ish titles
                    continue
                doc_id = idm.group(1).strip()
                self._titles[doc_id] = title
                out.setdefault(doc_id, "")
        log.info("ca_bc_discovered", total=len(out))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        if source_id.endswith("_00"):  # multi-part act root returns an HTML TOC, not statute XML
            log.info("ca_bc_skip_toc", id=source_id)
            return None
        try:
            r = await self.http.get(f"{CA_BC_DOC.format(id=source_id)}/xml")
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("ca_bc_fetch_failed", id=source_id, error=str(e))
            return None
        raw = r.text
        tm = _BC_TITLE_RE.search(raw)
        title = (_strip_tags(tm.group(1)) if tm
                 else self._titles.get(source_id) or english_label or source_id)
        full_text = _strip_tags(raw)
        if len(full_text) < 100:
            log.warning("ca_bc_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, source_url=CA_BC_DOC.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# Ontario: e-Laws. The public pages (ontario.ca/laws/…) are a React SPA — DO NOT crawl them. The SPA
# is backed by an open, no-auth JSON API (reverse-engineered + verified live 2026-07-03):
#   fetch:    GET /laws/api/v2/legislation/en/doc-search/<type>/<code>
#             -> {volume, content:<consolidated HTML string, Word-derived markup>}
# We seed the enacted Ontario EPR statutes/regs (ids confirmed against the API; regulation code =
# yy + zero-padded reg number). Autocomplete-based discovery (/laws/api/v2/laws/autocomplete) is a
# later enhancement. source_id = "<type>/<code>". Licence: King's Printer for Ontario permits
# reproduction of statutes/regulations without permission. Risk: undocumented API — pin a health check.
# --------------------------------------------------------------------------------------------------

CA_ON_BASE = "https://www.ontario.ca/laws"
CA_ON_API = CA_ON_BASE + "/api/v2/legislation/en/doc-search/{type}/{code}"
CA_ON_PAGE = CA_ON_BASE + "/{type}/{code}"
CA_ON_SEED: list[dict] = [
    {"type": "statute", "code": "16r12", "en": "Resource Recovery and Circular Economy Act, 2016 (RRCEA)"},
    {"type": "regulation", "code": "210391", "en": "O. Reg. 391/21 — Blue Box (packaging EPR)"},
    {"type": "regulation", "code": "200522", "en": "O. Reg. 522/20 — Batteries (EPR)"},
    {"type": "regulation", "code": "200542", "en": "O. Reg. 542/20 — Electrical & Electronic Equipment (EPR)"},
    {"type": "regulation", "code": "210449", "en": "O. Reg. 449/21 — Hazardous & Special Products (EPR)"},
]


class CanadaOntarioClient(ForeignSourceClient):
    """Ontario e-Laws adapter over the SPA's backing JSON API (undocumented, no auth)."""

    region = "CA"
    source = "elaws"

    async def discover(self) -> list[tuple[str, str]]:
        out = {f"{s['type']}/{s['code']}": s["en"] for s in CA_ON_SEED}
        log.info("ca_on_discovered", total=len(out))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            doc_type, code = source_id.split("/", 1)
        except ValueError:
            return None
        try:
            r = await self.http.get(CA_ON_API.format(type=doc_type, code=code))
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("ca_on_fetch_failed", id=source_id, error=str(e))
            return None
        full_text = _strip_tags(data.get("content") or "")
        if len(full_text) < 100:
            log.warning("ca_on_thin_text", id=source_id, chars=len(full_text))
            return None
        title = english_label or _strip_tags(data.get("volume", "")) or source_id
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source, title=title,
            full_text=full_text, english_label=english_label,
            source_url=CA_ON_PAGE.format(type=doc_type, code=code),
        )


# ==================================================================================================
# Australia — federal + states (EPR/container-deposit is largely state-level). region="AU"; the
# jurisdiction is carried in `source`. See docs/FEDERATED_EXPANSION_PLAN.md.
# --------------------------------------------------------------------------------------------------
# Federal: Register of Legislation. Grade A — OData v4 API (no auth); text via the website text view.
#   discover: GET /v1/titles?$filter=contains(name,'<term>')&$select=id,name,collection,status,isInForce
#   fetch:    GET https://www.legislation.gov.au/<id>/latest/text  (server HTML; the OData text stream
#             is broken). Licence: CC BY 4.0.
# --------------------------------------------------------------------------------------------------

AU_FED_API = "https://api.prod.legislation.gov.au/v1/titles"
AU_FED_TEXT = "https://www.legislation.gov.au/{id}/latest/text"
AU_FED_TERMS = ["Recycling and Waste Reduction", "Product Stewardship", "Packaging", "Hazardous Waste"]


class AustraliaFederalClient(ForeignSourceClient):
    """Federal Register of Legislation adapter (OData discovery + website text-view fetch)."""

    region = "AU"
    source = "legislation"

    async def discover(self) -> list[tuple[str, str]]:
        out: dict[str, str] = {}
        for term in AU_FED_TERMS:
            params = {"$filter": f"contains(name,'{term}')",
                      "$select": "id,name,collection,status,isInForce"}
            try:
                r = await self.http.get(AU_FED_API, params=params)
                r.raise_for_status()
                data = r.json()
            except (httpx.HTTPError, ValueError) as e:
                log.warning("au_fed_search_failed", term=term, error=str(e))
                continue
            for row in data.get("value", []):
                if row.get("collection") not in ("Act", "LegislativeInstrument"):
                    continue  # skip Gazette notices / other collections
                if row.get("isInForce") is False:
                    continue
                rid = row.get("id")
                if rid:
                    out.setdefault(rid, row.get("name", ""))
        log.info("au_fed_discovered", total=len(out))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        try:
            r = await self.http.get(AU_FED_TEXT.format(id=source_id))
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("au_fed_fetch_failed", id=source_id, error=str(e))
            return None
        full_text = _strip_tags(r.text)
        if len(full_text) < 100:
            log.warning("au_fed_thin_text", id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=AU_FED_TEXT.format(id=source_id), english_label=english_label,
        )


# --------------------------------------------------------------------------------------------------
# NSW / QLD / TAS share one platform + URL grammar ("EnAct"):
#   https://www.<host>/view/whole/<fmt>/inforce/current/act-YYYY-NNN
# QLD + TAS serve official consolidated XML (fmt="xml"); NSW is HTML-only (fmt="html") and REQUIRES a
# browser UA (403 without — the base client already sends one). Seeded with each state's CDS/EPR acts;
# A-Z browse discovery is a later enhancement. Licence: CC BY 4.0 in all three.
# --------------------------------------------------------------------------------------------------

# A fuller, realistic browser Accept set + gzip/deflate (NOT br — brotli 520s) for the EnAct hosts;
# harmless for QLD/TAS which serve XML fine without it.
_ENACT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


async def impersonate_get(url: str, timeout: float = 45.0) -> str | None:
    """Fetch a URL through a browser-impersonating TLS stack (curl_cffi) to clear Cloudflare bot
    management that fingerprints the TLS ClientHello — headers/HTTP2/host tricks don't help because the
    block is at the handshake (system curl passes, plain httpx gets a hard 403). Used by NSW; the same
    escape hatch fits any future Cloudflare-fronted portal (e.g. SA's flaky WAF). Returns text or None."""
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        log.warning("curl_cffi_missing", hint="pip install curl_cffi to fetch Cloudflare-fronted hosts")
        return None
    # Cloudflare 52x (520/522/524…) are transient origin/edge errors, not blocks — retry a couple times.
    for attempt in range(3):
        try:
            async with AsyncSession() as s:
                r = await s.get(url, impersonate="chrome", timeout=timeout)
        except Exception as e:  # curl_cffi raises its own (non-httpx) error hierarchy
            log.warning("impersonate_get_failed", url=url, error=str(e), attempt=attempt)
            continue
        if r.status_code == 200:
            return r.text
        if not (520 <= r.status_code <= 529):
            log.warning("impersonate_get_status", url=url, status=r.status_code)
            return None
        log.info("impersonate_get_retry", url=url, status=r.status_code, attempt=attempt)
    return None


class AustraliaEnActClient(ForeignSourceClient):
    """Shared base for the NSW/QLD/TAS 'view/whole' platform. Subclass sets host, source, fmt, seeds."""

    region = "AU"
    host: str = ""            # e.g. "legislation.qld.gov.au"
    fmt: str = "xml"          # "xml" (QLD/TAS) or "html" (NSW)
    seeds: list[dict] = []    # [{"id": "act-2011-031", "en": "…"}]
    impersonate: bool = False  # True for Cloudflare-fronted hosts (NSW) — fetch via curl_cffi

    def _doc_url(self, source_id: str) -> str:
        return f"https://www.{self.host}/view/whole/{self.fmt}/inforce/current/{source_id}"

    async def discover(self) -> list[tuple[str, str]]:
        out = {s["id"]: s["en"] for s in self.seeds}
        log.info("au_enact_discovered", source=self.source, total=len(out))
        return list(out.items())

    async def fetch(self, source_id: str, english_label: str = "") -> ForeignLaw | None:
        url = self._doc_url(source_id)
        if self.impersonate:
            raw = await impersonate_get(url, self._timeout)
            if raw is None:
                log.warning("au_enact_fetch_failed", source=self.source, id=source_id, error="impersonate")
                return None
        else:
            try:
                r = await self.http.get(url, headers=_ENACT_HEADERS)
                r.raise_for_status()
                raw = r.text
            except httpx.HTTPError as e:
                log.warning("au_enact_fetch_failed", source=self.source, id=source_id, error=str(e))
                return None
        full_text = _strip_tags(raw)
        if len(full_text) < 100:
            log.warning("au_enact_thin_text", source=self.source, id=source_id, chars=len(full_text))
            return None
        return ForeignLaw(
            source_id=source_id, region=self.region, source=self.source,
            title=english_label or source_id, full_text=full_text,
            source_url=self._doc_url(source_id), english_label=english_label,
        )


class AustraliaNswClient(AustraliaEnActClient):
    source = "nsw"
    host = "legislation.nsw.gov.au"
    fmt = "html"  # NSW XML export is a JS form; whole/html is the fetchable full text
    impersonate = True  # Cloudflare TLS-fingerprint challenge — fetch via curl_cffi
    seeds = [
        {"id": "act-2001-058", "en": "Waste Avoidance and Resource Recovery Act 2001 (NSW — container deposit)"},
        {"id": "act-2021-031", "en": "Plastic Reduction and Circular Economy Act 2021 (NSW)"},
    ]


class AustraliaQldClient(AustraliaEnActClient):
    source = "qld"
    host = "legislation.qld.gov.au"
    fmt = "xml"
    seeds = [
        {"id": "act-2011-031",
         "en": "Waste Reduction and Recycling Act 2011 (QLD — container refund + plastics bans)"},
    ]


class AustraliaTasClient(AustraliaEnActClient):
    source = "tas"
    host = "legislation.tas.gov.au"
    fmt = "xml"
    seeds = [
        {"id": "act-2022-005", "en": "Container Refund Scheme Act 2022 (TAS)"},
    ]


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
    "PL": PolandEliClient,
    "KR": KoreaLawGoKrClient,
    "ZA": LawsAfricaZAClient,
    "KE": LawsAfricaKEClient,
    "DK": DenmarkRetsinfoClient,
    "FI": FinlandFinlexClient,
    "LU": LuxembourgLegiluxClient,
    "EE": EstoniaRiigiClient,
    "LV": LatviaLikumiClient,
    "SK": SlovakiaSlovLexClient,
    "LT": LithuaniaESeimasClient,
    "SI": SloveniaUradniClient,
    "CZ": CzechiaESbirkaClient,
    # China (region="CN"): national DB + State Council policy library.
    "CN": ChinaFlkClient,
    "CN_GOV": ChinaGovCnClient,
    # Canada (region="CA"): federal + provinces (province carried in `source`).
    "CA": CanadaJusticeClient,
    "CA_BC": CanadaBcLawsClient,
    "CA_ON": CanadaOntarioClient,
    # Australia (region="AU"): federal + states (state carried in `source`).
    "AU": AustraliaFederalClient,
    "AU_NSW": AustraliaNswClient,
    "AU_QLD": AustraliaQldClient,
    "AU_TAS": AustraliaTasClient,
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
                # Year-only enactment date (Jan 1) derived from the id/title, unless the adapter set a
                # precise one — so foreign law is no longer dateless on the year charts. `or` guards an
                # already-set date from being cleared when a re-run can't re-derive (JP/CN residual).
                bill.status_date = law.resolved_status_date or bill.status_date
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

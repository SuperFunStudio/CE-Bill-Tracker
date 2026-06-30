"""EUR-Lex / CELLAR ingestion — EU-central circular-economy law (the EU lean spike).

EU law is free and machine-readable through the Publications Office's CELLAR repository. We use
two access paths (see plan serene-munching-brook / the deep-research findings):

  1. A curated SEED list of CELEX ids for the core EPR / circular-economy instruments (PPWR, WEEE,
     Batteries Regulation, SUP, Packaging Directive, ELV, Waste Framework, ESPR). This guarantees
     the spike surfaces the acts that matter on day one, independent of discovery.
  2. Best-effort discovery via the public CELLAR SPARQL endpoint, filtered by EuroVoc subject
     labels (packaging, waste, recycling, producer responsibility, batteries, …).

For each CELEX we fetch the English HTML rendering of the act and strip it to plain text. The act's
official title is long and descriptive (e.g. "Regulation (EU) 2023/1542 … concerning batteries and
waste batteries"), which gives the existing Haiku classifier strong signal with no EU-specific
tuning beyond the region-aware prompt.

This client is deliberately standalone — it is NOT wired into the US IngestionCoordinator loop. The
driver is scripts/ingest_eurlex.py. The pluggable multi-source refactor is deferred.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()

# Public CELLAR SPARQL endpoint (verified live in the research pass). HTTP per the official docs.
SPARQL_ENDPOINT = "http://publications.europa.eu/webapi/rdf/sparql"
# Human-facing EUR-Lex page for an act (used as source_url).
EURLEX_PAGE = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
# Server-rendered English HTML of the act body (no JS shell), for full-text extraction.
EURLEX_HTML = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
# PDF original — fallback for acts EUR-Lex has no HTML rendering for (mostly older or annex-heavy acts).
EURLEX_PDF = "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:{celex}"
# Below this many chars the HTML body is treated as missing → try the PDF.
_MIN_BODY_CHARS = 400

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

_SCRIPT_STYLE_RE = re.compile(r"<(script|style|head)\b[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t ]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")
# The act's official title block in the body starts with the act type and runs until the enacting
# clause ("THE EUROPEAN PARLIAMENT…", "Having regard…"). The HTML <title> tag is only the OJ
# filename (e.g. "L_2023191EN.01000101.xml"), so we extract the title from the body instead.
_ACT_START_RE = re.compile(
    r"^(COMMISSION\s+)?(REGULATION|DIRECTIVE|DECISION|RECOMMENDATION)\b", re.I
)
_ACT_STOP_RE = re.compile(
    r"^(THE EUROPEAN PARLIAMENT|THE COUNCIL|THE COMMISSION|HAVING REGARD|HAS ADOPTED)", re.I
)


# Core EU circular-economy instruments. CELEX = sector(3) + year + type letter + number.
# These are adopted EU law, so status maps to "enacted" in our vocabulary. The classifier sets
# instrument_type / material_categories itself; the material hint here is just documentation.
SEED_ACTS: list[dict] = [
    {"celex": "32025R0040", "name": "Packaging & Packaging Waste Regulation (PPWR)", "material": "packaging"},
    {"celex": "32012L0019", "name": "WEEE Directive (e-waste)", "material": "electronics"},
    {"celex": "32023R1542", "name": "Batteries Regulation", "material": "batteries"},
    {"celex": "32019L0904", "name": "Single-Use Plastics Directive (SUP)", "material": "plastics"},
    {"celex": "31994L0062", "name": "Packaging & Packaging Waste Directive", "material": "packaging"},
    {"celex": "32000L0053", "name": "End-of-Life Vehicles Directive (ELV)", "material": "vehicles"},
    {"celex": "32008L0098", "name": "Waste Framework Directive", "material": "waste"},
    {"celex": "32024R1781", "name": "Ecodesign for Sustainable Products Regulation (ESPR)", "material": "multi"},
]


# EuroVoc concept IDs for the circular-economy / EPR domain, used to enumerate the relevant slice of
# EU law via SPARQL (resolved live from EuroVoc by label, then hand-curated to drop noise like
# "bank deposit"/"ore deposit"). This is the EU analog of the US epr_keywords filter — it pre-narrows
# CELLAR's ~hundreds-of-thousands of acts to the waste/packaging/recycling cluster; the Haiku
# classifier then judges true relevance (same confidence floor as the US pipeline).
EUROVOC_CONCEPTS = [
    "1158",  # waste management
    "2947",  # waste recycling
    "720",   # packaging
    "2746",  # packaging product
    "2589",  # pre-packaging
    "6411",  # electronic waste
    "3651",  # recycling technology
    "5819",  # recycled product
    "5533",  # deposit on a polluting product
    "718",   # waste disposal
    "343",   # waste
    "344",   # agricultural waste
    "345",   # industrial waste
    "5294",  # metal waste
    "346",   # non-recoverable waste
    "6103",  # hazardous waste
]
# Act types we ingest: R=regulation, L=directive, D=decision. Excludes A (international agreements),
# Y (other), H (recommendations), G — none of which are producer-facing compliance instruments.
ACT_TYPES = "RLD"


@dataclass
class EurLexAct:
    celex: str
    title: str
    summary: str        # short text fed to the classifier as `description`
    full_text: str      # cleaned plain text of the act body (stored in bill_texts)
    source_url: str
    status: str = "enacted"  # adopted EU law

    @property
    def bill_number(self) -> str:
        # Surface a readable act label as the "bill number" (CELEX is also stored in celex_id).
        return self.celex


def _strip_html(raw: str) -> str:
    no_blocks = _SCRIPT_STYLE_RE.sub(" ", raw)
    no_tags = _TAG_RE.sub(" ", no_blocks)
    # Unescape common entities then collapse whitespace.
    text = (
        no_tags.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#160;", " ")
    )
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANKLINES_RE.sub("\n\n", text).strip()


def _extract_title(full_text: str, fallback: str) -> str:
    """Assemble the act's official title from the body — the type line ("REGULATION (EU) …") plus the
    "of <date>" and "concerning/laying down …" lines, up to the enacting clause."""
    lines = [ln.strip() for ln in full_text.splitlines()]
    start = next((i for i, ln in enumerate(lines) if _ACT_START_RE.match(ln)), None)
    if start is not None:
        collected: list[str] = []
        for ln in lines[start : start + 14]:
            if not ln:
                continue
            if _ACT_STOP_RE.match(ln):
                break
            collected.append(ln)
        title = re.sub(r"\(Text with EEA relevance\)", "", " ".join(collected), flags=re.I)
        title = _WS_RE.sub(" ", title).strip()
        if len(title) > 20:
            return title[:500]
    # Fall back to the first substantial body line, else the seed name.
    for ln in lines:
        if len(ln) > 25 and not ln.lower().endswith(".xml"):
            return ln[:500]
    return fallback


class EurLexClient:
    """Async client for fetching EU acts from EUR-Lex/CELLAR. Use as an async context manager."""

    def __init__(self, timeout: float = 45.0):
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EurLexClient":
        self._client = httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True, headers=_BROWSER_HEADERS
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

    async def _pdf_text(self, celex: str) -> str:
        """Extract text from the act's PDF original (digital PDFs only; scanned/image PDFs yield
        little and are left to the caller's fallback). Best-effort — never raises."""
        from pypdf import PdfReader  # lazy: only when HTML was thin

        try:
            resp = await self._client.get(EURLEX_PDF.format(celex=celex))
            if resp.status_code != 200 or "pdf" not in resp.headers.get("content-type", ""):
                return ""
            reader = PdfReader(io.BytesIO(resp.content))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception as e:  # noqa: BLE001 — pypdf raises a zoo of errors on odd PDFs
            log.warning("eurlex_pdf_failed", celex=celex, error=str(e))
            return ""

    async def fetch_act(self, celex: str, fallback_name: str = "") -> EurLexAct | None:
        """Fetch one act's title + full text by CELEX. Tries the HTML rendering first, then falls back
        to extracting the PDF original (recovers older/annex-heavy acts EUR-Lex has no HTML for).
        Returns None only when neither yields usable text and there's no fallback name."""
        assert self._client is not None, "use EurLexClient as an async context manager"
        url = EURLEX_HTML.format(celex=celex)
        full_text = ""
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            full_text = _strip_html(resp.text)
        except httpx.HTTPError as e:
            log.warning("eurlex_html_failed", celex=celex, error=str(e))

        if len(full_text) < _MIN_BODY_CHARS:
            # No (or thin) HTML rendering — try the PDF original.
            pdf_text = await self._pdf_text(celex)
            if len(pdf_text) > len(full_text):
                full_text = pdf_text

        if len(full_text) < _MIN_BODY_CHARS:
            # Neither HTML nor PDF gave usable text (e.g. a pre-digital scanned Decision).
            log.warning("eurlex_no_text", celex=celex, chars=len(full_text))
            if not fallback_name:
                return None
        title = _extract_title(full_text, fallback_name or celex)
        # Description fed to the classifier: title carries most signal; prepend a slice of the body.
        summary = (title + "\n\n" + full_text[:1200]).strip()
        return EurLexAct(
            celex=celex,
            title=title,
            summary=summary,
            full_text=full_text,
            source_url=EURLEX_PAGE.format(celex=celex),
        )

    async def discover_celex(
        self,
        in_force_only: bool = True,
        concepts: list[str] | None = None,
        act_types: str = ACT_TYPES,
        limit: int = 5000,
    ) -> list[str]:
        """Enumerate circular-economy / EPR acts from CELLAR by EuroVoc concept.

        Queries works tagged with any of EUROVOC_CONCEPTS, returns their base sector-3 CELEX ids
        (no consolidated '-date' suffix), optionally restricted to in-force acts and to act_types
        (R/L/D). Wrapped in try/except: an endpoint hiccup must not break ingestion — the SEED list
        is the guaranteed fallback. Returns CELEX ids (possibly empty).
        """
        assert self._client is not None
        ids_uris = " ".join(
            f"<http://eurovoc.europa.eu/{c}>" for c in (concepts or EUROVOC_CONCEPTS)
        )
        in_force_clause = (
            '?w <http://publications.europa.eu/ontology/cdm#resource_legal_in-force> ?inforce .\n'
            '  FILTER(STR(?inforce) = "true")'
            if in_force_only
            else ""
        )
        query = f"""
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex WHERE {{
  VALUES ?concept {{ {ids_uris} }}
  ?w cdm:work_is_about_concept_eurovoc ?concept .
  ?w cdm:resource_legal_id_celex ?celex .
  {in_force_clause}
  FILTER(STRSTARTS(STR(?celex), "3"))
  FILTER(!CONTAINS(STR(?celex), "-"))
}}
LIMIT {limit}
"""
        try:
            resp = await self._client.get(
                SPARQL_ENDPOINT,
                params={"query": query, "format": "application/sparql-results+json"},
                headers={"Accept": "application/sparql-results+json"},
                timeout=180.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("eurlex_sparql_failed", error=str(e))
            return []
        types = set(act_types)
        out: list[str] = []
        for b in data.get("results", {}).get("bindings", []):
            celex = b.get("celex", {}).get("value")
            # CELEX = sector(1) + year(4) + type-letter + number; filter on the type letter (index 5).
            if celex and len(celex) > 5 and celex[5] in types:
                out.append(celex)
        log.info("eurlex_discovered", count=len(out), in_force_only=in_force_only)
        return out


async def sync_eurlex(
    *,
    in_force_only: bool = True,
    classify: bool = True,
    only_new: bool = False,
    include_seed: bool = True,
    max_acts: int | None = None,
) -> dict:
    """End-to-end EU-central ingest: discover (SPARQL) -> fetch -> upsert bills + bill_texts ->
    classify (region-aware pipeline). The single entry point shared by the bulk backfill script and
    the weekly scheduler cycle.

    - in_force_only: restrict discovery to currently-valid acts (the compliance-focused default).
    - only_new: skip CELEX already present in the DB — the cheap weekly-refresh mode.
    - include_seed: always union the curated SEED_ACTS so the core instruments are guaranteed.
    - max_acts: cap the number processed this run (bounds a backfill / a runaway).
    Classification runs in chunks of settings.max_haiku_calls_per_run so a large backfill isn't
    truncated by the per-run LLM cap. EU acts bypass the US-tuned keyword filter (curated source);
    the Haiku confidence floor still decides ce_relevant. Returns a summary dict.
    """
    from sqlalchemy import func, select

    from app.classification.pipeline import ClassificationPipeline
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models import Bill, BillText

    async with EurLexClient() as client:
        discovered = await client.discover_celex(in_force_only=in_force_only)
        items: dict[str, str] = {c: "" for c in discovered}
        if include_seed:
            for a in SEED_ACTS:
                items.setdefault(a["celex"], a["name"])

        if only_new:
            async with AsyncSessionLocal() as db:
                existing = set(
                    (
                        await db.execute(
                            select(Bill.celex_id).where(Bill.celex_id.is_not(None))
                        )
                    )
                    .scalars()
                    .all()
                )
            items = {c: n for c, n in items.items() if c not in existing}

        if max_acts is not None:
            items = dict(list(items.items())[:max_acts])

        log.info("eurlex_sync_start", to_process=len(items), only_new=only_new)

        ingested: list[int] = []
        fetched = skipped = 0
        # Commit every CHECKPOINT acts so a long backfill is checkpointed (survives a proxy/network
        # blip) and observable, rather than one giant all-or-nothing transaction holding ~hundreds of
        # large texts. Re-running is safe — upserts are keyed on celex_id.
        CHECKPOINT = 25
        total = len(items)
        async with AsyncSessionLocal() as db:
            for idx, (celex, name) in enumerate(items.items(), 1):
                act = await client.fetch_act(celex, fallback_name=name)
                if act is None:
                    skipped += 1
                    continue
                fetched += 1
                bill = (
                    await db.execute(select(Bill).where(Bill.celex_id == act.celex))
                ).scalar_one_or_none()
                if bill is None:
                    bill = Bill(celex_id=act.celex, region="EU", state="EU")
                    db.add(bill)
                bill.region = "EU"
                bill.state = "EU"
                bill.bill_number = act.bill_number
                bill.title = act.title
                bill.description = act.summary
                bill.status = act.status
                bill.source_url = act.source_url
                await db.flush()

                bt = (
                    await db.execute(select(BillText).where(BillText.bill_id == bill.id))
                ).scalar_one_or_none()
                if bt is None:
                    bt = BillText(bill_id=bill.id)
                    db.add(bt)
                bt.text = act.full_text
                bt.char_len = len(act.full_text)
                ingested.append(bill.id)
                if idx % CHECKPOINT == 0:
                    await db.commit()
                    log.info("eurlex_fetch_progress", done=idx, total=total, fetched=fetched, skipped=skipped)
            await db.commit()

    summary = {"discovered": len(discovered), "fetched": fetched, "skipped": skipped,
               "ingested": len(ingested), "classified": 0, "relevant": 0}

    if classify and ingested:
        chunk = max(1, settings.max_haiku_calls_per_run)
        for i in range(0, len(ingested), chunk):
            chunk_ids = ingested[i : i + chunk]
            async with AsyncSessionLocal() as db:
                bills = list(
                    (await db.execute(select(Bill).where(Bill.id.in_(chunk_ids)))).scalars().all()
                )
                # Curated source: bypass the US keyword gate, let Haiku judge relevance.
                res = await ClassificationPipeline().run(db, bills, skip_keyword_filter=True)
                summary["classified"] += res.classified_haiku
        async with AsyncSessionLocal() as db:
            summary["relevant"] = (
                await db.execute(
                    select(func.count())
                    .select_from(Bill)
                    .where(Bill.region == "EU", Bill.ce_relevant.is_(True))
                )
            ).scalar_one()

    log.info("eurlex_sync_done", **summary)
    return summary

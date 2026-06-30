"""Shared full-bill-text fetch ladder — the single source of truth for getting clean bill text.

Factored out of scripts/scan_bill_polymers.py for Layer B of the full-text search plan
(docs/V2_FULLTEXT_SEARCH_PLAN.md). Consumers: the polymer/resin scanner, the bill_texts backfill
(scripts/backfill_bill_text.py), and the bill_texts refresh job — one ladder so they can't drift.

Ladder (per bill): **LegiScan primary** (reliable full text + freshest quota) → **OpenStates
versions API** (throttled fallback) → **source_url scrape** (last; for many states the stored
source_url is the bill's overview/landing page, not the document). The returned text is
tag-stripped and whitespace-normalized so it is suitable for BOTH the regex resin detector AND
Postgres FTS / ts_headline — no HTML tags leak into the tsvector or the highlighted snippets.

`fetch_clean_text` is duck-typed on the bill: it needs `.state`, `.bill_number`, `.openstates_id`,
`.legiscan_bill_id`, `.source_url` (a SQLAlchemy row or any object with those attrs).
"""
from __future__ import annotations

import asyncio
import base64
import html
import re

from app.ingestion.legiscan import LegiScanClient
from app.ingestion.openstates import OpenStatesClient, _extract_pdf_text

# Source labels stored in bill_texts.source / shown by the scanner.
SOURCE_LEGISCAN = "legiscan"
SOURCE_OPENSTATES = "openstates"
SOURCE_URL = "source_url"
SOURCE_NONE = "none"

_TAG_RE = re.compile(r"<[^>]+>")
# Drop these blocks CONTENT-AND-ALL before stripping tags — otherwise a source_url landing-page
# scrape leaves inline JS/CSS text (e.g. gtag('config', …)) in the body, polluting the tsvector and
# producing junk ts_headline snippets. (Plain tag-stripping removes <script> but keeps the code.)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|head)\b[^>]*>.*?</\1>", re.I | re.S)
# C0 control bytes that aren't ordinary whitespace (\t\n\r) — they can't live in a Postgres TEXT
# column and only ever appear in binary/garbage, never real bill text.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Markers of a scraped web-app SHELL (nav menus, testimony-registration forms) rather than the bill
# document. source_url for some states — notably OR's OLIS — returns the measure *overview* page,
# whose chrome ("Toggle navigation", "Register to Testify") pollutes full-text search (e.g. a "phone"
# query matched 41 OR bills on the testimony form). None of these strings occur in real statutory
# text, so their presence means we grabbed a page, not a bill → treat the fetch as no-text.
_WEB_CHROME_MARKERS = ("toggle navigation", "register to testify", "staff login")


def canon_bill_number(num: str | None) -> str:
    """Normalize a bill number for cross-source matching (drop punctuation, zero-pad)."""
    if not num:
        return ""
    raw = num.upper().replace("-", "").replace(" ", "").replace(".", "")
    m = re.match(r"^([A-Z]+)0*(\d+)", raw)
    return f"{m.group(1)}{m.group(2)}" if m else raw


def clean_text(raw: str) -> str:
    """Strip HTML tags (when present) and collapse whitespace. Idempotent on already-clean text,
    so it is safe to run over every ladder rung — mirrors app.ingestion.openstates._document_text
    so the OpenStates rungs (already cleaned there) and the raw LegiScan HTML rung end up identical.
    """
    if not raw:
        return ""
    # A NUL byte means the source returned binary (e.g. a source_url that serves an image), not bill
    # text — skip it entirely (Postgres TEXT rejects NUL, and storing a stripped image fragment would
    # be junk). The bill then shows as not-indexed rather than crashing the run.
    if "\x00" in raw:
        return ""
    if "<" in raw[:2000]:
        raw = _SCRIPT_STYLE_RE.sub(" ", raw)
        raw = html.unescape(_TAG_RE.sub(" ", raw))
    raw = _CTRL_RE.sub("", raw)  # drop any residual control bytes from dirty-but-textual sources
    cleaned = re.sub(r"\s+", " ", raw).strip()
    # Scraped web-app shell, not a bill document → skip (the bill shows as not-indexed).
    low = cleaned.lower()
    if any(m in low for m in _WEB_CHROME_MARKERS):
        return ""
    return cleaned


async def _resolve_legiscan_id(client: LegiScanClient, b) -> int | None:
    """LegiScan bill_id: the stored id, else an exact bill#/state search match."""
    if b.legiscan_bill_id:
        return int(b.legiscan_bill_id)
    target = canon_bill_number(b.bill_number)
    if not target:
        return None
    try:
        res = await client.search((b.bill_number or "").replace("-", " "), state=b.state)
    except Exception:  # noqa: BLE001
        return None
    for r in res:
        if r.get("state") == b.state and canon_bill_number(r.get("bill_number")) == target:
            return int(r["bill_id"])
    return None


async def _legiscan_text(client: LegiScanClient, legiscan_bill_id: int) -> str:
    """Full bill text from LegiScan: pick the best text doc, decode HTML/PDF/plain.

    Returns text with PDFs already extracted; HTML is still tagged here and is cleaned by the
    caller via clean_text() (so the >400-char substance gate below sees the raw document)."""
    bill = await client.get_bill(int(legiscan_bill_id))
    docs = bill.get("texts") or []

    def rank(d):
        return 1 if "html" in (d.get("mime") or "").lower() else 0

    for d in sorted(docs, key=rank, reverse=True):
        doc_id = d.get("doc_id")
        if not doc_id:
            continue
        data = await client._get("getBillText", id=int(doc_id))
        encoded = (data.get("text") or {}).get("doc", "")
        if not encoded:
            continue
        try:
            blob = base64.b64decode(encoded)
        except Exception:  # noqa: BLE001
            continue
        if blob[:5] == b"%PDF-" or "pdf" in (d.get("mime") or "").lower():
            txt = _extract_pdf_text(blob)
        else:
            try:
                txt = blob.decode("utf-8")
            except UnicodeDecodeError:
                txt = blob.decode("latin-1", errors="replace")
        if txt and len(txt) > 400:
            return txt
    return ""


async def fetch_clean_text(
    ls_client: LegiScanClient, os_client: OpenStatesClient, b, os_delay: float = 0.0
) -> tuple[str, str]:
    """Fetch a bill's full text and return ``(clean_text, source)``.

    `source` is one of SOURCE_LEGISCAN / SOURCE_OPENSTATES / SOURCE_URL / SOURCE_NONE. LegiScan is
    primary; the OpenStates versions API is the throttled fallback (`os_delay` seconds before each
    call to respect the free-tier limit); the source_url scrape is last. Empty text → ("", "none").
    """
    try:
        lid = await _resolve_legiscan_id(ls_client, b)
        if lid:
            txt = await _legiscan_text(ls_client, lid)
            if txt:
                return clean_text(txt), SOURCE_LEGISCAN
    except Exception:  # noqa: BLE001
        pass
    if b.openstates_id and not str(b.openstates_id).startswith("hist:"):
        if os_delay:
            await asyncio.sleep(os_delay)  # respect OpenStates free-tier rate limit
        txt = await os_client.get_bill_text(b.openstates_id)
        if txt:
            return clean_text(txt), SOURCE_OPENSTATES
    if b.source_url:
        txt = await os_client.get_text_from_source(b.source_url)
        if txt:
            return clean_text(txt), SOURCE_URL
    return "", SOURCE_NONE

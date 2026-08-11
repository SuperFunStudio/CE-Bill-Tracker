"""Shared full-bill-text fetch ladder — the single source of truth for getting clean bill text.

Factored out of scripts/scan_bill_polymers.py for Layer B of the full-text search plan
(docs/V2_FULLTEXT_SEARCH_PLAN.md). Consumers: the polymer/resin scanner, the bill_texts backfill
(scripts/backfill_bill_text.py), and the bill_texts refresh job — one ladder so they can't drift.

Ladder (per bill): **NYS Open Legislation first for NY bills** (authoritative, clean plain text,
needs settings.nys_api_key — skipped when unset) → **LegiScan primary** (reliable full text +
freshest quota) → **OpenStates versions API** (throttled fallback) → **source_url scrape** (last;
for many states the stored source_url is the bill's overview/landing page, not the document —
and for NY it's the OpenLeg API itself, which 401s without a key). The returned text is
tag-stripped and whitespace-normalized so it is suitable for BOTH the regex resin detector AND
Postgres FTS / ts_headline — no HTML tags leak into the tsvector or the highlighted snippets.

`fetch_clean_text` is duck-typed on the bill: it needs `.state`, `.bill_number`, `.openstates_id`,
`.legiscan_bill_id`, `.source_url` (a SQLAlchemy row or any object with those attrs), plus
`.status_date` / `.last_action_date` — read via getattr, so an older caller that omits them still
works, it just loses the LegiScan search rung (see below).

SESSION SAFETY: legislatures reuse bill numbers every session, so resolving a LegiScan id by
(state, bill_number) alone can attach a *different* bill's text — CA SB 54 is packaging EPR in
2021-22 and court fee waivers in 2025-26. Search is therefore constrained by the bill's own year and
the resolved bill's session window is verified before its text is accepted. A bill we cannot pin to
a session yields NO text rather than someone else's: silent wrong text reads as a real extraction
and gets cited, which is far worse than an unindexed bill (a case every consumer already handles).
"""
from __future__ import annotations

import asyncio
import base64
import html
import re

from app.ingestion.legiscan import LegiScanClient
from app.ingestion.nysenate import NYSenateClient, session_year_for
from app.ingestion.openstates import OpenStatesClient, _extract_pdf_text

# Source labels stored in bill_texts.source / shown by the scanner.
SOURCE_NYSENATE = "nysenate"
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
_WEB_CHROME_MARKERS = (
    "toggle navigation", "register to testify", "staff login",
    # A client-rendered legislature site (MT's, among others) serves an empty SPA shell to a plain
    # HTTP fetch. 25 bills had this stored as their statute text.
    "enable javascript",
)
# Site FOOTER furniture. Checked only in the document's tail, because these strings can legitimately
# appear mid-text — a data-privacy bill says "privacy policy", a copyright bill says "all rights
# reserved" — but a statute does not END on one. RI's bill pages slipped past the markers above
# (their chrome is a bare menu: "Senate House Auditor General Captiol Television…") and were stored
# as bill text, so seven RI beverage-deposit bills held a page shell instead of their statute.
_PAGE_FOOTER_MARKERS = (
    "all rights reserved", "privacy policy", "terms of use", "terms of service",
)
# How much of the tail counts as "the footer".
_FOOTER_WINDOW = 400


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
    if any(m in low[-_FOOTER_WINDOW:] for m in _PAGE_FOOTER_MARKERS):
        return ""
    return cleaned


def bill_year(b) -> int | None:
    """The session year to match a bill on — status_date, else last_action_date. None when neither
    is known, which is the signal that we cannot safely resolve this bill by search."""
    for attr in ("status_date", "last_action_date"):
        d = getattr(b, attr, None)
        if d is not None and getattr(d, "year", None):
            return d.year
    return None


# Legislatures reuse bill numbers every session — "CA SB 54" exists in 2021-22 (packaging EPR) and
# again in 2025-26 (court fee waivers). A session window may legitimately end the year before a
# bill's recorded status_date (a measure signed or chaptered after the session closed), so allow a
# year of slack; the collisions this guards against are two or more sessions apart.
_SESSION_YEAR_SLACK = 1


def _session_matches(bill_data: dict, year: int) -> bool:
    """Does the LegiScan bill's session window plausibly contain `year`? Unknown window → False:
    an unverifiable match is exactly the case that attached the wrong statute."""
    session = bill_data.get("session") or {}
    start, end = session.get("year_start"), session.get("year_end")
    if not start or not end:
        return False
    return int(start) - _SESSION_YEAR_SLACK <= year <= int(end) + _SESSION_YEAR_SLACK


async def _resolve_legiscan_id(client: LegiScanClient, b) -> tuple[int | None, bool]:
    """Returns ``(legiscan_bill_id, needs_session_check)``.

    A stored id is trusted — it was captured alongside the bill record, so it cannot be a
    number collision. A search-resolved id is not: getSearch matches on number + state and skews
    to the CURRENT session, so an older bill would silently adopt a same-numbered new bill's text.
    We constrain the search by year AND make the caller verify the session window before storing.
    """
    if b.legiscan_bill_id:
        return int(b.legiscan_bill_id), False
    target = canon_bill_number(b.bill_number)
    year = bill_year(b)
    # No year to match on means no way to tell the sessions apart. Fall through to the other rungs
    # rather than guess — wrong text is far more damaging than no text, because it reads as a real
    # extraction and gets cited.
    if not target or year is None:
        return None, False
    try:
        res = await client.search(
            (b.bill_number or "").replace("-", " "), state=b.state, year=year
        )
    except Exception:  # noqa: BLE001
        return None, False
    for r in res:
        if r.get("state") == b.state and canon_bill_number(r.get("bill_number")) == target:
            return int(r["bill_id"]), True
    return None, False


async def _legiscan_text(
    client: LegiScanClient, legiscan_bill_id: int, expect_year: int | None = None
) -> str:
    """Full bill text from LegiScan: pick the best text doc, decode HTML/PDF/plain.

    When `expect_year` is given the resolved bill's session window must contain it, otherwise we
    return no text. This is the guard on a search-resolved id: getBill carries the authoritative
    session, so it is the last point at which a same-numbered bill from another session can be
    caught before its text is stored under the wrong record.

    Returns text with PDFs already extracted; HTML is still tagged here and is cleaned by the
    caller via clean_text() (so the >400-char substance gate below sees the raw document)."""
    bill = await client.get_bill(int(legiscan_bill_id))
    if expect_year is not None and not _session_matches(bill, expect_year):
        return ""
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
    ls_client: LegiScanClient,
    os_client: OpenStatesClient,
    b,
    os_delay: float = 0.0,
    ny_client: NYSenateClient | None = None,
) -> tuple[str, str]:
    """Fetch a bill's full text and return ``(clean_text, source)``.

    `source` is one of SOURCE_NYSENATE / SOURCE_LEGISCAN / SOURCE_OPENSTATES / SOURCE_URL /
    SOURCE_NONE. For NY bills the NYS Open Legislation API is tried first when `ny_client` is
    passed and enabled (authoritative + plain text); LegiScan is primary elsewhere; the OpenStates
    versions API is the throttled fallback (`os_delay` seconds before each call to respect the
    free-tier limit); the source_url scrape is last. Empty text → ("", "none").

    Each rung is cleaned BEFORE it is accepted, so a rung that returns bytes which clean_text
    rejects (a page shell, an SPA stub, site chrome) falls through to the next rung instead of
    ending the ladder with an empty result. Testing the raw response and cleaning at the return
    meant one junk scrape could mask a perfectly good OpenStates document.
    """
    if b.state == "NY" and ny_client is not None and ny_client.is_enabled:
        session = session_year_for(b)
        print_no = canon_bill_number(b.bill_number)
        if session and print_no:
            try:
                txt = clean_text(await ny_client.get_bill_text(session, print_no))
                if txt:
                    return txt, SOURCE_NYSENATE
            except Exception:  # noqa: BLE001
                pass  # fall through to the generic rungs
    try:
        lid, needs_session_check = await _resolve_legiscan_id(ls_client, b)
        if lid:
            txt = clean_text(await _legiscan_text(
                ls_client, lid, expect_year=bill_year(b) if needs_session_check else None
            ))
            if txt:
                return txt, SOURCE_LEGISCAN
    except Exception:  # noqa: BLE001
        pass
    if b.openstates_id and not str(b.openstates_id).startswith("hist:"):
        if os_delay:
            await asyncio.sleep(os_delay)  # respect OpenStates free-tier rate limit
        txt = clean_text(await os_client.get_bill_text(b.openstates_id))
        if txt:
            return txt, SOURCE_OPENSTATES
    if b.source_url:
        txt = clean_text(await os_client.get_text_from_source(b.source_url))
        if txt:
            return txt, SOURCE_URL
    return "", SOURCE_NONE

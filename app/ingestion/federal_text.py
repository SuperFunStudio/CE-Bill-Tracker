"""Fetch full text for federal circular-economy *enablers* (statutes / CFR / EOs) from
KEYLESS US-government sources, and window it down to the circular-economy-relevant portions.

Why windowing
-------------
Some enablers are enormous (the IIJA public law is ~1,000+ pages). Storing an entire act
in `bill_texts` would swamp the `english` FTS index and drown the deep-read passages in
irrelevant appropriations boilerplate. So for anything over `SOFT_CAP`, we keep only the
paragraphs/sections that mention circular-economy terms (plus the short-title/preamble head),
capped at `HARD_CAP`. Small laws (e.g. Save Our Seas 2.0, ~97k) are kept whole.

Sources (all keyless):
- govinfo public-law HTML : https://www.govinfo.gov/content/pkg/PLAW-<c>publ<n>/html/PLAW-<c>publ<n>.htm
- eCFR versioner XML       : https://www.ecfr.gov/api/versioner/v1/full/<date>/title-<N>.xml?part=<P>
- Federal Register / govinfo EO HTML (executive_order)
- govinfo USCODE HTML (uscode)

Used by scripts/import_federal_enablers.py; standalone-testable via __main__.
"""
from __future__ import annotations

import html
import re
import sys

import httpx

# Keep whole below this; window above it.
SOFT_CAP = 120_000
# Never store more than this many chars of windowed text.
HARD_CAP = 140_000
# Always keep this much of the head verbatim (short title / table of contents / preamble).
HEAD_KEEP = 3_000

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Circular-economy signal — a paragraph matching any of these survives windowing.
_CE = re.compile(
    r"recycl|recover(ed|able)?\s+(material|content|resource)|recyclable|circular\s+econom|"
    r"extended\s+producer|producer\s+responsibilit|product\s+stewardship|marine\s+debris|"
    r"bio-?based|compost|reuse|re-?use|refill|deposit[\s-]?return|take[\s-]?back|"
    r"end[\s-]of[\s-]life|remanufactur|source\s+reduction|pollution\s+prevention|"
    r"solid\s+waste|scrap|secondary\s+material|post-?consumer|comprehensive\s+procurement|"
    r"designated\s+item|minimum\s+content|sustainab",
    re.IGNORECASE,
)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_MULTINL = re.compile(r"\n{3,}")
# C0 control chars except tab (\x09) and newline (\x0a) — Postgres text/varchar rejects NUL
# (0x00), and other controls are noise. Govinfo's Federal Register HTML carries stray NULs.
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean(text: str) -> str:
    text = _TAG.sub("", text)
    text = html.unescape(text)  # decode all entity forms (&amp;, &#8212;, &#x2014;, &sect;, …)
    text = _CTRL.sub("", text)  # drop NUL + C0 controls (unstorable / noise)
    text = _WS.sub(" ", text)
    text = _MULTINL.sub("\n\n", text)
    return text.strip()


def _window(text: str) -> str:
    """Keep the head plus every CE-relevant paragraph, capped at HARD_CAP."""
    if len(text) <= SOFT_CAP:
        return text[:HARD_CAP]
    head = text[:HEAD_KEEP]
    paras = re.split(r"\n\s*\n", text[HEAD_KEEP:])
    kept, size = [head], len(head)
    for p in paras:
        if not _CE.search(p):
            continue
        p = p.strip()
        if not p:
            continue
        if size + len(p) + 2 > HARD_CAP:
            break
        kept.append(p)
        size += len(p) + 2
    out = "\n\n".join(kept)
    # If the CE filter matched almost nothing (unexpected), fall back to a plain head slice
    # so we never store a near-empty text for a law we deliberately curated in.
    if len(out) < HEAD_KEEP + 500:
        out = text[:SOFT_CAP]
    return out


def _fetch(url: str, accept: str) -> str:
    with httpx.Client(headers={"User-Agent": _UA, "Accept": accept},
                      follow_redirects=True, verify=False, timeout=60.0) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def fetch_text(fulltext_url: str, fulltext_kind: str) -> tuple[str, int]:
    """Return (windowed_ce_text, raw_char_len). raw_char_len is the pre-window size (for reporting)."""
    if fulltext_kind == "ecfr_xml":
        raw = _clean(_fetch(fulltext_url, "application/xml,text/xml,*/*"))
    elif fulltext_kind in ("govinfo_html", "uscode", "federalregister"):
        raw = _clean(_fetch(fulltext_url, "text/html,application/xhtml+xml,*/*"))
    else:
        raise ValueError(f"unsupported fulltext_kind: {fulltext_kind!r}")
    return _window(raw), len(raw)


if __name__ == "__main__":
    # Smoke test against the two verified keyless sources.
    tests = [
        ("https://www.govinfo.gov/content/pkg/PLAW-116publ224/html/PLAW-116publ224.htm", "govinfo_html", "Save Our Seas 2.0"),
        ("https://www.ecfr.gov/api/versioner/v1/full/2024-01-01/title-40.xml?part=247", "ecfr_xml", "40 CFR 247 (CPG)"),
    ]
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for url, kind, name in tests:
        txt, raw = fetch_text(url, kind)
        ce_hits = len(_CE.findall(txt))
        print(f"\n=== {name} [{kind}] ===")
        print(f"  raw chars   : {raw:,}")
        print(f"  stored chars: {len(txt):,}  (windowed={'yes' if raw > SOFT_CAP else 'no, kept whole'})")
        print(f"  CE matches  : {ce_hits}")
        print(f"  head        : {txt[:220].strip()!r}")

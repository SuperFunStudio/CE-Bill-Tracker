"""Validate + normalize the curated federal circular-economy *enabler* seed.

Pipeline (mirrors build_historical_seed.py, the broken-link lesson):
    data/seed/_federal_enablers_raw.json   (researcher output; schema below)
        │  map `theme` -> instrument_type + carry material tags
        │  LIVE-validate BOTH source_url and fulltext_url over HTTP
        ▼
    data/seed/federal_enablers.json         — entries whose URLs resolved (ready to import)
    data/seed/_federal_enablers_quarantine.json  — dead-URL entries (manual review)

Raw entry schema (per object):
    key, title, kind, citation, public_law, enacted_date, source_url, fulltext_url,
    fulltext_kind, theme, materials[], summary, confidence, fulltext_verified

Run:
    python scripts/build_federal_seed.py            # validate + write
    python scripts/build_federal_seed.py --no-http  # offline (skip URL checks)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "seed" / "_federal_enablers_raw.json"
OUT = ROOT / "data" / "seed" / "federal_enablers.json"
QUARANTINE = ROOT / "data" / "seed" / "_federal_enablers_quarantine.json"

# Researcher `theme` -> the corpus instrument_type (validated against the live taxonomy:
# epr / recycled_content / incentives / right_to_repair / other, …). These enablers are
# mostly government-purchasing (recycled_content) and funding (incentives) levers, not EPR.
THEME_INSTRUMENT: dict[str, str] = {
    "recycling_infrastructure": "incentives",
    "recovered_content_procurement": "recycled_content",
    "biobased_procurement": "recycled_content",
    "federal_sustainability": "recycled_content",
    "marine_debris": "incentives",
    "battery_recycling": "epr",
    "epr": "epr",
    "pollution_prevention": "other",
    "right_to_repair": "right_to_repair",
    "other": "other",
}

_LIVE_BUT_BLOCKED = {401, 403, 405, 406, 429}  # gatekept, not dead — keep


# Lifecycle -> DB status. "repealed" is the umbrella no-longer-in-force value (the precise
# sub-type — rescinded/superseded/repealed — is preserved in compliance_details.lifecycle at
# import). in_force enablers stay "enacted".
_LIFECYCLE_STATUS = {
    "in_force": "enacted",
    "rescinded": "repealed",
    "superseded": "repealed",
    "repealed": "repealed",
}


def _to_seed(raw: dict) -> dict:
    theme = raw.get("theme", "other")
    lifecycle = raw.get("lifecycle_status", "in_force")
    return {
        "key": raw["key"],
        "region": "US",
        "state": "US",              # US-federal jurisdiction
        "bill_number": (raw.get("citation") or "").strip() or None,
        "title": raw.get("title"),
        "public_law": raw.get("public_law"),
        "kind": raw.get("kind"),
        "status": _LIFECYCLE_STATUS.get(lifecycle, "enacted"),
        "lifecycle_status": lifecycle,
        "lifecycle_date": raw.get("lifecycle_date"),
        "lifecycle_by": raw.get("lifecycle_by"),
        "enacted_date": raw.get("enacted_date"),
        "instrument_type": THEME_INSTRUMENT.get(theme, "other"),
        "theme": theme,
        "material_categories": raw.get("materials", []) or [],
        "urgency": "low",           # in force / active
        "ai_summary": raw.get("summary"),
        "source_url": raw.get("source_url"),
        "fulltext_url": raw.get("fulltext_url"),
        "fulltext_kind": raw.get("fulltext_kind"),
        "confidence": raw.get("confidence", "medium"),
    }


async def _check(client: httpx.AsyncClient, url: str | None) -> tuple[bool, int | str]:
    if not url:
        return (False, "no_url")
    try:
        r = await client.get(url, follow_redirects=True, timeout=30.0)
        return (r.status_code < 400 or r.status_code in _LIVE_BUT_BLOCKED, r.status_code)
    except Exception as e:  # noqa: BLE001
        return (False, type(e).__name__)


async def main(do_http: bool = True) -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    seeds = [_to_seed(r) for r in raw]

    # Dedupe on (state, bill_number) and on key.
    seen_key, seen_bn, deduped = set(), set(), []
    for s in seeds:
        if s["key"] in seen_key:
            continue
        bn_key = (s["state"], s["bill_number"])
        if s["bill_number"] and bn_key in seen_bn:
            continue
        seen_key.add(s["key"])
        if s["bill_number"]:
            seen_bn.add(bn_key)
        deduped.append(s)

    kept, quarantined = deduped, []
    if do_http:
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        async with httpx.AsyncClient(headers={"User-Agent": ua}, verify=False) as client:
            sem = asyncio.Semaphore(6)

            async def run(s: dict):
                async with sem:
                    src_ok, src_code = await _check(client, s["source_url"])
                    ft_ok, ft_code = await _check(client, s["fulltext_url"])
                    s["_src_status"], s["_ft_status"] = src_code, ft_code
                    # A 5xx is a transient gateway hiccup / bot-throttle on a big .gov site, not a
                    # dead resource — keep it (the weekly link-health job re-verifies source_url).
                    src_soft = isinstance(src_code, int) and 500 <= src_code < 600
                    # Program/strategy entries have no legal full text by design (fulltext_kind
                    # "none"); they cite via ai_summary like text-free foreign rows. Require text
                    # only for entries that claim a fulltext_url.
                    text_free = (s.get("fulltext_kind") in (None, "none")) or not s.get("fulltext_url")
                    text_ok = text_free or ft_ok
                    return (src_ok or src_soft) and text_ok

            results = await asyncio.gather(*(run(s) for s in deduped))
        kept = [s for s, ok in zip(deduped, results) if ok]
        quarantined = [s for s, ok in zip(deduped, results) if not ok]

    OUT.write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")
    if quarantined:
        QUARANTINE.write_text(json.dumps(quarantined, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    by_instr = Counter(s["instrument_type"] for s in kept)
    print(f"raw entries          : {len(raw)}")
    print(f"after dedupe         : {len(deduped)}")
    print(f"URL-validated (kept) : {len(kept)}  -> {OUT.relative_to(ROOT)}")
    print(f"quarantined          : {len(quarantined)}"
          + (f"  -> {QUARANTINE.relative_to(ROOT)}" if quarantined else ""))
    print("by instrument (kept) :", dict(sorted(by_instr.items())))
    if quarantined:
        print("\nQUARANTINED (fix a URL then move back into the raw file):")
        for s in quarantined:
            print(f"  {s['key']:32} src={s.get('_src_status')} ft={s.get('_ft_status')}  {s['fulltext_url']}")


if __name__ == "__main__":
    asyncio.run(main(do_http="--no-http" not in sys.argv))

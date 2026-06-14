"""Assemble + validate the historical EPR-law seed from researched raw data.

Pipeline
--------
data/seed/_historical_raw.json  (researcher output: state, product_category, bill_number,
                                 title, enacted_date, source_url, source_url_verified, notes)
        │  normalize bill_number to DB form ("SB 20" -> "SB-20")
        │  map product_category -> instrument_type + material_categories
        │  LIVE-validate every source_url over HTTP (the broken-link lesson that
        │  retired the original seed_database.py)
        ▼
data/seed/historical_epr_laws.json        — entries whose URL resolved (ready to import)
data/seed/_historical_quarantine.json     — entries whose URL failed (manual review)

Run:
    python scripts/build_historical_seed.py            # validate + write
    python scripts/build_historical_seed.py --no-http  # skip URL checks (offline)
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.coordinator import _normalize_bill_number  # noqa: E402

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "seed" / "_historical_raw.json"
OUT = ROOT / "data" / "seed" / "historical_epr_laws.json"
QUARANTINE = ROOT / "data" / "seed" / "_historical_quarantine.json"
EXISTING = ROOT / "data" / "seed" / "known_epr_laws.json"

# product_category -> (instrument_type, material_categories[])
CATEGORY_MAP: dict[str, tuple[str, list[str]]] = {
    "packaging": ("epr", ["packaging", "paper"]),
    "paint": ("epr", ["paint"]),
    "carpet": ("epr", ["carpet"]),
    "mattresses": ("epr", ["mattresses"]),
    "textiles": ("epr", ["textiles"]),
    "electronics": ("epr", ["electronics"]),
    "solar_panels": ("epr", ["solar_panels", "electronics"]),
    "batteries": ("epr", ["batteries"]),
    "lighting": ("epr", ["lighting", "mercury"]),
    "mercury_thermostats": ("epr", ["mercury", "thermostats"]),
    "mercury_auto_switches": ("epr", ["mercury", "auto_switches"]),
    "tires": ("epr", ["tires"]),
    "pesticides": ("epr", ["pesticides"]),
    "pharmaceuticals": ("epr", ["pharmaceuticals"]),
    "medical_sharps": ("epr", ["medical_sharps"]),
    "hhw": ("epr", ["household_hazardous_waste"]),
    "gas_cylinders": ("epr", ["gas_cylinders"]),
    "motor_oil": ("epr", ["motor_oil"]),
}

# A few entries are stewardship-adjacent rather than true producer-takeback EPR.
DEPOSIT_RETURN_KEYS = {("RI", "tires")}  # RI refundable tire deposit


# A few pre-2010 laws have no chamber bill number; their source cites a session-law chapter
# or codified statute (e.g. "Acts 1993, c. 462", "Fla. Stat. 403.7192"). Those are real
# identifiers but must NOT go through chamber normalization ("SB 20"->"SB-20"), which would
# mangle them. Detect a citation by its punctuation / law-cite keywords and pass it verbatim.
_CITATION_HINT = re.compile(r"[.,§]|\b(?:Code|Stat|Act|Law|Laws|Gen|c\.)\b", re.IGNORECASE)


def _seed_bill_number(bn: str | None) -> str | None:
    if not bn:
        return None
    return bn.strip() if _CITATION_HINT.search(bn) else _normalize_bill_number(bn)


def _to_seed(raw: dict) -> dict:
    cat = raw["product_category"]
    instrument, materials = CATEGORY_MAP.get(cat, ("epr", [cat]))
    if (raw["state"], cat) in DEPOSIT_RETURN_KEYS:
        instrument = "deposit_return"
    bn = raw.get("bill_number")
    return {
        "state": raw["state"],
        "bill_number": _seed_bill_number(bn),
        "title": raw.get("title"),
        "status": "enacted",
        "enacted_date": raw.get("enacted_date"),
        "effective_date": None,
        "material_categories": materials,
        "instrument_type": instrument,
        "product_category": cat,
        "urgency": "low",  # historical, already in effect
        "ai_summary": raw.get("notes"),
        "source_url": raw.get("source_url"),
        "compliance_details": None,
    }


# Codes that mean "the resource exists but the server is gatekeeping the bot"
# (anti-bot challenge, auth, method, content-negotiation, rate-limit) — these are NOT
# dead links, so we keep them. Only 404/410/5xx and connection errors are truly dead.
_LIVE_BUT_BLOCKED = {401, 403, 405, 406, 429}


async def _check(client: httpx.AsyncClient, url: str) -> tuple[bool, int | str]:
    try:
        r = await client.get(url, follow_redirects=True, timeout=25.0)
        ok = r.status_code < 400 or r.status_code in _LIVE_BUT_BLOCKED
        return (ok, r.status_code)
    except Exception as e:  # noqa: BLE001
        return (False, type(e).__name__)


async def main(do_http: bool = True) -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    seeds = [_to_seed(r) for r in raw]

    # Dedupe within the historical set on (state, normalized bill_number, product_category).
    seen: set = set()
    deduped: list[dict] = []
    for s in seeds:
        key = (s["state"], s["bill_number"], s["product_category"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)

    # Flag overlap with the existing (packaging-era) seed for visibility.
    existing_keys = set()
    try:
        for law in json.loads(EXISTING.read_text(encoding="utf-8")):
            existing_keys.add((law.get("state"), _normalize_bill_number(law.get("bill_number") or "")))
    except Exception:  # noqa: BLE001
        pass
    overlap = [s for s in deduped if (s["state"], s["bill_number"]) in existing_keys]

    kept, quarantined = deduped, []
    if do_http:
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        async with httpx.AsyncClient(
            headers={"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,*/*"},
            verify=False,
        ) as client:
            sem = asyncio.Semaphore(8)

            async def run(s: dict):
                async with sem:
                    ok, code = await _check(client, s["source_url"])
                    s["_url_status"] = code
                    return ok

            results = await asyncio.gather(*(run(s) for s in deduped))
        kept = [s for s, ok in zip(deduped, results) if ok]
        quarantined = [s for s, ok in zip(deduped, results) if not ok]

    for s in kept + quarantined:
        s.pop("_url_status", None)

    OUT.write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")
    if quarantined:
        QUARANTINE.write_text(json.dumps(quarantined, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    by_cat = Counter(s["product_category"] for s in kept)
    print(f"raw entries            : {len(raw)}")
    print(f"after dedupe           : {len(deduped)}")
    print(f"URL-validated (kept)   : {len(kept)}  -> {OUT.relative_to(ROOT)}")
    print(f"quarantined (dead URL) : {len(quarantined)}" + (f"  -> {QUARANTINE.relative_to(ROOT)}" if quarantined else ""))
    print(f"overlap w/ existing seed: {len(overlap)} (will be skipped by importer if already in DB)")
    print("by category (kept):", dict(sorted(by_cat.items())))
    if quarantined:
        print("\nQUARANTINED (fix URL or confirm enacted, then move into _historical_raw.json):")
        for s in quarantined:
            print(f"  {s['state']:2} {s['product_category']:22} {s['bill_number'] or '(no bill#)':12} {s['source_url']}")


if __name__ == "__main__":
    asyncio.run(main(do_http="--no-http" not in sys.argv))

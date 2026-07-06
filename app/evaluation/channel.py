"""Derive `channel_maturity` from the corpus — the one map axis the data can actually measure.

A material has a mature reverse channel to the extent that enacted laws have already stood up collection
for it, across many jurisdictions. So we count, per material, the DISTINCT jurisdictions with an enacted
law that legislates a reverse channel (a collection target, a PRO/stewardship org, deposit-return, or
EPR), and saturate that breadth onto 0..1. Batteries/e-waste/paint/mattress/carpet — the materials with
EPR laws in a dozen-plus states — come out mature; textiles (a couple of jurisdictions) comes out low.

Corpus coverage is uneven (old lead-acid/aluminium laws are under-represented), so the corpus signal is
BLENDED with the hand-set seed prior rather than replacing it — the seed keeps a known-ubiquitous channel
from being zeroed by a thin corpus, while the data pulls the estimate toward reality where the corpus is
rich. Result is cached (channel maturity moves on the scale of legislative sessions, not requests).
"""
from __future__ import annotations

import math
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.strength import MATERIAL_PROFILES, match_material_label
from app.models import Bill

# 0.5 = weight the enacted-law breadth and the seed prior equally. Bump toward 1.0 as corpus coverage of
# historical take-back laws improves.
_CORPUS_WEIGHT = 0.5
_SATURATION = 6.0  # ~a dozen jurisdictions with a collection law reads as a mature/ubiquitous channel
_TTL_SECONDS = 6 * 3600

_SEED = {p.label: p.channel_maturity for p in MATERIAL_PROFILES}

_cache: dict[str, float] | None = None
_cache_at = 0.0


def _channel_signal(cd: dict, instrument_types: list | None) -> bool:
    """True if this law legislates a reverse channel for its material: a collection target, a PRO, a
    deposit-return scheme, or EPR (which implies producer take-back)."""
    def present(key: str) -> bool:
        env = cd.get(key)
        return isinstance(env, dict) and env.get("status") == "present"

    instruments = {str(i).lower() for i in (instrument_types or [])}
    return (
        present("collection_targets") or present("pro_structure")
        or bool(instruments & {"deposit_return", "epr"})
    )


async def _compute(db: AsyncSession) -> dict[str, float]:
    rows = (
        await db.execute(
            select(Bill.state, Bill.region, Bill.title, Bill.instrument_types, Bill.compliance_details)
            .where(Bill.status == "enacted")
            .where(Bill.ce_relevant.is_(True))
            .where(Bill.compliance_details.isnot(None))
        )
    ).all()

    # Per material: jurisdictions with ANY enacted law (coverage), and with a channel-signal law.
    any_law: dict[str, set[str]] = {}
    channel_law: dict[str, set[str]] = {}
    for r in rows:
        cd = r.compliance_details or {}
        label = match_material_label(" ".join([*(cd.get("covered_products") or []), r.title or ""]))
        if not label:
            continue
        juris = (r.state or r.region or "?")
        any_law.setdefault(label, set()).add(juris)
        if _channel_signal(cd, r.instrument_types):
            channel_law.setdefault(label, set()).add(juris)

    out: dict[str, float] = {}
    for label, seen in any_law.items():
        n = len(channel_law.get(label, set()))
        corpus_norm = 1.0 - math.exp(-n / _SATURATION)
        seed = _SEED.get(label, 0.45)
        out[label] = round((1 - _CORPUS_WEIGHT) * seed + _CORPUS_WEIGHT * corpus_norm, 2)
    return out


async def channel_maturity(db: AsyncSession) -> dict[str, float]:
    """Blended (corpus × seed) channel maturity per material label, for materials present in the corpus.
    Cached for _TTL_SECONDS. Best-effort: on any error returns {} so callers fall back to the seed axis."""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _TTL_SECONDS:
        return _cache
    try:
        _cache = await _compute(db)
        _cache_at = now
    except Exception:  # noqa: BLE001 — presentational axis; never break the caller on it
        return _cache or {}
    return _cache

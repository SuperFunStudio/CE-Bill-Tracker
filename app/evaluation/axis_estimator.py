"""Estimate a material's map axes with the LLM, for materials outside the seed table.

The seed table (MATERIAL_PROFILES) covers the ~16 materials EPR law usually targets, each with a sourced
$/tonne value and a corpus-derived channel. A bill about something else — say marine gear, mining
tailings, or a novel composite — otherwise falls to a fixed "assume critical-mass" default. This asks a
cheap model to place the material on the same three axes (recoverable value, dispersion, channel maturity)
so the position is reasoned from the material's economics rather than defaulted.

Value is still expressed as $/tonne and pushed through the SAME log-normalization as the seed table, so an
estimated point sits on the same scale as the grounded ones. Best-effort: any failure returns None and the
caller falls back to the fixed default.
"""
from __future__ import annotations

import json

import anthropic
import structlog

from app.config import settings
from app.evaluation.strength import (
    Positioning,
    _REGIME_RATIONALE,
    regime_for_axes,
    value_density_from_usd,
)
from app.schemas import RegimeAxes

log = structlog.get_logger()

# A small judgment task — Haiku is enough and keeps the estimate cheap relative to the Sonnet extraction.
_MODEL = "claude-haiku-4-5-20251001"
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=30.0, max_retries=1)

_SYSTEM = """\
You estimate where a material sits in a circular-economy framework, to decide which policy intervention \
its economics demand. Two regimes:
- INCREMENTAL-VIABLE: high recoverable value AND an established reverse channel — the material already \
circulates on its own economics (lead-acid batteries, aluminium, precious metals). Legislation only has \
to internalize the externality.
- CRITICAL-MASS-REQUIRED: low value and/or dispersed with no channel — collection unit-economics never \
close below near-total coverage, so a law must engineer collection + PRO financing + design intervention \
at once (textiles, footwear, flexible film).
Judge the material on three axes and output STRICT JSON only."""

_USER = """\
Material (covered products of a bill): {products}
Bill title: {title}

Estimate, as JSON only:
{{
  "material": "<short label, e.g. 'Fishing gear & nets'>",
  "value_usd_per_tonne": <approx recoverable secondary-material value per tonne, USD; hazardous/negative-value ~20>,
  "dispersion": <0..1, how thinly spread across many holders (0=concentrated, 1=every household)>,
  "channel_maturity": <0..1, how established the reverse/collection channel already is (0=none, 1=ubiquitous)>,
  "reasoning": "<one sentence>"
}}"""


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.5


async def estimate_positioning(covered_products: list[str], title: str | None) -> Positioning | None:
    products = ", ".join(covered_products or []) or (title or "")
    if not products.strip():
        return None
    try:
        resp = await _client.messages.create(
            model=_MODEL, max_tokens=400, temperature=0, system=_SYSTEM,
            messages=[{"role": "user", "content": _USER.format(products=products[:600], title=(title or "")[:200])}],
        )
        raw = resp.content[0].text.strip()
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except (anthropic.APIError, json.JSONDecodeError, ValueError, IndexError) as e:
        log.warning("axis_estimate_failed", error=str(e))
        return None

    value_density = value_density_from_usd(float(data.get("value_usd_per_tonne") or 300))
    dispersion, channel = _clamp01(data.get("dispersion")), _clamp01(data.get("channel_maturity"))
    regime = regime_for_axes(value_density, dispersion, channel)
    material = (data.get("material") or "").strip() or "the measure's covered products"
    return Positioning(
        regime=regime, material=material, confidence="estimated",
        axes=RegimeAxes(value_density=value_density, dispersion=dispersion, channel_maturity=channel),
        rationale=_REGIME_RATIONALE[regime],
    )

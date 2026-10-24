"""Butterfly-diagram STEP placement — where a bill sits on the Ellen MacArthur circular-economy diagram.

The steps are the diagram's nodes (Maintain, Reuse, Refurbish / remanufacture, Recycle, Recycled content,
Collection, Composting, Cascades, Farming, ...). A bill can sit at several. Like cycles.py this is
derived, not stored: it reads fields we already have (instrument_types, material_categories, adjacency,
the v5 compliance_details envelopes, title + ai_summary), so it costs no LLM call and can be recomputed.

Placement sources, strongest first:
  * instrument — the classifier's instrument_types (right_to_repair -> Maintain, epr -> Collection ...).
  * extraction — a compliance_details envelope whose verbatim quote shows the practice.
  * material   — a material tag that IS the step (agriculture -> Farming, biobased -> Feedstock).
  * keyword    — a reviewed keyword net over title + ai_summary (medium confidence).
  * by_products — rows promoted by the 2026-10-23 by-products scope rule (adjacency='by_products').

Decisions baked in (Kenny, 2026-10-23; see docs/METHODOLOGY_CE_DIAGRAM_PLAN.md):
  * Recycling / recovery TARGETS sit on Recycle. MINIMUM recycled content in new products is its own step
    (`content`), where the loop re-enters production. A pure collection rate stays with EPR collection.
  * The `remanufacturing` envelope also carries secondary-material (recycled content) targets, so
    status=present alone over-counts remanufacturing; it counts only when the quote names the practice.
  * Farm-equipment right to repair is repair law (Maintain), not Farming; solar/wind "farms" are
    decommissioning law.
  * Waste-to-energy is the out-of-scope energy_recovery bucket, never a step.
  * Share has no source: no sharing / product-as-a-service law was found in or out of scope.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# step id -> instruments that place a bill there directly.
INSTRUMENT_STEPS: dict[str, frozenset[str]] = {
    "maintain": frozenset({"right_to_repair"}),
    "reuse": frozenset({"deposit_return"}),
    "content": frozenset({"recycled_content"}),
    "collect": frozenset({"epr", "product_stewardship"}),
    "leak": frozenset({"disposal_ban"}),
    "parts": frozenset({"chemical_restriction"}),
    "service": frozenset({"labeling"}),
    "compost": frozenset({"organics_diversion"}),
}

MATERIAL_STEPS: dict[str, frozenset[str]] = {
    "farm": frozenset({"agriculture"}),
    "extract": frozenset({"biobased"}),
    "regen": frozenset({"biodiversity"}),
}

KEYWORD_STEPS: dict[str, re.Pattern] = {k: re.compile(v, re.I) for k, v in {
    "farm": r"\bagricultur\w*|\bfarm(s|ing|land|er|ers)?\b|\bcrops?\b|livestock|fisher(y|ies)|forestry|aquacultur",
    "regen": r"regenerat\w* (agricultur|econom|farm|practice|grazing)|soil (health|carbon|organic matter|amendment)"
             r"|healthy soils|cover crop|carbon farming|biochar|biodiversit|restor\w* (soil|ecosystem|habitat)",
    "extract": r"bio-?based|biorefin|bioplastic|biopolymer|biochemical|biomanufactur|bio-?feedstock",
    "cascade": r"by-?products?\b|food (donation|rescue|recovery)|donated food|edible food|surplus food|animal feed|cascad",
    "refurb": r"refurbish|remanufactur|recondition|repurpos|upcycl|second[- ]life",
    "share": r"shar(e|ing) (economy|platform|scheme)|product[- ]as[- ]a[- ]service|lending librar|tool librar",
    "compost": r"compost|anaerobic digest|biomethane|food scraps?|organic waste",
}.items()}
_NOT_FARM = re.compile(r"(wind|solar|energy|server) farm", re.I)
_REPAIR = re.compile(r"repair", re.I)

# The remanufacturing quote must name the practice (multilingual: the extraction quotes the original text).
REMAN_QUOTE = re.compile(
    r"remanufactur|refurbish|recondition|repurpos|upcycl|second[- ]life|prepar\w* for re-?use|re-?us(e|ed|ing)\b"
    r"|réemploi|réutilis|reconditionn|issues? de l.économie circulaire|wiederverwend|instandsetz|aufbereit"
    r"|再製造|再制造|再生部品|リユース|再使用|återanvänd|uudelleenkäyt|atkārtot|yeniden kullan|reutiliz|riutilizz|hergebruik",
    re.I)
# A collection target is a RECYCLING target only when its quote names recycling or recovery.
RECYCLING_QUOTE = re.compile(
    r"recycl|recover|recuper|valori|verwert|再資源|再商品化|再生利用|reciclaj|recicla|recykl|odzysk|riciclo|riciclagg"
    r"|återvinn|kierrät|hyödynt|pārstrād|geri dönüşüm|geri kazan|hergebruik|nuttige toepassing|genanvend", re.I)
# A secondary-material target is a CONTENT rule when it is about what new products must contain.
CONTENT_TARGET = re.compile(r"content|contain|incorporat|in new products|teneur|rezyklatanteil|recyclaatgehalte"
                            r"|再生材料|再生プラスチック", re.I)


def _env(details: Mapping | None, name: str) -> Mapping:
    env = (details or {}).get(name)
    return env if isinstance(env, Mapping) else {}


def _present(env: Mapping) -> bool:
    return env.get("status") == "present"


def remanufacturing_evidence(details: Mapping | None) -> str | None:
    """The quote that places a bill on Refurbish / remanufacture, or None."""
    env = _env(details, "remanufacturing")
    if not _present(env):
        return None
    quote, std = env.get("source_excerpt") or "", env.get("refurb_standard")
    if REMAN_QUOTE.search(quote) or (std and std != "null"):
        return quote or std
    return None


def _extraction_steps(details: Mapping | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if remanufacturing_evidence(details):
        out["refurb"] = "extraction"
    if _present(_env(details, "recycled_content")):
        out["content"] = "extraction"
    ct = _env(details, "collection_targets")
    if _present(ct) and (RECYCLING_QUOTE.search(ct.get("source_excerpt") or "")
                         or any(isinstance(t, Mapping) and t.get("basis") == "value_recovered"
                                for t in ct.get("targets") or [])):
        out["recycle"] = "extraction"
    reman = _env(details, "remanufacturing")
    for t in reman.get("secondary_material_targets") or []:
        if not isinstance(t, Mapping):
            continue
        if CONTENT_TARGET.search(f"{t.get('material') or ''} {reman.get('source_excerpt') or ''}"):
            out.setdefault("content", "extraction")
        else:
            out.setdefault("recycle", "extraction")
    return out


def butterfly_steps(bill: Mapping[str, Any]) -> dict[str, str]:
    """step id -> how the bill was placed ('instrument' | 'extraction' | 'material' | 'keyword' | 'by_products').

    `bill` needs: title, ai_summary, instrument_types, material_categories, adjacency, compliance_details
    (a Bill ORM row works through a small adapter, or pass a dict)."""
    insts = set(bill.get("instrument_types") or [])
    mats = set(bill.get("material_categories") or [])
    title = bill.get("title") or ""
    blob = f"{title} {bill.get('ai_summary') or ''}"
    out: dict[str, str] = {}

    for step, needed in INSTRUMENT_STEPS.items():
        if insts & needed:
            out[step] = "instrument"
    for step, how in _extraction_steps(bill.get("compliance_details")).items():
        out.setdefault(step, how)
    for step, needed in MATERIAL_STEPS.items():
        if mats & needed:
            out.setdefault(step, "material")
    for step, rx in KEYWORD_STEPS.items():
        if step in out:
            continue
        if step == "farm":
            # Title only: summaries mention farms in passing.
            if not rx.search(title) or _NOT_FARM.search(title) or "right_to_repair" in insts or _REPAIR.search(title):
                continue
        elif not rx.search(blob):
            continue
        out[step] = "keyword"
    if bill.get("adjacency") == "by_products":
        out["cascade"] = "by_products"
    return out

import json
import re
from dataclasses import dataclass

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger()

SONNET_MODEL = "claude-sonnet-4-6"

# Bump when the extraction schema changes so backfills can select "bills below current version" and
# re-run only what's stale. v2 added the eco_modulation / recycled_content / penalties envelopes;
# v3 added collection_targets / pro_structure / bans_restrictions; v4 added fee_amounts / labeling;
# v5 added repairability / reuse_refill / digital_product_passport / remanufacturing (one LLM pass
# fills all twelve). See docs/DIMENSION_EXPANSION_PLAN.md.
EXTRACTION_VERSION = 5

# Region code -> human label injected into the prompts, so the extractor frames the measure for the
# right jurisdiction (member-state national law extracts richly even in its native language — German
# VerpackG, Swedish/Dutch/Polish ordinances — but only if it knows the country, not a bare code).
# Covers every jurisdiction currently ingested (see app/ingestion/foreign.py adapters). An unknown
# code falls back to the raw code rather than mislabeling foreign law "United States".
REGION_LABELS = {
    "US": "United States", "EU": "European Union", "UK": "United Kingdom",
    "FR": "France", "JP": "Japan", "PL": "Poland", "DE": "Germany", "SE": "Sweden",
    "NL": "Netherlands", "ES": "Spain", "FI": "Finland", "IE": "Ireland", "CL": "Chile",
    "DK": "Denmark", "CH": "Switzerland", "SI": "Slovenia", "BR": "Brazil", "AT": "Austria",
    "LU": "Luxembourg", "LV": "Latvia", "SK": "Slovakia", "LT": "Lithuania", "CZ": "Czechia",
    "EE": "Estonia", "KR": "South Korea", "NO": "Norway", "BE": "Belgium", "IT": "Italy",
    "PT": "Portugal", "CA": "Canada", "AU": "Australia", "CN": "China",
}


def region_label(region: str | None) -> str:
    code = (region or "US").upper()
    return REGION_LABELS.get(code, code)


# Anchors marking the EPR / circular-economy core of a large omnibus act. select_text_window uses
# these so a measure that exceeds the model's text budget is windowed around its compliance-relevant
# sections instead of blindly truncated from the top — which on the UK Environment Act 2021 (687K
# chars) captured only governance preamble and missed every EPR/DRS provision. See the foreign-corpus
# extraction post-mortem.
_BASE_ANCHORS = [
    r"producer responsibility", r"extended producer", r"product stewardship", r"packaging waste",
    r"packaging", r"deposit return", r"deposit scheme", r"deposit and return", r"take[-\s]?back",
    r"recycled content", r"right to repair", r"single[-\s]use plastic", r"eco[-\s]?modulat",
    r"collection target", r"recycling target", r"stewardship",
    # v5 envelope anchors so large omnibus acts window onto these provisions too.
    r"repairab", r"repair index", r"durabilit", r"planned obsolescence", r"reuse", r"refill",
    r"reusable", r"product passport", r"traceabilit", r"remanufactur", r"refurbish",
]
_BASE_ANCHOR_RE = re.compile(r"\b(?:" + "|".join(_BASE_ANCHORS) + r")\b", re.IGNORECASE)

# The English anchors above never fire on native-language law (French REP decrees, Japan's 容器包装
# recycling act, China's 循环经济 law), so a large non-English omnibus act windowed to preamble and
# lost its obligations. Sonnet itself reads native text fine — only THIS regex-based windowing needed
# translating. Native EPR/circular-economy terms keyed by the language the source stores text in (see
# app/ingestion/foreign.py). CJK terms carry no word boundaries, so native anchors match without \b.
_NATIVE_ANCHORS = {
    "fr": ["responsabilité élargie", "déchets d'emballages", "éco-modulation", "consigne",
           "filière REP", "reprise", "collecte", "recyclage",
           "réparabilité", "indice de réparabilité", "réemploi", "réutilisation", "reconditionn"],
    "de": ["Herstellerverantwortung", "Produktverantwortung", "Verpackung", "Rücknahme",
           "Pfand", "Mehrweg", "Recycling", "Rezyklat"],
    "es": ["responsabilidad ampliada", "envases", "residuos", "depósito", "reciclaje", "recogida"],
    "nl": ["producentenverantwoordelijkheid", "verpakking", "statiegeld", "inzameling", "recycling"],
    "sv": ["producentansvar", "förpackningar", "pant", "insamling", "återvinning"],
    "pl": ["odpowiedzialność producenta", "opakowania", "kaucja", "zbiórka", "recykling"],
    "pt": ["responsabilidade compartilhada", "logística reversa", "embalagens", "resíduos", "reciclagem"],
    "it": ["responsabilità estesa del produttore", "imballaggi", "cauzione", "raccolta", "riciclaggio"],
    "cs": ["odpovědnost výrobců", "obaly", "zálohování", "recyklace"],
    "ja": ["生産者責任", "拡大生産者責任", "容器包装", "デポジット", "リサイクル", "回収", "再商品化"],
    "zh": ["生产者责任", "生产者责任延伸", "包装", "回收", "押金", "循环经济", "再生"],
    "ko": ["생산자책임", "생산자책임재활용", "포장", "재활용", "회수", "보증금"],
}
# Region code -> stored-text language (English regions omitted; they use the base anchors alone).
# CH is trilingual (de/fr/it), handled explicitly in _anchor_re.
_REGION_LANG = {
    "FR": "fr", "DE": "de", "AT": "de", "ES": "es", "CL": "es", "NL": "nl", "SE": "sv",
    "PL": "pl", "BR": "pt", "IT": "it", "CZ": "cs", "JP": "ja", "CN": "zh", "KR": "ko",
}


def _anchor_re(region: str | None) -> re.Pattern:
    """English anchors plus native EPR terms for the region's language. English/unknown-language
    regions get the base pattern (a fast path and identical to the previous behavior)."""
    code = (region or "US").upper()
    if code == "CH":
        native = _NATIVE_ANCHORS["de"] + _NATIVE_ANCHORS["fr"] + _NATIVE_ANCHORS["it"]
    else:
        native = _NATIVE_ANCHORS.get(_REGION_LANG.get(code, ""), [])
    if not native:
        return _BASE_ANCHOR_RE
    eng = r"\b(?:" + "|".join(_BASE_ANCHORS) + r")\b"
    nat = "(?:" + "|".join(re.escape(t) for t in native) + ")"  # no \b — CJK has no word boundaries
    return re.compile(eng + "|" + nat, re.IGNORECASE)


def select_text_window(
    full_text: str, region: str | None = None, max_chars: int = 40000, head_chars: int = 4000
) -> str:
    """Pick the slice of bill text to send to the extractor.

    Small measures (<= max_chars) go whole. For larger ones, keep a head slice (title / scope /
    definitions — usually front-loaded) plus a window starting at the first EPR anchor, so omnibus
    acts surface their actual compliance provisions rather than just the preamble. Anchors are
    language-aware (see _anchor_re) so native-language law windows on its obligations, not preamble.
    If no anchor is found, fall back to the leading max_chars (pure EPR laws front-load obligations —
    e.g. German VerpackG extracted fully from its first 12K).
    """
    if len(full_text) <= max_chars:
        return full_text
    head = full_text[:head_chars]
    budget = max_chars - head_chars
    m = _anchor_re(region).search(full_text, head_chars)
    if not m:
        return full_text[:max_chars]
    start = max(head_chars, m.start() - 1000)
    body = full_text[start : start + budget]
    return f"{head}\n[...]\n{body}"


SYSTEM_PROMPT_TEMPLATE = """\
You are a compliance specialist analyzing {region} EPR / circular-economy legislation. \
Extract all compliance-relevant details that would matter to a producer, manufacturer, brand owner, or importer. \
Be precise about dates, thresholds, and obligations. If a detail is not specified in the measure, omit that key. \
The measure's text may be in its national language (e.g. French, German, Japanese, Chinese); \
read it in that language and emit all JSON keys and values in English, EXCEPT source_excerpt fields, \
which must be verbatim quotes in the original language.\
"""

USER_TEMPLATE = """\
Extract compliance details from this measure. Respond with ONLY valid JSON — no prose, no markdown.

Jurisdiction: {state}
Bill: {bill_number}
Title: {title}

Full text:
{full_text}

Return this JSON structure. Omit optional keys where data is absent, but ALWAYS include the twelve
envelope fields (eco_modulation, recycled_content, penalties, collection_targets, pro_structure,
bans_restrictions, fee_amounts, labeling, repairability, reuse_refill, digital_product_passport,
remanufacturing) with an explicit "status":
  - "present": the measure addresses this; fill in the details and a verbatim source_excerpt.
  - "absent": you read the text and it does not address this (do NOT guess — only after reading).
  - "not_applicable": the concept cannot apply to this kind of measure.
{{
  "covered_products": ["<description of covered products/materials>"],
  "producer_definition": "<who is a covered producer>",
  "producer_obligations": ["<each obligation as a string>"],
  "deadlines": [
    {{"type": "<registration|reporting|compliance|fee_payment|other>", "date": "<YYYY-MM-DD or null>", "description": "<what is due>"}}
  ],
  "fees": {{
    "structure": "<per_unit|per_ton|flat|eco_modulated|unknown>",
    "details": "<description of fee structure>"
  }},
  "exemptions": ["<each exemption>"],
  "pro_requirements": "<PRO/stewardship organization requirements>",
  "enforcement": {{
    "agency": "<enforcing agency>",
    "penalties": "<penalty description>"
  }},
  "effective_date": "<YYYY-MM-DD or null>",
  "reporting_requirements": "<annual/periodic reporting obligations>",
  "preemption_risk": "<Low|Medium|High>",
  "preemption_notes": "<any preemption-related provisions or risks>",
  "related_bills": ["<e.g. CA-SB-343>"],
  "implementation_phases": ["<phase descriptions with dates>"],
  "eco_modulation": {{
    "status": "<present|absent|not_applicable>",
    "criteria": ["<design attributes that raise/lower fees: recyclability, recycled_content, reusability, toxicity/PFAS, etc.>"],
    "source_excerpt": "<verbatim quote from the text, in the original language>"
  }},
  "recycled_content": {{
    "status": "<present|absent|not_applicable>",
    "minimums": [{{"material": "<e.g. PET beverage bottles>", "percent": <number>, "by_year": "<YYYY or null>"}}],
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "penalties": {{
    "status": "<present|absent|not_applicable>",
    "max_amount": <number or null>,
    "currency": "<ISO 4217 code, e.g. USD, EUR, JPY, CNY>",
    "per": "<violation|day|unit|null>",
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "collection_targets": {{
    "status": "<present|absent|not_applicable>",
    "targets": [{{"material": "<e.g. all packaging, WEEE, beverage containers>", "percent": <number or null>, "by_year": "<YYYY or null>", "basis": "<weight|units|value_recovered|material_specific|unspecified>"}}],
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "pro_structure": {{
    "status": "<present|absent|not_applicable>",
    "model": "<single_pro|competitive_pros|government_run|individual|unspecified>",
    "needs_assessment": <true|false>,
    "named_pros": ["<any named stewardship organization>"],
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "bans_restrictions": {{
    "status": "<present|absent|not_applicable>",
    "items": [{{"target": "<e.g. single-use plastic bags, PFAS in packaging>", "type": "<sales_ban|material_restriction|design_ban>", "effective_date": "<YYYY or null>"}}],
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "fee_amounts": {{
    "status": "<present|absent|not_applicable>",
    "rates": [{{"basis": "<per_ton|per_unit|flat|eco_modulated|percent_revenue|unspecified>", "amount": <number or null>, "currency": "<ISO 4217, e.g. USD, EUR>", "material": "<what the rate applies to, or null>"}}],
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "labeling": {{
    "status": "<present|absent|not_applicable>",
    "requirements": [{{"type": "<recyclability|material_id|disposal_instructions|deposit_mark|reusability|other>", "on_pack": <true or false>, "detail": "<what must be labeled>"}}],
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "repairability": {{
    "status": "<present|absent|not_applicable>",
    "has_repair_score": <true or false>,
    "score_scheme": "<e.g. FR indice de réparabilité, EU repair index/scoring, durability score, or null>",
    "parts_availability_years": <number or null>,
    "manuals_required": <true or false>,
    "disassembly_required": <true or false>,
    "obsolescence_clause": <true or false>,
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "reuse_refill": {{
    "status": "<present|absent|not_applicable>",
    "targets": [{{"scope": "<e.g. beverage packaging, foodware, transport packaging>", "percent": <number or null>, "by_year": "<YYYY or null>"}}],
    "refill_infrastructure_required": <true or false>,
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "digital_product_passport": {{
    "status": "<present|absent|not_applicable>",
    "dpp_required": <true or false>,
    "data_fields": ["<e.g. material_composition, provenance, repair_info, recycled_content, carbon_footprint>"],
    "carrier": "<QR|RFID|barcode|unspecified|null>",
    "effective_year": "<YYYY or null>",
    "source_excerpt": "<verbatim quote, original language>"
  }},
  "remanufacturing": {{
    "status": "<present|absent|not_applicable>",
    "remanufacture_allowed": <true or false>,
    "refurb_standard": "<name/description of any refurbishment or remanufacturing standard, or null>",
    "secondary_material_targets": [{{"material": "<what the secondary/recovered-material target applies to>", "percent": <number or null>, "by_year": "<YYYY or null>"}}],
    "source_excerpt": "<verbatim quote, original language>"
  }}
}}
"""


@dataclass
class SonnetResult:
    covered_products: list[str]
    producer_definition: str
    producer_obligations: list[str]
    deadlines: list[dict]
    fees: dict
    exemptions: list[str]
    pro_requirements: str
    enforcement: dict
    effective_date: str | None
    reporting_requirements: str
    preemption_risk: str
    preemption_notes: str
    related_bills: list[str]
    implementation_phases: list[str]
    # v2 envelopes — each carries status (present|absent|not_applicable) + a verbatim source_excerpt,
    # so a filter/chart can tell "measure does not eco-modulate" apart from "not yet extracted".
    eco_modulation: dict
    recycled_content: dict
    penalties: dict
    collection_targets: dict
    pro_structure: dict
    bans_restrictions: dict
    fee_amounts: dict
    labeling: dict
    # v5 envelopes — repair/durability, reuse & refill, digital product passport, remanufacturing.
    repairability: dict
    reuse_refill: dict
    digital_product_passport: dict
    remanufacturing: dict
    extraction_version: int
    raw_json: dict


class SonnetExtractor:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None, model: str = SONNET_MODEL):
        # model is parameterized (default Sonnet, unchanged) so a Haiku pass can be run for the
        # cost/quality A/B and the hybrid triage (Haiku presence-detect → Sonnet precise extract).
        self._model = model
        # 120s timeout (extraction is heavier than Haiku classification, so longer than its 60s) so a
        # hung call fails fast instead of pinning the caller — critically, the classification cycle
        # holds a DB transaction across this call, and an unbounded hang there strands a connection
        # idle-in-transaction holding bills locks (see ClassificationPipeline.run Stage 3).
        # max_retries=4 (was 1): bulk backfills over a flaky network saw ~16% of calls fail with a
        # transient APIConnectionError; the SDK's exponential backoff absorbs those blips instead of
        # dropping the bill. The live classification pipeline holds a DB txn across this call, but the
        # 120s timeout still bounds each attempt, so a few retries can't strand a connection for long.
        self._client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key, timeout=120.0, max_retries=4
        )

    def build_params(
        self, state: str, bill_number: str, title: str, full_text: str, region: str = "US",
    ) -> dict:
        """The messages.create kwargs for one bill — factored out so the Batch API can submit the
        SAME request (model/prompt/schema) without a live call. See scripts/extract_dimensions_batch.py."""
        prompt = USER_TEMPLATE.format(
            state=state,
            bill_number=bill_number or "Unknown",
            title=title or "",
            # ~10K tokens of text, keyword-windowed for large omnibus acts (see select_text_window).
            # region drives language-aware anchors so native-language law windows on its obligations.
            full_text=select_text_window(full_text, region=region),
        )
        return {
            "model": self._model,
            "max_tokens": 16000,  # compliance JSON for large bills overflows a smaller budget; grew with
            # each envelope wave (4000→8000 v2, →12000 v3, →16000 v4/eight, →v5 twelve) to curb truncation
            "temperature": 0,
            "system": SYSTEM_PROMPT_TEMPLATE.format(region=region_label(region)),
            "messages": [{"role": "user", "content": prompt}],
        }

    def parse_response(self, raw: str, bill_number: str = "") -> SonnetResult:
        """Parse a model response (live or batched) into a SonnetResult. Tolerant of prose-wrapped or
        truncated JSON, exactly as the live path was."""
        raw = (raw or "").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            try:
                data = json.loads(match.group()) if match else {}
            except json.JSONDecodeError:
                # Truncated or malformed JSON (e.g. response cut off mid-object).
                log.warning("sonnet_json_parse_failed", bill_number=bill_number, raw=raw[:200])
                data = {}

        # Stamp the schema version only on a real parse, so a failed extraction stays "unversioned"
        # and a backfill re-runs it rather than treating an empty result as done.
        if data:
            data["extraction_version"] = EXTRACTION_VERSION

        return SonnetResult(
            covered_products=data.get("covered_products", []),
            producer_definition=data.get("producer_definition", ""),
            producer_obligations=data.get("producer_obligations", []),
            deadlines=data.get("deadlines", []),
            fees=data.get("fees", {}),
            exemptions=data.get("exemptions", []),
            pro_requirements=data.get("pro_requirements", ""),
            enforcement=data.get("enforcement", {}),
            effective_date=data.get("effective_date"),
            reporting_requirements=data.get("reporting_requirements", ""),
            preemption_risk=data.get("preemption_risk", "Low"),
            preemption_notes=data.get("preemption_notes", ""),
            related_bills=data.get("related_bills", []),
            implementation_phases=data.get("implementation_phases", []),
            eco_modulation=data.get("eco_modulation", {}),
            recycled_content=data.get("recycled_content", {}),
            penalties=data.get("penalties", {}),
            collection_targets=data.get("collection_targets", {}),
            pro_structure=data.get("pro_structure", {}),
            bans_restrictions=data.get("bans_restrictions", {}),
            fee_amounts=data.get("fee_amounts", {}),
            labeling=data.get("labeling", {}),
            repairability=data.get("repairability", {}),
            reuse_refill=data.get("reuse_refill", {}),
            digital_product_passport=data.get("digital_product_passport", {}),
            remanufacturing=data.get("remanufacturing", {}),
            extraction_version=data.get("extraction_version", 0),
            raw_json=data,
        )

    async def extract(
        self, state: str, bill_number: str, title: str, full_text: str, region: str = "US",
    ) -> SonnetResult:
        params = self.build_params(state, bill_number, title, full_text, region)
        resp = await self._client.messages.create(**params)
        return self.parse_response(resp.content[0].text, bill_number=bill_number)

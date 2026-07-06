"""'Evaluate a Bill' (Pro) — score a pasted/uploaded measure by whether it carries the mechanisms its
target material's economics require (see app/evaluation/strength.py for the load-bearing idea).

Flow: the SAME SonnetExtractor that analyzes the corpus reads the pasted text into the eight compliance
envelopes; then deterministic rules POSITION the material into a regime and SCORE the bill against that
regime's baseline. Reusing the extractor means an uploaded draft is measured on exactly the same axes as
every tracked bill, so the comparison is apples-to-apples.
"""
# NOTE: no `from __future__ import annotations` — slowapi's @limiter.limit wrapper introspects the
# signature at runtime and stringized annotations don't mix with it (see app/api/billing.py).
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthedUser, require_pro
from app.classification.sonnet_extractor import SonnetExtractor
from app.database import get_db
from app.evaluation.axis_estimator import estimate_positioning
from app.evaluation.channel import channel_maturity
from app.evaluation.corpus import cross_check
from app.evaluation.strength import evaluate_strength, match_material_label, material_map
from app.ratelimit import limiter
from app.schemas import EvaluateRequest, EvaluateResponse, MaterialMapPoint

router = APIRouter(prefix="/evaluate", tags=["evaluate"])
log = structlog.get_logger()

# One shared extractor (its own AsyncAnthropic client with a 120s timeout — see SonnetExtractor).
_extractor = SonnetExtractor()

MIN_CHARS = 200        # below this there aren't enough substantive provisions to extract meaningfully
MAX_CHARS = 200_000    # hard cap before the extractor's own keyword-windowing; guards against abuse


@router.post("/bill", response_model=EvaluateResponse)
@limiter.limit("10/hour")  # a heavy Sonnet extraction per call — tighter than the read endpoints
async def evaluate_bill(
    request: Request,
    body: EvaluateRequest,
    _user: AuthedUser = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
) -> EvaluateResponse:
    text = (body.text or "").strip()
    if len(text) < MIN_CHARS:
        raise HTTPException(
            status_code=422,
            detail="Paste more of the bill text — include the substantive provisions (targets, fees, PRO, "
            "obligations), not just the title.",
        )
    result = await _extractor.extract(
        state=body.jurisdiction or "Draft",
        bill_number="draft",
        title=body.title or "",
        full_text=text[:MAX_CHARS],
        region=(body.region or "US"),
    )
    if not result.raw_json:
        raise HTTPException(status_code=502, detail="Could not extract compliance details from that text. "
                            "Try pasting a cleaner copy of the bill's operative sections.")
    # For materials outside the seed table, estimate the map axes with the LLM instead of the fixed
    # critical-mass fallback (best-effort — a failed estimate falls back to the default positioning).
    positioning = None
    if match_material_label(" ".join([*(result.covered_products or []), body.title or ""])) is None:
        positioning = await estimate_positioning(result.covered_products, body.title)

    resp = evaluate_strength(result, title=body.title, jurisdiction=body.jurisdiction, positioning=positioning)
    # Overlay the corpus-derived channel maturity for this material onto the seed axis (best-effort).
    channel = (await channel_maturity(db)).get(resp.regime.material)
    if channel is not None:
        resp.regime.axes.channel_maturity = channel
    # Ground the draft against enacted laws in the same regime (which mechanisms they carried, what
    # landed). Best-effort: a cross-check failure must not sink the (already-computed) fit score.
    try:
        resp.corpus = await cross_check(
            db, result, resp.requirements, resp.regime.key, resp.regime.material
        )
    except Exception:  # noqa: BLE001 — corpus is additive; never fail the whole evaluation on it
        log.warning("evaluate_corpus_crosscheck_failed", exc_info=True)
    return resp


@router.get("/material-map", response_model=list[MaterialMapPoint])
async def get_material_map(db: AsyncSession = Depends(get_db)) -> list[MaterialMapPoint]:
    """The value×dispersion×channel map of known materials + their regime — reference data for the
    material-position viz. Open (no auth); the value axis is grounded in $/tonne and the channel axis is
    overlaid with corpus-derived maturity where the corpus covers the material."""
    channel = await channel_maturity(db)
    points = material_map()
    for p in points:
        if p["material"] in channel:
            p["channel_maturity"] = channel[p["material"]]
    return [MaterialMapPoint(**p) for p in points]

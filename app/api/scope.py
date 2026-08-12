"""Anonymous personalization scope — the signed-out half of /me/settings.

Personalization used to be account-only, which meant the site's largest and most engaged cohort
(returning visitors who never sign in) generated no record of what they came for. This endpoint lets
a signed-out reader's scope reach the database against a browser-minted id, so "what do anonymous
returners actually care about" becomes a query instead of a guess.

Security posture — this is an UNAUTHENTICATED write, so it is deliberately boring:
  * Rate limited per IP, like the other public POST (app/api/access.py).
  * Accepts only closed vocabularies (two-letter state codes, known material slugs) and booleans.
    Nothing free-text, so it cannot become an anonymous storage/PII channel.
  * Unknown slugs are dropped, not rejected — a stale client shipping one unrecognised material
    shouldn't cost us the rest of an otherwise valid signal.
  * Upsert on client_id, so the table is bounded by distinct browsers rather than by request count.
  * Write-only. There is no GET: the client already holds this in localStorage, so a read endpoint
    would add an enumeration surface (guess a UUID, learn a stranger's interests) for no product gain.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AnonScope
from app.ratelimit import limiter
from app.schemas import AnonScopeUpsert

router = APIRouter(prefix="/anon-scope", tags=["scope"])

# client_id shape is enforced by AnonScopeUpsert's validator (app/schemas.py), so a malformed id is
# a 422 at request parsing with the field named, before this module runs.

# Mirrors MATERIAL_CATEGORIES in the frontend filters and the classifier's enum
# (app/classification/federal_classifier.py). Kept here as a literal set so an unauthenticated write
# can never introduce a new value.
_MATERIALS = {
    "plastic_packaging", "paper_packaging", "glass", "metals", "electronics", "batteries",
    "paint", "carpet", "mattresses", "tires", "vehicles", "construction", "furniture",
    "used_oil", "pharmaceuticals", "solar_panels", "textiles", "organics", "biobased",
    "agriculture", "hazardous_materials", "water", "biodiversity", "microplastics",
    "pesticides", "compostable_packaging", "printed_paper", "other",
}

# Generous caps: 51 US states + DC is the real ceiling for states, and nobody meaningfully selects
# every material. These bound the row size rather than express a product rule.
_MAX_STATES = 60
_MAX_MATERIALS = 40


def _clean_states(raw: list[str]) -> list[str]:
    """Two-letter codes, uppercased, deduped, order preserved."""
    out: list[str] = []
    for s in raw[:_MAX_STATES]:
        code = str(s).strip().upper()
        if len(code) == 2 and code.isalpha() and code not in out:
            out.append(code)
    return out


def _clean_materials(raw: list[str]) -> list[str]:
    out: list[str] = []
    for m in raw[:_MAX_MATERIALS]:
        slug = str(m).strip().lower()
        if slug in _MATERIALS and slug not in out:
            out.append(slug)
    return out


@router.post("", status_code=204)
@limiter.limit("20/minute")
async def upsert_anon_scope(
    request: Request,
    payload: AnonScopeUpsert,
    db: AsyncSession = Depends(get_db),
):
    """Record (or update) an anonymous visitor's scope. Returns 204 — the client is the source of
    truth for its own scope and has nothing to learn from the response."""
    client_id = payload.client_id
    states = _clean_states(payload.states)
    materials = _clean_materials(payload.material_categories)

    # ON CONFLICT keeps this a single round trip and makes concurrent writes from the same browser
    # (two tabs) last-write-wins instead of raising on the unique index.
    stmt = pg_insert(AnonScope).values(
        client_id=client_id,
        states=states,
        material_categories=materials,
        configured=payload.configured,
        scoped=payload.scoped,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[AnonScope.client_id],
        set_={
            "states": stmt.excluded.states,
            "material_categories": stmt.excluded.material_categories,
            "configured": stmt.excluded.configured,
            "scoped": stmt.excluded.scoped,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()

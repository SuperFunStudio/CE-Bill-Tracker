"""Serve the full Design Guide — Pro subscribers only.

The Free teaser ships in the dashboard bundle (src/data/designGuideTeaser.ts). The full rendered
guide (app/static/design_guide.html) is the Pro deliverable, gated behind require_pro so only an
authenticated account with a live Pro subscription can fetch it. See gating-and-monetization-plan.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.api.auth import AuthedUser, require_pro

router = APIRouter(prefix="/design-guide", tags=["design-guide"])

_GUIDE_PATH = Path(__file__).resolve().parents[1] / "static" / "design_guide.html"


@router.get("/full", response_class=HTMLResponse)
async def full_guide(_user: AuthedUser = Depends(require_pro)) -> HTMLResponse:
    if not _GUIDE_PATH.exists():
        raise HTTPException(status_code=404, detail="guide not available")
    return HTMLResponse(_GUIDE_PATH.read_text(encoding="utf-8"))

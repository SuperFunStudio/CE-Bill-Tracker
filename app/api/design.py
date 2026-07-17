"""Serve the full Design Guide — members with the design_guide capability (Student and up).

The Free teaser ships in the dashboard bundle (src/data/designGuideTeaser.ts). The full rendered
guide (app/static/design_guide.html) is a member deliverable, gated behind the design_guide capability
so any Student/Research/Pro/Enterprise member (see app/api/auth.py PLAN_CAPS) can fetch it.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.api.auth import CAP_DESIGN_GUIDE, AuthedUser, require_capability

router = APIRouter(prefix="/design-guide", tags=["design-guide"])

_GUIDE_PATH = Path(__file__).resolve().parents[1] / "static" / "design_guide.html"


@router.get("/full", response_class=HTMLResponse)
async def full_guide(_user: AuthedUser = Depends(require_capability(CAP_DESIGN_GUIDE))) -> HTMLResponse:
    if not _GUIDE_PATH.exists():
        raise HTTPException(status_code=404, detail="guide not available")
    return HTMLResponse(_GUIDE_PATH.read_text(encoding="utf-8"))

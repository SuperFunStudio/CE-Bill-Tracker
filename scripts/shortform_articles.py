"""Distill EXISTING Atlas answers into SHORT-form, publishable article drafts — the quick sibling of
the long-form /research/drafts pipeline (app/api/research.create_content_draft).

Where that endpoint stitches whole thread turns into a full Substack post, this crops each answer to its
sharpest point. Two shapes:

  crop  (default) — one research turn -> the single most impactful finding, tightened to ~150-220 words.
  pair            — one turn -> the 2 or 4 cited bills that form the most illuminating contrast, written
                    up as a ~200-word "side by side".

Each result lands as a `content_drafts` row (status='staged') with its [STATE BILL_NUMBER] citations
already rewritten to /?bill=<id> deep links — so it shows up in the admin drafts queue and publishes via
the SAME POST /research/drafts/{id}/publish (mints /p/?token=). Nothing here auto-publishes.

Reuses the real editorial machinery (RESEARCH_MODEL, _HOUSE_VOICE, link_citations, _ref_map_for,
_cited_ids, _slugify) so the voice + citation linking match the long-form flow exactly.

Run against PROD via the Cloud SQL proxy (127.0.0.1:5436), same recipe as scripts/corpus_survey_ask.py:

    PW=$(gcloud secrets versions access latest --secret=SIGNALSCOUT_DB_PASSWORD --project=ce-bill-tracker)
    AK=$(gcloud secrets versions access latest --secret=ANTHROPIC_API_KEY --project=ce-bill-tracker)
    DATABASE_URL="postgresql://signalscout:$PW@127.0.0.1:5436/signalscout" ANTHROPIC_API_KEY="$AK" \
        venv/Scripts/python.exe scripts/shortform_articles.py --mode crop --limit 5 --dry-run

Drop --dry-run to actually write the staged drafts. Select the source turns with --owner-uid / --session
/ --limit / --min-citations; --pair-size controls how many bills the pair mode contrasts.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402

# Canonical short-form distillation lives in the endpoint module, so the script + POST /research/drafts
# (mode=crop|pair) share ONE voice, prompt, and citation-linking path. See create_content_draft.
from app.api.research import (  # noqa: E402
    _candidate_bill_details,
    _cited_ids,
    _crop_editorialize,
    _pair_editorialize,
    _ref_map_for,
    _slugify,
    link_citations,
)
from app.database import AsyncSessionLocal  # noqa: E402
from app.models import ContentDraft, ResearchSession, ResearchTurn  # noqa: E402

OWNER_UID = "L8BeKGapUcPfK9IydeE2gu2kV7z2"  # kenny@superfun.studio (the seeded corpus-survey account)
CONCURRENCY = 3
PROGRESS = Path(__file__).parent.parent / "data" / "exports" / "shortform_articles_progress.jsonl"


def _log(rec: dict):
    line = json.dumps(rec, ensure_ascii=False)
    print(line, flush=True)
    with PROGRESS.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def _make_draft(mode: str, turn, pair_size: int) -> dict | None:
    """Build (but don't persist) one short-form draft from a research turn, via the SAME crop/pair
    distillation the /research/drafts endpoint uses. Returns the persist-ready field bag + a log record,
    or None if the turn can't produce a short-form article."""
    answer_text = (turn.answer or {}).get("text") or ""
    cited = _cited_ids(turn)
    ref = f"session={turn.session_id} seq={turn.seq}"

    if mode == "crop":
        if not answer_text.strip():
            return None
        data = await _crop_editorialize([(turn.question, answer_text)])
        link_ids = cited
    else:  # pair
        if len(cited) < pair_size:
            return None
        async with AsyncSessionLocal() as db:
            candidates = await _candidate_bill_details(db, cited[:8])  # top ~8, model picks the {n}
        data = await _pair_editorialize(turn.question, candidates, pair_size)
        link_ids = cited[:8]

    if not data:
        return {"ok": False, "ref": ref, "error": "llm_failed_or_too_few_bills"}

    # Deep-link the citation markers over the SAME ref map the long-form flow uses.
    async with AsyncSessionLocal() as db:
        ref_map = await _ref_map_for(db, link_ids)
    body_md = link_citations(str(data["body"]), ref_map)
    title = str(data["title"])[:300]
    return {
        "ok": True, "ref": ref, "mode": mode,
        "fields": dict(
            source_session_id=turn.session_id, source_seq=turn.seq,
            title=title, dek=(str(data["dek"]) if data.get("dek") else None),
            body_markdown=body_md, status="staged", created_by="shortform_articles.py"),
        "title": title, "slug_preview": _slugify(title),
        "picked_refs": data.get("refs"), "body_chars": len(body_md),
    }


async def _select_turns(args) -> list:
    """The source turns: newest-first, answers present, filtered by owner/session/min-citations."""
    async with AsyncSessionLocal() as db:
        q = (select(ResearchTurn)
             .join(ResearchSession, ResearchSession.id == ResearchTurn.session_id)
             .order_by(ResearchTurn.created_at.desc()))
        if args.session:
            q = q.where(ResearchTurn.session_id == args.session)
        elif args.owner_uid:
            q = q.where(ResearchSession.owner_uid == args.owner_uid)
        turns = (await db.execute(q.limit(args.limit * 4 + 20))).scalars().all()
    picked = []
    for t in turns:
        if not ((t.answer or {}).get("text") or "").strip():
            continue
        if len(_cited_ids(t)) < args.min_citations:
            continue
        picked.append(t)
        if len(picked) >= args.limit:
            break
    return picked


async def process(t, sem, args) -> dict:
    async with sem:
        t0 = time.monotonic()
        rec = await _make_draft(args.mode, t, args.pair_size)
        if rec is None:
            rec = {"ok": False, "ref": f"session={t.session_id} seq={t.seq}", "error": "not_eligible"}
        if rec.get("ok") and not args.dry_run:
            async with AsyncSessionLocal() as db:
                draft = ContentDraft(**rec["fields"])
                db.add(draft)
                await db.commit()
                await db.refresh(draft)
                rec["draft_id"] = str(draft.id)
        rec.pop("fields", None)  # not JSON-serializable / noisy for the log
        rec["secs"] = round(time.monotonic() - t0, 1)
        rec["dry_run"] = args.dry_run
        _log(rec)
        return rec


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["crop", "pair"], default="crop")
    ap.add_argument("--owner-uid", default=OWNER_UID, help="Source-turn owner (ignored if --session set).")
    ap.add_argument("--session", default=None, help="Only turns from this research session id.")
    ap.add_argument("--limit", type=int, default=5, help="Max source turns to distill.")
    ap.add_argument("--min-citations", type=int, default=0,
                    help="Skip turns citing fewer than N bills (pair mode auto-raises to --pair-size).")
    ap.add_argument("--pair-size", type=int, choices=[2, 4], default=2, help="pair mode: bills to contrast.")
    ap.add_argument("--dry-run", action="store_true", help="Generate + log, but write NO drafts.")
    args = ap.parse_args()
    if args.mode == "pair":
        args.min_citations = max(args.min_citations, args.pair_size)

    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text("", encoding="utf-8")
    turns = await _select_turns(args)
    _log({"event": "start", "mode": args.mode, "n": len(turns), "dry_run": args.dry_run,
          "pair_size": args.pair_size, "min_citations": args.min_citations})
    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(process(t, sem, args) for t in turns))
    ok = [r for r in results if r.get("ok")]
    _log({"event": "done", "made": len(ok), "skipped": len(results) - len(ok),
          "draft_ids": [r["draft_id"] for r in ok if r.get("draft_id")]})


if __name__ == "__main__":
    asyncio.run(main())

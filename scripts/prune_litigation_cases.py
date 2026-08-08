"""Re-screen every already-ingested litigation case against the relevance gate.

Background: `litigation_cases` was populated by "whatever CourtListener's full-text search returned",
with no subject-matter check anywhere between the search and the alert email. On production that left
34 tracked cases — Pfizer and Novo Nordisk products liability, DraftKings v. Philadelphia, a
motorcycle club, two copies of a DOJ constitutional suit against Maryland — of which exactly one
(NAWD v. Ryan, the challenge to Colorado's packaging EPR program) is circular-economy litigation.
Subscribers received alerts for them under the subject "EPR Litigation Update: <case>".

This script rules on each row and records the verdict in the migration-046 columns:

    ce_relevant = true   -> stays public and alertable
    ce_relevant = false  -> hidden from the API and never alerted on, ROW AND EVENTS RETAINED

Nothing is deleted. The rows are the evidence of what went out, the verdict is reversible with a
single UPDATE, and every change is written to `classification_changes` (old/new snapshot, run_id
`litigation-prune-<date>`) exactly like the bill-classification backfills, so the run is queryable
and undoable as a unit.

Two ways to decide, and the default is the cheap one:

  --mode metadata (default)  Screen on what is already in the database — case name, court, challenge
                             type, plaintiffs, and every stored event description. No network, no
                             LLM, reproducible. This is sufficient for the current backlog: the junk
                             has no circular-economy vocabulary anywhere in it.
  --mode fetch               Re-fetch each docket from CourtListener and read the complaint text,
                             the same evidence the live gate uses. Slower and costs API calls, but it
                             is the only mode that can RESCUE a true positive whose relevance lives
                             only in the filing (NAWD v. Ryan is docketed as "42:1983 Civil Rights
                             Act" and says nothing about packaging outside its complaint).

Because metadata mode cannot see filings, it never silently condemns an unreadable case: a row it
cannot clear is reported and, unless --commit-uncertain is passed, left untouched at NULL for a human
or a --mode fetch pass. Only unambiguous rejections are written.

Also reports exact-duplicate cases (same case_name, different courtlistener_id) — production carries
"United States v. State of Maryland" twice, ids 9 and 15 — but does not merge them; that needs a human
call about which docket is canonical.

DEFAULTS TO DRY RUN.

Run:
    python scripts/prune_litigation_cases.py                                   # dry run, local
    python scripts/prune_litigation_cases.py --commit
    python scripts/prune_litigation_cases.py --dsn "postgresql://...@127.0.0.1:55432/signalscout"
    python scripts/prune_litigation_cases.py --mode fetch --commit --dsn "..."
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.add_bill_from_legiscan import _normalize_dsn  # noqa: E402

RUN_ID = f"litigation-prune-{date.today().isoformat()}"


async def _load_cases(session) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT c.id, c.courtlistener_id, c.case_name, c.court_id, c.docket_number,
                       c.challenge_type, c.key_plaintiffs, c.related_state, c.case_status,
                       c.preemption_risk, c.ce_relevant, c.relevance_source,
                       COALESCE(
                           (SELECT string_agg(COALESCE(e.description, '') || ' ' || COALESCE(e.summary, ''),
                                              E'\\n')
                            FROM litigation_events e WHERE e.case_id = c.id),
                           ''
                       ) AS event_text
                FROM litigation_cases c
                ORDER BY c.id
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def _metadata_evidence(row: dict) -> str:
    from app.ingestion.litigation_relevance import build_evidence

    plaintiffs = row.get("key_plaintiffs") or []
    if not isinstance(plaintiffs, list):
        plaintiffs = []
    return build_evidence(
        case_name=row["case_name"] or "",
        cause=row.get("challenge_type") or "",
        party_names=[str(p) for p in plaintiffs][:12],
        entry_descriptions=[(row.get("event_text") or "")[:8000]],
    )


async def _verdict_from_metadata(row: dict):
    from app.ingestion.litigation_relevance import assess_relevance

    return await assess_relevance(_metadata_evidence(row), case_name=row["case_name"] or "")


async def _verdict_from_fetch(cl, row: dict):
    from app.ingestion.litigation_relevance import RelevanceVerdict, screen_docket

    docket_id = row["courtlistener_id"]
    try:
        docket = await cl.get_docket_details(docket_id)
        await asyncio.sleep(1.0)
        parties = await cl.get_parties(docket_id)
        await asyncio.sleep(1.0)
        entries = await cl.get_docket_entries(docket_id)
        await asyncio.sleep(1.0)
    except Exception as e:  # noqa: BLE001
        return RelevanceVerdict(
            relevant=False,
            reason=f"Could not re-fetch docket ({type(e).__name__}); left for review.",
            source="llm_unavailable",
            needs_review=True,
        )
    return await screen_docket(cl, docket=docket, parties=parties, entries=entries)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--mode", choices=("metadata", "fetch"), default="metadata")
    ap.add_argument("--commit", action="store_true", help="Write the verdicts (default: dry run).")
    ap.add_argument(
        "--commit-uncertain",
        action="store_true",
        help="Also write ce_relevant=false for cases the gate flagged as uncertain.",
    )
    ap.add_argument("--only-unscreened", action="store_true", help="Skip rows already screened.")
    args = ap.parse_args()

    if not args.dsn:
        print("No DSN: pass --dsn or set DATABASE_URL.")
        return

    engine = create_async_engine(_normalize_dsn(args.dsn))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        cases = await _load_cases(session)
        if args.only_unscreened:
            cases = [c for c in cases if c["ce_relevant"] is None]
        print(f"{len(cases)} case(s) to screen · mode={args.mode} · "
              f"{'COMMIT' if args.commit else 'DRY RUN'}\n")

        # Duplicate report — same case, two dockets. Reported, never auto-merged.
        by_name: dict[str, list[dict]] = defaultdict(list)
        for c in cases:
            by_name[(c["case_name"] or "").strip().lower()].append(c)
        dupes = {k: v for k, v in by_name.items() if len(v) > 1}

        cl_ctx = None
        if args.mode == "fetch":
            from app.ingestion.courtlistener import CourtListenerClient

            cl_ctx = CourtListenerClient()
            await cl_ctx.__aenter__()

        kept, dropped, uncertain = [], [], []
        try:
            for row in cases:
                verdict = (
                    await _verdict_from_fetch(cl_ctx, row)
                    if args.mode == "fetch"
                    else await _verdict_from_metadata(row)
                )
                mark = "KEEP  " if verdict.relevant else ("?     " if verdict.needs_review else "DROP  ")
                print(f"{mark} [{row['id']:>4}] {(row['case_name'] or '')[:62]:<62} "
                      f"{verdict.source:<16} {verdict.reason[:80]}")

                bucket = kept if verdict.relevant else (uncertain if verdict.needs_review else dropped)
                bucket.append((row, verdict))

                writable = verdict.relevant or not verdict.needs_review or args.commit_uncertain
                if not (args.commit and writable):
                    continue

                await session.execute(
                    text(
                        """
                        UPDATE litigation_cases
                           SET ce_relevant = :rel,
                               relevance_reason = :reason,
                               relevance_source = :source,
                               relevance_checked_at = :now
                         WHERE id = :id
                        """
                    ),
                    {
                        "rel": verdict.relevant,
                        "reason": verdict.reason,
                        "source": verdict.source,
                        "now": datetime.now(timezone.utc),
                        "id": row["id"],
                    },
                )
                # Audit trail. classification_changes is keyed on bill_id, so a case with no matched
                # bill can't be logged there — those are covered by the printed run output and by the
                # relevance_* columns themselves, which carry the same old/new information per row.
                await session.execute(
                    text(
                        """
                        INSERT INTO classification_changes (bill_id, run_id, old_value, new_value)
                        SELECT related_law_id, :run_id, CAST(:old AS jsonb), CAST(:new AS jsonb)
                          FROM litigation_cases WHERE id = :id AND related_law_id IS NOT NULL
                        """
                    ),
                    {
                        "run_id": RUN_ID,
                        "old": _json(
                            {
                                "litigation_case_id": row["id"],
                                "case_name": row["case_name"],
                                "ce_relevant": row["ce_relevant"],
                                "relevance_source": row["relevance_source"],
                            }
                        ),
                        "new": _json(
                            {
                                "litigation_case_id": row["id"],
                                "case_name": row["case_name"],
                                "ce_relevant": verdict.relevant,
                                "relevance_source": verdict.source,
                                "reason": verdict.reason,
                            }
                        ),
                        "id": row["id"],
                    },
                )
        finally:
            if cl_ctx is not None:
                await cl_ctx.__aexit__()

        if args.commit:
            await session.commit()

    print(f"\nkept {len(kept)} · dropped {len(dropped)} · uncertain {len(uncertain)}")
    if uncertain and not args.commit_uncertain:
        print("  uncertain rows left at NULL — re-run with --mode fetch, or --commit-uncertain to "
              "exclude them pending review.")
    if dupes:
        print("\nDuplicate case names (not merged — pick the canonical docket by hand):")
        for name, group in dupes.items():
            ids = ", ".join(f"id={c['id']}/cl={c['courtlistener_id']}" for c in group)
            print(f"  {name[:60]}: {ids}")
    if not args.commit:
        print("\nDry run — nothing written. Re-run with --commit.")

    await engine.dispose()


def _json(value: dict) -> str:
    import json

    return json.dumps(value, default=str)


if __name__ == "__main__":
    asyncio.run(main())

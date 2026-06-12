"""Reset classification on bills so the next classification cycle re-judges them.

Why this exists
---------------
We expanded scope to the biological cycle of the circular economy (biomaterials,
regenerative agriculture & soil health, organics recycling) — new keywords, new classifier
taxonomy, and new TRACKED_INSTRUMENTS. Re-ingesting the OpenStates dump pulls in the
*newly-matched* bills (they arrive with confidence_score NULL and auto-classify), but bills
ALREADY in the table keep their old, pre-taxonomy classification. An organics bill the
classifier previously tagged "other"/not-relevant won't be re-judged as "organics_recycling"
unless we clear its score.

run_classification_cycle() only reprocesses bills with confidence_score IS NULL or = -1.0.
This script sets confidence_score = NULL for the bills the new scope can rescue, so the next
cycle picks them up.

Scope (cost control)
--------------------
Only OpenStates-sourced bills whose title/description pass the CURRENT (expanded) keyword
filter are touched — re-running Haiku over the whole irrelevant corpus would be wasteful.
By default only currently NOT-relevant bills are reset (the bio-cycle gap); pass
--include-relevant to also refresh already-relevant rows (heavier — re-judges material
categories etc.).

Alert guard
-----------
Bills that flip to relevant after reclassification look "new" to the alert cycle. Pass
--suppress-alerts to set new_bill_alert_sent = true on every reset row so they enter quietly
and only genuinely future bills trigger emails. (See the plan's Phase E.)

Run against LOCAL first, then push_bills_to_prod.py, OR point --dsn at prod via the Cloud SQL
Auth Proxy:
    python scripts/reset_classification.py --dry-run
    python scripts/reset_classification.py --suppress-alerts
    python scripts/reset_classification.py --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout" --suppress-alerts
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.classification.keywords import KEYWORDS_PATH, KeywordFilter  # noqa: E402

# The bio-cycle categories the broadened classifier prompt newly brings into scope. Scoping the
# reset to bills matching these (rather than the whole keyword-passing corpus) avoids re-running
# Haiku over thousands of bills it already, correctly, judged not-relevant — only bills whose
# relevance could actually flip under the new prompt are re-judged.
BIO_CYCLE_CATEGORIES = [
    "biomaterials_keywords",
    "soil_health_and_regenerative_ag_keywords",
    "organics_and_food_waste_keywords",
]


def _bio_patterns() -> list[re.Pattern]:
    kw = json.loads(Path(KEYWORDS_PATH).read_text(encoding="utf-8"))
    terms = [t for cat in BIO_CYCLE_CATEGORIES for t in kw.get(cat, [])]
    return [re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in terms]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing.")
    ap.add_argument("--limit", type=int, default=None, help="Cap rows reset (testing).")
    ap.add_argument("--scope", choices=["bio", "all"], default="bio",
                    help="bio (default): only re-judge bills matching the new biological-cycle "
                         "terms (biomaterials / soil & regen-ag / organics). all: every bill that "
                         "passes the expanded filter (heavier — mostly re-confirms not-relevant).")
    ap.add_argument("--include-relevant", action="store_true",
                    help="Also reset bills already marked relevant (refresh under new taxonomy).")
    ap.add_argument("--suppress-alerts", action="store_true",
                    help="Set new_bill_alert_sent=true on reset rows so they don't flood subscribers.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    kf = KeywordFilter()
    bio_patterns = _bio_patterns() if args.scope == "bio" else None

    def _in_scope(title: str, desc: str) -> bool:
        if not kf.passes_threshold(title, desc):
            return False
        if bio_patterns is None:
            return True
        corpus = f"{title} {desc}"
        return any(p.search(corpus) for p in bio_patterns)

    # Candidates: OpenStates bills already classified (so the cycle would otherwise skip them).
    # confidence_score = -1.0 is the "awaiting LLM" sentinel — already picked up by the cycle,
    # so leave it. We re-judge in Python with the expanded keyword filter to scope the reset.
    where = (
        "openstates_id IS NOT NULL "
        "AND confidence_score IS NOT NULL "
        "AND confidence_score <> -1.0"
    )
    if not args.include_relevant:
        where += " AND epr_relevant = false"

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            f"SELECT id, title, description FROM bills WHERE {where}"
        )
        reset_ids = [
            r["id"] for r in rows
            if _in_scope(r["title"] or "", r["description"] or "")
        ]
        if args.limit:
            reset_ids = reset_ids[: args.limit]

        print(f"{len(rows)} candidate rows scanned; "
              f"{len(reset_ids)} pass the expanded keyword filter and will be reset")
        if args.suppress_alerts:
            print("  (will also set new_bill_alert_sent=true on those rows)")

        if args.dry_run or not reset_ids:
            print("\n(dry run — no changes written)" if args.dry_run else "\n(nothing to reset)")
            return

        set_clause = "confidence_score = NULL, epr_relevant = false, updated_at = now()"
        if args.suppress_alerts:
            set_clause += ", new_bill_alert_sent = true"
        result = await conn.execute(
            f"UPDATE bills SET {set_clause} WHERE id = ANY($1::int[])",
            reset_ids,
        )
        print(f"\napplied: {result}")
        print("Next: run `MODE=classify python app/pipeline_job.py` to re-judge them.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

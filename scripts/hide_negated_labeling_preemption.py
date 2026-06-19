"""Hide labeling/preemption bills the classifier itself judged out of scope.

"labeling" and "preemption" are generic instruments: they apply far outside circular-economy
policy (nutrition/ingredient labeling, country-of-origin; preemption of tobacco, firearm,
employment, or tax rules). The old pipeline forced any bill tagged with one of them in scope
via TRACKED_INSTRUMENTS, even when Haiku's own reasoning said it was "not product stewardship,
EPR, or circular economy policy". The pipeline no longer does this (labeling/preemption now
ride in only via is_ce_relevant — see app/classification/haiku_classifier.TRACKED_INSTRUMENTS),
and this script applies the same correction to existing rows.

We don't persist Haiku's raw is_ce_relevant, only the computed ce_relevant flag and the
reasoning (ai_summary), so we classify rows by their reasoning text:

  HIDE  = ce_relevant AND instrument_type in {labeling, preemption}
          AND ai_summary has a NEGATION cue ("not / unrelated to / no connection to ... EPR")
          AND ai_summary has NO in-domain cue (plastics, recyclability claims, EPR relevance).

The in-domain guard protects genuine circular-economy bills that share the instrument:
recyclability / truth-in-labeling laws (CA SB-343, IL Truth in Recycling Act) and preemption
of plastic-bag / polystyrene / e-waste / EPR laws. Bills whose reasoning merely says "rather
than producer responsibility ... mechanisms" (no NEGATION cue) are left untouched.

Inverse of backfill_relevance.py; same idea as hide_untracked_instruments.py but text-based.
DRY RUN BY DEFAULT — prints the full HIDE / KEEP partition for audit. Pass --apply to write.

Run against LOCAL first, then re-run push_bills_to_prod.py, OR point --dsn straight at prod
via the Cloud SQL Auth Proxy:
    python scripts/hide_negated_labeling_preemption.py --dsn "postgresql://signalscout@127.0.0.1:5434/signalscout" --apply

Local default uses the app's DATABASE_URL.
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))

INSTRUMENTS = ["labeling", "preemption"]

# The classifier asserts the bill is NOT in the circular-economy domain. Phrases like
# "rather than producer responsibility ... mechanisms" are deliberately NOT here: that hedge
# also describes genuine recyclability-labeling laws, so we leave those rows alone.
NEGATION_CUES = [
    r"\bunrelated to\b",
    r"\bno connection to\b",
    r"\boutside\b[^.]{0,40}\bepr\b",
    r"\bfalling outside\b[^.]{0,20}\bepr\b",
    r"\bcontains no epr\b",
    r"\bno epr[, ]",
    # "not / does not (address|establish) ... <domain term>" within the same clause
    r"\bnot\b[^.]{0,70}(product stewardship|extended producer|\bepr\b|circular econom|producer responsibility)",
    r"\bdoes not (address|establish|contain)\b[^.]{0,90}(product stewardship|\bepr\b|circular econom|producer responsibility|recycled content)",
]

# Genuine circular-economy signal — keep the row even if a negation cue also fired. These match
# only POSITIVE mentions (a plastics/recyclability subject, or explicit EPR relevance), NOT the
# boilerplate negation list ("... recycled content, or deposit schemes") that off-domain bills
# also carry, so they don't accidentally rescue menstrual-product / tobacco / firearm bills.
INDOMAIN_CUES = [
    r"recyclab",            # recyclability / recyclable (never appears in the negation boilerplate)
    r"\brecycling (symbol|act|claims|infrastructure)",
    r"truth in recycling",
    r"biodegrad",
    r"compostab",
    r"plastic bag",
    r"polystyrene",
    r"single-use plastic",
    r"auxiliary container",
    r"plastic container",
    r"disposable plastic",
    r"\be-waste\b",
    r"local plastic",
    r"plastic (and|regulation|materials)",
    # explicit EPR relevance (positive verbs, not negations)
    r"relevant to epr",
    r"epr.adjacent",
    r"enabling local",
    r"affecting local epr",
    r"directly impacting",
    r"impacting state",
    r"could (enable|restrict|affect|impact)",
    r"restrict[^.]{0,40}implementation",
    r"product stewardship (policies|policy by|ordinances)",
    r"supporting epr",
]

_NEG = [re.compile(p, re.I) for p in NEGATION_CUES]
_POS = [re.compile(p, re.I) for p in INDOMAIN_CUES]


def should_hide(summary: str) -> bool:
    s = summary or ""
    if not any(rx.search(s) for rx in _NEG):
        return False
    if any(rx.search(s) for rx in _POS):
        return False
    return True


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry run).")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, state, bill_number, instrument_type, coalesce(ai_summary,'') AS s "
            "FROM bills WHERE ce_relevant = true AND instrument_type = ANY($1::text[]) "
            "ORDER BY instrument_type, state, bill_number",
            INSTRUMENTS,
        )
        hide_ids, hide_rows, keep_rows = [], [], []
        for r in rows:
            (hide_rows if should_hide(r["s"]) else keep_rows).append(r)
            if should_hide(r["s"]):
                hide_ids.append(r["id"])

        def dump(title, rs):
            print(f"\n{title} ({len(rs)}):")
            for r in rs:
                print(f"  [{r['instrument_type'][:4]}|{r['state']}|{r['bill_number']}] {r['s'][:160]}")

        print(f"{len(rows)} labeling/preemption bills currently in scope")
        dump("KEEP (in-domain or no negation)", keep_rows)
        dump("HIDE (classifier judged out of scope)", hide_rows)
        print(f"\n=> {len(hide_ids)} bills would flip ce_relevant -> False")

        if not args.apply:
            print("\n(dry run — pass --apply to write)")
            return
        if hide_ids:
            await conn.execute(
                "UPDATE bills SET ce_relevant = false, updated_at = now() "
                "WHERE id = ANY($1::int[])",
                hide_ids,
            )
        print(f"\napplied: {len(hide_ids)} rows updated")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

"""Seed the bill_outcome table — documented real-world outcomes of enacted laws.

Every other table describes what a law REQUIRES; bill_outcome captures what an enacted law has
been documented to PRODUCE (positive / negative / mixed), always anchored to a citation. These
are hand-curated and slug-keyed (measured impacts are rare and uneven — there's no auto-extractor),
so this list grows by research over time. Each row is upserted on `slug`, and `bill_id` is linked
by (state, bill_number) when the law is a tracked row — otherwise it stays null and the denormalized
fields carry the law's identity.

`attribution` is the honesty knob:
  direct     — the statute itself produced the number
  program    — the law funds/incentivizes a program that produced it (the number predates/exceeds
               the law; the law scales the activity behind it)
  associated — correlated, looser

Usage:
  venv/Scripts/python scripts/seed_bill_outcomes.py --test   # print, no writes
  venv/Scripts/python scripts/seed_bill_outcomes.py
  venv/Scripts/python scripts/seed_bill_outcomes.py --prod-dsn "..."
"""
import argparse
import json
import sys

from sqlalchemy import create_engine, text

from app.config import settings

# --- Curated outcomes. Add to this list as research surfaces documented impacts. ---
OUTCOMES = [
    dict(
        slug="tx-hb3487-oyster-reef",
        state="TX",
        bill_number="HB3487",
        law_title="Sales-tax deduction for restaurants in oyster-shell recycling programs",
        instrument_type="incentives",
        material_categories=["organics"],
        direction="positive",
        metric_label="of oyster reef restored",
        metric_value=25,
        metric_unit="acres",
        metric_display=None,
        summary=(
            "TX HB3487 (effective Oct 1, 2025) lets restaurants deduct $2 per 50 lbs of oyster "
            "shells recycled from their sales-and-use tax — a financial lever to scale the shell "
            "recovery that feeds reef restoration. The programs it incentivizes, led by the "
            "Sink Your Shucks initiative, have reclaimed 3M+ lbs of shell and restored ~25 acres of "
            "reef across Copano, Aransas, and St. Charles Bays since 2009. The law is new, so the "
            "acreage reflects the activity it now subsidizes, not the deduction alone."
        ),
        attribution="program",
        as_of_date="2025-10-01",
        source_name="Harte Research Institute — Sink Your Shucks",
        source_url="https://www.harteresearch.org/oyster-recycling-efforts-major-gulf-restoration-project",
        confidence=0.7,
        reviewed=False,
    ),
    dict(
        slug="or-bottle-bill-redemption",
        state="OR",
        bill_number=None,
        law_title="Oregon Bottle Bill (beverage-container deposit, first in the U.S., 1971)",
        instrument_type="deposit_return",
        material_categories=["packaging"],
        direction="positive",
        metric_label="container redemption rate (highest of any U.S. deposit state)",
        metric_value=87.3,
        metric_unit="%",
        metric_display=None,
        summary=(
            "The nation's first deposit-return law (10¢ since 2017) drove a 2023 redemption rate of "
            "~87% — the highest of any U.S. bottle-bill state (a preliminary OBRC estimate put it at "
            "90.5%; the final OLCC figure landed lower). Decades of evidence that a refundable deposit "
            "keeps the overwhelming majority of containers out of the litter stream."
        ),
        attribution="direct",
        as_of_date="2023-12-31",
        source_name="Resource Recycling / Oregon OLCC",
        source_url="https://resource-recycling.com/recycling/2024/04/16/oregon-deposit-system-estimates-90-5-return-rate/",
        confidence=0.8,
        reviewed=False,
    ),
    dict(
        slug="mi-bottle-bill-decline",
        state="MI",
        bill_number=None,
        law_title="Michigan Bottle Bill (10¢ beverage-container deposit, 1976)",
        instrument_type="deposit_return",
        material_categories=["packaging"],
        direction="mixed",
        metric_label="redemption rate — once the nation's best, now eroding",
        metric_value=None,
        metric_unit=None,
        metric_display="70.4% (2024), down from >95%",
        summary=(
            "Michigan's 10¢ deposit — the country's highest — once delivered redemption above 95%. The "
            "rate fell to 70.4% in 2024 (lowest since at least 1990; ~$116M went unredeemed), partly "
            "because a 1976 dime is worth ~2¢ today and a COVID return shutdown broke the habit. The "
            "cautionary case: a fixed nominal deposit decays in real value if it isn't indexed."
        ),
        attribution="direct",
        as_of_date="2024-12-31",
        source_name="Bridge Michigan",
        source_url="https://bridgemi.com/michigan-environment-watch/michigans-bottle-return-rates-keep-falling-it-time-change/",
        confidence=0.85,
        reviewed=False,
    ),
    dict(
        slug="ca-sb270-bag-waste-increase",
        state="CA",
        bill_number="SB270",
        law_title="California single-use carryout bag ban (SB 270, 2014)",
        instrument_type="other",
        material_categories=["plastic_packaging"],
        direction="negative",
        metric_label="plastic-bag waste tonnage after the ban",
        metric_value=None,
        metric_unit=None,
        metric_display="157k → 231k tons (+47%)",
        summary=(
            "SB 270 banned thin plastic bags but let stores sell thicker 'reusable' film bags that were "
            "usually thrown away after one use — and carry far more plastic each. Discarded plastic-bag "
            "tonnage rose from ~157,000 (2014) to ~231,000 (2022). A loophole turned a ban into more "
            "plastic by weight; California closed it with a 2024 follow-on law. The clearest negative "
            "case in the set — design detail decided the outcome."
        ),
        attribution="direct",
        as_of_date="2022-12-31",
        source_name="Policy Review at Berkeley / CalRecycle data",
        source_url="https://www.ocf.berkeley.edu/~prb/sb270-and-the-recycling-myth/",
        confidence=0.75,
        reviewed=False,
    ),
    dict(
        slug="dc-bag-fee-reduction",
        state="DC",
        bill_number=None,
        law_title="DC Anacostia River Cleanup & Protection Act (5¢ bag fee, 2009)",
        instrument_type="incentives",
        material_categories=["plastic_packaging"],
        direction="positive",
        metric_label="drop in disposable-bag use per person (72% fewer bags in river cleanups)",
        metric_value=None,
        metric_unit=None,
        metric_display="−60% bags per person",
        summary=(
            "The first U.S. all-bag fee (5¢) cut reported per-person bag use from ~10 to ~4 a week (−60%), "
            "and the Alice Ferguson Foundation logged 72% fewer bags in Anacostia cleanup counts. The fee "
            "also raised ~$28.8M (2010–2022) for river restoration. Evidence that a small priced nudge "
            "outperformed a poorly-designed ban (cf. CA SB 270)."
        ),
        attribution="direct",
        as_of_date="2024-12-31",
        source_name="Anacostia Riverkeeper / GW report",
        source_url="https://www.anacostiariverkeeper.org/evaluating-dcs-bag-fee-2024-gw-report/",
        confidence=0.75,
        reviewed=False,
    ),
    dict(
        slug="paint-stewardship-epr-gallons",
        state=None,
        bill_number=None,
        law_title="State paint-stewardship (EPR) laws — first OR 2009, now 10+ states (PaintCare programs)",
        instrument_type="epr",
        material_categories=["paint"],
        direction="positive",
        metric_label="of leftover paint collected and managed",
        metric_value=82,
        metric_unit="million gallons",
        metric_display=None,
        summary=(
            "Producer-funded paint stewardship — the model EPR program — has collected ~82 million gallons "
            "of leftover paint across the 10+ states with paint-EPR laws, run by the nonprofit PRO "
            "PaintCare. The figure aggregates across all state programs, so it's the activity those laws "
            "set up rather than any single statute."
        ),
        attribution="program",
        as_of_date=None,
        source_name="Product Stewardship Institute",
        source_url="https://productstewardship.us/paint-care-qa/",
        confidence=0.8,
        reviewed=False,
    ),
    dict(
        slug="mattress-stewardship-epr-recycled",
        state=None,
        bill_number=None,
        law_title="State mattress-stewardship (EPR) laws — CA/CT/RI 2013, OR later (MRC programs)",
        instrument_type="epr",
        material_categories=["mattresses"],
        direction="positive",
        metric_label="mattresses recycled",
        metric_value=None,
        metric_unit=None,
        metric_display="15M+ mattresses (555M+ lbs diverted)",
        summary=(
            "Mattress-stewardship EPR laws fund the Mattress Recycling Council's Bye Bye Mattress program, "
            "which has recycled more than 15 million mattresses and kept 555M+ lbs of steel, foam, fiber "
            "and wood out of landfills across CA, CT, OR and RI. Aggregated across the state programs."
        ),
        attribution="program",
        as_of_date=None,
        source_name="Mattress Recycling Council",
        source_url="https://mattressrecyclingcouncil.org/who-we-are/",
        confidence=0.8,
        reviewed=False,
    ),
    dict(
        slug="wa-ecycle-electronics-collected",
        state="WA",
        bill_number=None,
        law_title="Washington E-Cycle electronics EPR (Electronic Product Recycling law, program from 2009)",
        instrument_type="epr",
        material_categories=["electronics"],
        direction="positive",
        metric_label="of electronics collected since 2009",
        metric_value=None,
        metric_unit=None,
        metric_display="453M+ lbs since 2009",
        summary=(
            "One of the first U.S. electronics-EPR programs: manufacturers fund free e-waste collection, "
            "which has taken in 453M+ lbs since 2009. Annual tonnage is now declining (≈13M lbs in 2023) — "
            "largely because devices keep getting lighter, not because less is recovered."
        ),
        attribution="direct",
        as_of_date="2022-12-31",
        source_name="Northwest Product Stewardship Council",
        source_url="https://productstewardship.net/news/e-cycle-washington-collects-13-million-pounds-electronics-2022",
        confidence=0.8,
        reviewed=False,
    ),
    dict(
        slug="ca-ab2398-carpet-underperformance",
        state="CA",
        bill_number="AB2398",
        law_title="California carpet stewardship (AB 2398, 2010)",
        instrument_type="epr",
        material_categories=["carpet"],
        direction="mixed",
        metric_label="carpet recycling rate stayed ~10–12%; $1.18M in state penalties",
        metric_value=None,
        metric_unit=None,
        metric_display="10–12% recycling rate (2013–16)",
        summary=(
            "The first U.S. carpet-EPR law stood up a program but badly missed its goals: recycling rates "
            "sat at 10–12% from 2013–2016, and CalRecycle fined the stewardship organization (CARE) "
            "$1.175M for repeated failures. It prompted stronger enforcement (AB 729 raised penalties to "
            "$5,000/day). EPR can be enacted yet underperform without teeth — a mixed, instructive case."
        ),
        attribution="direct",
        as_of_date="2016-12-31",
        source_name="CalRecycle",
        source_url="https://calrecycle.ca.gov/2021/03/30/press-release-21-01/",
        confidence=0.85,
        reviewed=False,
    ),
]


def main():
    # Summaries carry non-ASCII (→, ¢); avoid a cp1252 console blowing up after a clean write.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--prod-dsn", default=None)
    args = ap.parse_args()
    engine = create_engine(args.prod_dsn or settings.database_url)

    # Resolve bill_id by (state, bill_number) for outcomes whose law is a tracked row.
    keys = [(o["state"], o["bill_number"]) for o in OUTCOMES if o.get("state") and o.get("bill_number")]
    bill_ids: dict[tuple[str, str], int] = {}
    if keys:
        with engine.connect() as c:
            for st, bn in keys:
                row = c.execute(
                    text("select id from bills where state=:st and bill_number=:bn limit 1"),
                    {"st": st, "bn": bn},
                ).first()
                if row:
                    bill_ids[(st, bn)] = row[0]

    linked = 0
    for o in OUTCOMES:
        bid = bill_ids.get((o.get("state"), o.get("bill_number")))
        if bid:
            linked += 1
        if not args.test:
            with engine.begin() as c:
                c.execute(text("""
                    insert into bill_outcome
                      (slug, bill_id, state, bill_number, law_title, instrument_type,
                       material_categories, direction, metric_label, metric_value, metric_unit,
                       metric_display, summary, attribution, as_of_date, source_name, source_url,
                       confidence, reviewed)
                    values
                      (:slug, :bill_id, :state, :bill_number, :law_title, :instrument_type,
                       cast(:material_categories as jsonb), :direction, :metric_label, :metric_value,
                       :metric_unit, :metric_display, :summary, :attribution, :as_of_date,
                       :source_name, :source_url, :confidence, :reviewed)
                    on conflict (slug) do update set
                      bill_id=excluded.bill_id, state=excluded.state, bill_number=excluded.bill_number,
                      law_title=excluded.law_title, instrument_type=excluded.instrument_type,
                      material_categories=excluded.material_categories, direction=excluded.direction,
                      metric_label=excluded.metric_label, metric_value=excluded.metric_value,
                      metric_unit=excluded.metric_unit, metric_display=excluded.metric_display,
                      summary=excluded.summary, attribution=excluded.attribution,
                      as_of_date=excluded.as_of_date, source_name=excluded.source_name,
                      source_url=excluded.source_url, confidence=excluded.confidence,
                      reviewed=excluded.reviewed
                """), {**o, "bill_id": bid,
                       "material_categories": json.dumps(o.get("material_categories"))})

    print(f"Outcomes seeded: {len(OUTCOMES)}  (linked to a tracked bill: {linked})  test={args.test}\n")
    for o in OUTCOMES:
        bid = bill_ids.get((o.get("state"), o.get("bill_number")))
        link = f"bill_id={bid}" if bid else "unlinked"
        fig = o.get("metric_display") or (
            f"{o.get('metric_value')} {o.get('metric_unit') or ''}".strip()
            if o.get("metric_value") is not None else "—")
        law = f"{o.get('state') or '--'} {o.get('bill_number') or ''}".strip()
        print(f"  [{o['direction']:>8s}] {law:14s} {fig:>22s}  ({link})")


if __name__ == "__main__":
    main()

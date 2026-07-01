"""Generate the free Design Guide teaser (dashboard-next/src/data/designGuideTeaser.ts).

The teaser IS the design principles — the free page. The full guide (app/static/design_guide.html,
built by build_design_guide.py + render_design_guide.py) expands them into design guidance. This is
step 2 of the pipeline, run after synthesize_design_principles.py has written tmp/design_principles.json:

    cloud-sql-proxy --address 127.0.0.1 --port 5434 ce-bill-tracker:us-central1:signalscout-pg &
    venv/Scripts/python.exe scripts/synthesize_design_principles.py --dsn "...:5434/signalscout" --persist
    venv/Scripts/python.exe scripts/generate_design_teaser.py       --dsn "...:5434/signalscout"
    venv/Scripts/python.exe scripts/build_design_guide.py           --dsn "...:5434/signalscout"
    venv/Scripts/python.exe scripts/render_design_guide.py

It reads tmp/design_principles.json, aggregates the per-(lever, obligation) principles into one
TeaserLever per lever (headline = the "required" statement; direction = the top evidence action;
bills = the deduped source bills with their ids; focus = the most common materials, from the DB), and
writes the TS data module the dashboard imports. --dsn is only needed for the `focus` material chips;
omit it to skip them.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from app.synthesis.design_guide import PACKAGING_LEVERS, PRODUCT_LEVERS  # noqa: E402

PRINCIPLES = REPO / "tmp" / "design_principles.json"
OUT = REPO / "dashboard-next" / "src" / "data" / "designGuideTeaser.ts"

# Display names for the levers (the taxonomy codes live in app/synthesis/design_guide.py).
LEVER_NAMES = {
    "design_for_recycling": "Design for Recycling",
    "recycled_content": "Recycled Content",
    "source_reduction": "Source Reduction",
    "reuse_refill": "Reuse & Refill",
    "toxics_elimination": "Toxics Elimination",
    "material_restriction": "Material Restrictions",
    "labeling_marking": "Labeling & Marking",
    "compostability": "Compostability",
    "repairability_durability": "Repairability & Durability",
}
LEVER_ORDER = [*PACKAGING_LEVERS, *PRODUCT_LEVERS]


US_STATES = set(
    "AL AK AZ AR CA CO CT DC DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV "
    "NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
# Threshold units that denote a currency amount — the concrete "this costs €X" figures for the fee
# overlay (eco-modulation). Percentages / microns / years are quantitative but not monetary.
_MONETARY = ("eur", "euro", "chf", "gbp", "pln", "zl", "usd", "kr", "eek", "deposit")
# Packaging-material codes collapsed into a single "Packaging" focus chip (EPR treats glass/metal as
# packaging), so product categories (textiles, electronics, batteries…) aren't crowded out.
_PACKAGING_MATERIALS = frozenset({"plastic_packaging", "paper_packaging", "glass", "metals"})


def fmt_material(code: str) -> str:
    return code.replace("_", " ").strip().capitalize()


def _money_example(ev: dict) -> str | None:
    """A concise 'amount + unit' string when the signal carries a currency threshold, else None."""
    val, unit = ev.get("threshold_value"), (ev.get("threshold_unit") or "")
    u = unit.lower()
    if val in (None, "", "None") or "percent" in u or "%" in u:
        return None
    if not any(t in u for t in _MONETARY):
        return None
    return f"{val} {unit.replace('_per_', '/').replace('_', ' ')}".strip()


def _confidence(e: dict) -> float:
    try:
        return float(e.get("confidence"))
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None,
                    help="Postgres DSN (via the Cloud SQL proxy) — used only for the material 'focus' "
                         "chips. Omit to skip them.")
    args = ap.parse_args()

    principles = json.loads(PRINCIPLES.read_text(encoding="utf-8"))

    by_lever: dict[str, list] = {}
    for p in principles:
        by_lever.setdefault(p["lever"], []).append(p)

    # Materials per bill_id (for the focus chips) — one query over every cited bill.
    mat_by_bill: dict[int, list] = {}
    bill_ids = {int(e["bill_id"]) for ps in by_lever.values() for p in ps
                for e in p["evidence"] if e.get("bill_id")}
    if args.dsn and bill_ids:
        with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT id, material_categories FROM bills WHERE id = ANY(%s)", (list(bill_ids),))
            for bid, mats in cur.fetchall():
                mat_by_bill[bid] = mats or []

    levers_out = []
    all_bills, all_states = set(), set()

    for lever in LEVER_ORDER:
        ps = by_lever.get(lever)
        if not ps:
            continue
        # Primary principle drives the headline: prefer 'required', else the most-cited.
        primary = next((p for p in ps if p.get("obligation_type") == "required"), None) \
            or max(ps, key=lambda p: p["bill_count"])
        headline = re.sub(r"^[^:]+:\s*", "", primary["statement"]).strip()

        ev_sorted = sorted((e for p in ps for e in p["evidence"]), key=_confidence, reverse=True)

        seen, bills, states = set(), [], set()
        for e in ev_sorted:
            bid = e.get("bill_id")
            if not bid or bid in seen:
                continue
            seen.add(bid)
            bills.append({"state": e["state"], "billNumber": e.get("bill_number") or "", "billId": int(bid)})
            states.add(e["state"])
            all_bills.add(int(bid))
            all_states.add(e["state"])

        top = ev_sorted[0] if ev_sorted else None
        direction = (top.get("design_action") or headline).strip() if top else headline
        evidence = None
        if top:
            evidence = {"state": top["state"], "bill": top.get("bill_number") or "",
                        "quote": (top.get("source_excerpt") or "").strip()}

        # "Applies to" chips. The packaging materials (plastic/paper/glass/metal) collapse into one
        # "Packaging" chip so they don't crowd out the product categories — otherwise textiles,
        # electronics, batteries, vehicles all get buried under packaging variants. Then the top
        # non-packaging categories show individually.
        counts: dict[str, int] = {}
        has_packaging = False
        for b in bills:
            for m in mat_by_bill.get(b["billId"], []):
                if not m or m == "other":
                    continue
                if m in _PACKAGING_MATERIALS:
                    has_packaging = True
                else:
                    counts[m] = counts.get(m, 0) + 1
        focus = (["Packaging"] if has_packaging else []) + [
            fmt_material(m) for m, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:6]
        ]

        # Fee-impact overlay (eco-modulation): this lever modulates a producer's EPR fee up (malus,
        # from `penalized` signals) or down (bonus, from `rewarded`). Set-fee jurisdictions (mostly
        # EU/foreign, further along) show concrete amounts; the US is directional — fees are still
        # being determined (Circular Action Alliance schedule), so it reads "rate TBD (CAA)".
        mod_ev = [e for p in ps if p.get("obligation_type") in ("penalized", "rewarded") for e in p["evidence"]]
        set_juris = sorted({e["state"] for e in mod_ev} - US_STATES)
        us_in_lever = bool({e["state"] for p in ps for e in p["evidence"]} & US_STATES)
        examples, seen_amt = [], set()
        for e in mod_ev:
            amt = _money_example(e)
            key = (e["state"], amt)
            if amt and key not in seen_amt:
                seen_amt.add(key)
                examples.append({"jurisdiction": e["state"], "amount": amt})
        fee_impact = None
        if set_juris or any(p.get("obligation_type") in ("penalized", "rewarded") for p in ps):
            fee_impact = {
                "malus": any(p.get("obligation_type") == "penalized" for p in ps),
                "bonus": any(p.get("obligation_type") == "rewarded" for p in ps),
                "setJurisdictions": set_juris,
                "usPending": us_in_lever,
                "examples": examples[:3],
            }

        levers_out.append({
            "lever": lever,
            "name": LEVER_NAMES.get(lever, lever.replace("_", " ").title()),
            "headline": headline,
            "direction": direction,
            "focus": focus,
            "billCount": len(bills),
            "states": sorted(states),
            "evidence": evidence,
            "feeImpact": fee_impact,
            "bills": bills,
        })

    coverage = {"bills": len(all_bills), "states": len(all_states), "levers": len(levers_out)}

    header = (
        "// AUTO-GENERATED from tmp/design_principles.json by scripts/generate_design_teaser.py. Do not edit by hand.\n"
        "// The Free teaser: per-lever headline + direction + material/product focus (front face),\n"
        "// plus the grounded source bills behind the principle (back face -- each opens the bill modal).\n\n"
        "export interface TeaserBill {\n  state: string;\n  billNumber: string;\n  billId: number;\n}\n\n"
        "export interface FeeImpact {\n  malus: boolean;\n  bonus: boolean;\n"
        "  setJurisdictions: string[];\n  usPending: boolean;\n"
        "  examples: { jurisdiction: string; amount: string }[];\n}\n\n"
        "export interface TeaserLever {\n  lever: string;\n  name: string;\n  headline: string;\n  direction: string;\n"
        "  focus: string[];\n  billCount: number;\n  states: string[];\n"
        "  evidence: { state: string; bill: string; quote: string } | null;\n"
        "  feeImpact: FeeImpact | null;\n  bills: TeaserBill[];\n}\n\n"
        f"export const GUIDE_COVERAGE = {json.dumps(coverage)};\n\n"
        "export const TEASER_LEVERS: TeaserLever[] = "
    )
    OUT.write_text(header + json.dumps(levers_out, indent=2, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    print("Coverage:", coverage)
    print("Levers:", ", ".join(f"{lv['name']}({lv['billCount']})" for lv in levers_out))


if __name__ == "__main__":
    main()

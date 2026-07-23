"""Build the shareable Design-for-Circularity guide from persisted bill_design_signal rows.

Reads the cited design signals (prod, read-only via the Cloud SQL proxy), authors a canonical
section per lever (app/synthesis/design_guide.py, Sonnet), and writes a Markdown guide:
    tmp/design_guide.md

The guide is grounded in real bills with verbatim quotes preserved (chain of custody). Evidence
is weighted enacted-first. No fee/cost figures are asserted — eco-modulation rates are pending the
Circular Action Alliance schedules.

Usage:
    cloud-sql-proxy --address 127.0.0.1 --port 5434 ce-bill-tracker:us-central1:signalscout-pg &
    venv/Scripts/python.exe scripts/build_design_guide.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5434/signalscout"
Needs ANTHROPIC_API_KEY in the environment / .env.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.synthesis.design_guide import (  # noqa: E402
    OBLIGATION_LABEL,
    PACKAGING_LEVERS,
    PRODUCT_LEVERS,
    PRINCIPLE_STATEMENTS,
    GuideAuthor,
    status_rank,
)

TMP = Path(__file__).parent.parent / "tmp"
MAX_EVIDENCE_PER_LEVER = 28  # cap tokens; enacted-first sampling keeps the authoritative ones


def _heading(lever: str) -> str:
    return PRINCIPLE_STATEMENTS.get(lever, lever.replace("_", " ").title())


def _evidence_sort_key(e: dict) -> tuple:
    # enacted first, then higher confidence, then has-threshold.
    return (
        -status_rank(e.get("status")),
        -(e.get("confidence") or 0.0),
        0 if e.get("threshold_value") is not None else 1,
    )


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True, help="Prod Postgres DSN (via the Cloud SQL proxy).")
    args = ap.parse_args()

    conn = await asyncpg.connect(args.dsn)
    try:
        rows = await conn.fetch(
            "SELECT s.lever, s.obligation_type, s.design_action, s.source_excerpt, "
            "       s.threshold_value, s.threshold_unit, s.confidence, "
            "       b.state, b.bill_number, b.status "
            "FROM bill_design_signal s JOIN bills b ON b.id = s.bill_id"
        )
    finally:
        await conn.close()

    by_lever: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_lever[r["lever"]].append(dict(r))

    total_bills = len({(r["state"], r["bill_number"]) for r in rows})
    enacted_bills = len({
        (r["state"], r["bill_number"]) for r in rows if (r["status"] or "").lower() == "enacted"
    })
    states = sorted({r["state"] for r in rows})

    author = GuideAuthor()

    async def _author_lever(lever: str) -> tuple[str, dict, list[dict]]:
        ev = sorted(by_lever.get(lever, []), key=_evidence_sort_key)
        section = await author.author(lever, ev[:MAX_EVIDENCE_PER_LEVER]) if ev else {}
        return lever, section, ev

    ordered = [lv for lv in (*PACKAGING_LEVERS, *PRODUCT_LEVERS) if by_lever.get(lv)]
    print(f"Authoring {len(ordered)} lever sections from {len(rows)} signals "
          f"({total_bills} bills, {enacted_bills} enacted)...")
    results = await asyncio.gather(*[_author_lever(lv) for lv in ordered])
    sections = {lv: (sec, ev) for lv, sec, ev in results}

    # ---- Assemble Markdown -------------------------------------------------
    md: list[str] = []
    md.append("# Designing for Circularity: A Practitioner's Guide\n")
    md.append(
        "_How to design packaging and products that stay compliant — and pay lower fees — under "
        "US Extended Producer Responsibility (EPR) and adjacent circular-economy law._\n")
    md.append(
        f"> Derived from **{total_bills} bills across {len(states)} states** "
        f"({enacted_bills} already enacted) that our system has classified and analyzed. Every "
        "principle below traces to specific bills, with the exact statutory language quoted. "
        "Proposed bills show the direction of travel; **enacted** laws are obligations today.\n")
    md.append(
        "**How to use this guide.** Each lever is a design decision you control. For every lever: "
        "the *imperatives* are what to do, *targets* are the hard numbers to hit, and *evidence* "
        "shows the laws driving it. Audit your SKUs lever by lever; prioritize the states you sell "
        "into. Fee figures are intentionally omitted until the Circular Action Alliance publishes "
        "eco-modulation rates — at which point design choices map directly to dollar exposure.\n")
    md.append("\n---\n")

    def render_section(lever: str) -> None:
        sec, ev = sections[lever]
        if not ev:
            return
        # Obligation -> states coverage line.
        oblig_states: dict[str, set] = defaultdict(set)
        for e in ev:
            oblig_states[e["obligation_type"]].add(e["state"])
        bills_n = len({(e["state"], e["bill_number"]) for e in ev})
        enacted_n = len({
            (e["state"], e["bill_number"]) for e in ev if (e.get("status") or "").lower() == "enacted"
        })

        md.append(f"## {_heading(lever)}\n")
        if sec.get("summary"):
            md.append(sec["summary"] + "\n")
        coverage = " · ".join(
            f"**{OBLIGATION_LABEL.get(o, o)}** in {len(s)} state(s)"
            for o, s in sorted(oblig_states.items(), key=lambda kv: -len(kv[1]))
        )
        md.append(f"_Backed by {bills_n} bills ({enacted_n} enacted) — {coverage}._\n")

        if sec.get("imperatives"):
            md.append("\n**Design imperatives**\n")
            for imp in sec["imperatives"]:
                cites = ", ".join(imp.get("cite_bills", []))
                tag = imp.get("obligation", "")
                tagstr = f" _({tag})_" if tag else ""
                cite_str = f" — {cites}" if cites else ""
                md.append(f"- **{imp.get('action','').rstrip('.')}**{tagstr}. {imp.get('detail','')}{cite_str}")

        if sec.get("targets"):
            md.append("\n**Targets to hit**\n")
            for t in sec["targets"]:
                md.append(f"- {t}")

        # Verbatim provenance — up to 3 enacted-first quotes, unaltered.
        md.append("\n<details><summary>Evidence (statutory language)</summary>\n")
        for e in ev[:3]:
            tag = "enacted" if (e.get("status") or "").lower() == "enacted" else (e.get("status") or "proposed")
            md.append(f"\n> \"{(e.get('source_excerpt') or '').strip()}\"  \n"
                      f"> — **{e['state']} {e.get('bill_number') or '?'}** ({tag}, "
                      f"{OBLIGATION_LABEL.get(e['obligation_type'], e['obligation_type'])})")
        md.append("\n</details>\n")
        md.append("\n---\n")

    md.append("\n# Part 1 — Packaging design\n")
    for lever in PACKAGING_LEVERS:
        if lever in sections:
            render_section(lever)

    md.append("\n# Part 2 — Product design & right to repair\n")
    md.append(
        "_Adjacent legislation: right-to-repair and durability laws don't use EPR fees, but they "
        "impose design obligations on the same product teams — and they are the fastest-moving "
        "category in this dataset._\n")
    for lever in PRODUCT_LEVERS:
        if lever in sections:
            render_section(lever)

    md.append("\n# Methodology & limits\n")
    md.append(
        f"- **Source.** {total_bills} bills across {len(states)} states classified and analyzed by "
        "Atlas Circular; design signals extracted from each bill's compliance text and **verified to be "
        "verbatim** before inclusion (no paraphrased citations).\n"
        "- **Authority.** Enacted laws are current obligations; proposed bills indicate direction and "
        "may change or fail. Each principle notes how many of its backing bills are enacted.\n"
        "- **Coverage.** Drawn from the bills with full compliance extractions to date — strong on "
        "flagship enacted programs (CA, OR, CO, ME, CT, MN, VT), lighter on early-stage bills.\n"
        "- **Costs.** No fee or cost figures are asserted; eco-modulation rates are set by producer "
        "responsibility organizations (e.g. Circular Action Alliance) and are pending. Once published, "
        "each design lever maps to fee exposure based on the volume of covered product you sell.\n"
        "- **This is design guidance, not legal advice.** Confirm obligations against the statute and "
        "your counsel for the states you operate in.\n")

    TMP.mkdir(exist_ok=True)
    out = TMP / "design_guide.md"
    doc = "\n".join(md)
    out.write_text(doc, encoding="utf-8")
    print(f"\nWrote {out}  ({len(doc)} chars, {len(ordered)} sections)")


if __name__ == "__main__":
    asyncio.run(main())

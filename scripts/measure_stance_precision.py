"""Ground-truth the precision of the "weakens" stance call — the gate behind the public red
"weakens circular economy" flag.

The flag currently relies on confidence_score >= 0.7, but confidence_score is the classifier's
confidence that a bill is *circular-economy-relevant*, NOT its confidence in the stance *direction*
(advances vs weakens). And every AI-weakens bill already scores >= 0.7, so that gate filters nothing.
Before trusting an AI-only public "harmful" flag we need a real number: of the bills Haiku called
"weakens", how many actually weaken a circular-economy policy?

The population is small (~57), so this measures the WHOLE population, not a sample — the result is the
exact precision, not an estimate.

Two phases:

  --run     For every ce_relevant bill with policy_stance='weakens' & stance_source='ai', re-judge the
            stance with a stronger adjudicator model (Opus by default) — an independent second opinion,
            not the Haiku that made the original call. Writes two artifacts:
              data/analysis/stance_weakens_audit.csv  — machine-readable, has a blank `human_verdict`
              data/analysis/stance_weakens_audit.md   — readable worksheet, disagreements first
            and prints the adjudicator-agreement rate (an automated PROXY for precision).

  --score   Read back the CSV after you've filled `human_verdict` (weakens | advances | neutral | unsure)
            and print the EXACT human-ground-truth precision + a 95% Wilson interval.

The adjudicator sees the same input Haiku saw (title + description) by default, so --run isolates
"would a smarter model on the same evidence agree?". Pass --with-text to additionally fetch the bill's
full text from OpenStates (slower, rate-limited) for a fairer judgment. The human worksheet always
carries source_url so your verdict can be the true ground truth from the actual bill.

Usage:
    venv/Scripts/python.exe scripts/measure_stance_precision.py --run                 # Opus, title+desc
    venv/Scripts/python.exe scripts/measure_stance_precision.py --run --model claude-sonnet-4-6
    venv/Scripts/python.exe scripts/measure_stance_precision.py --run --with-text     # +full text
    venv/Scripts/python.exe scripts/measure_stance_precision.py --score data/analysis/stance_weakens_audit.csv
"""
import argparse
import asyncio
import csv
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

OPUS_MODEL = "claude-opus-4-8"
OUT_CSV = Path("data/analysis/stance_weakens_audit.csv")
OUT_MD = Path("data/analysis/stance_weakens_audit.md")

# Mirrors the stance definition the Haiku classifier uses (app/classification/haiku_classifier.py),
# so the adjudicator judges against the SAME rubric — we're testing the call, not changing the rules.
ADJUDICATOR_SYSTEM = """\
You are an expert in US environmental and circular-economy policy (EPR, product stewardship, \
right-to-repair, recycled-content, deposit-return, organics/composting, regenerative agriculture & \
soil health, bio-based materials, and federal/state preemption of such laws). You judge a bill's \
DIRECTION relative to the circular-economy policy it touches — not whether you personally favor it.\
"""

ADJUDICATOR_TEMPLATE = """\
Judge this bill's policy stance and respond with ONLY valid JSON — no prose, no markdown.

State: {state}
Bill: {bill_number}
Title: {title}
Description: {description}
{text_block}
Stance is the bill's direction relative to the circular-economy policy it touches:
  - "advances": establishes, strengthens, broadens, or funds the policy, OR repeals/limits a
    preemption that blocked it. A small-producer carve-out inside an otherwise-establishing bill is
    still "advances" — judge the bill's NET effect.
  - "weakens": exempts or carves products/entities out of the policy, narrows its scope, repeals it,
    defunds it, or newly preempts local authority to enact it.
  - "neutral": study/task-force/appropriations-only/administrative, or genuinely unclear from the
    available text.

Return exactly:
{{
  "stance": "advances" | "weakens" | "neutral",
  "stance_confidence": <float 0.0-1.0, your confidence in the DIRECTION call>,
  "rationale": "<one sentence: what in the bill drives the direction>"
}}
"""

_VALID = {"advances", "weakens", "neutral"}


async def _adjudicate(client, model, b, text):
    import anthropic  # noqa: F401  (ensure dep present)

    text_block = f"Bill text excerpt (first 4000 chars):\n{text[:4000]}\n" if text else ""
    prompt = ADJUDICATOR_TEMPLATE.format(
        state=b["state"] or "",
        bill_number=b["bill_number"] or "Unknown",
        title=b["title"] or "",
        description=(b["description"] or "")[:800],
        text_block=text_block,
    )
    # Opus 4.8 deprecates `temperature`; older models still honor it for determinism.
    kwargs = {}
    if not model.startswith("claude-opus-4-8"):
        kwargs["temperature"] = 0
    last_err = None
    for attempt in range(3):
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=300,
                system=ADJUDICATOR_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            raw = resp.content[0].text.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                import re
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                data = json.loads(m.group()) if m else {}
            stance = str(data.get("stance", "")).lower()
            if stance not in _VALID:
                stance = "neutral"
            return {
                "stance": stance,
                "confidence": float(data.get("stance_confidence", 0.0) or 0.0),
                "rationale": str(data.get("rationale", "")).replace("\n", " ").strip(),
            }
        except Exception as e:  # noqa: BLE001
            last_err = e
            await asyncio.sleep(1.5 * (attempt + 1))
    return {"stance": "error", "confidence": 0.0, "rationale": f"adjudication failed: {last_err}"}


async def run(model, with_text, limit, concurrency):
    import anthropic
    import asyncpg
    from app.config import settings

    dsn = settings.database_url.replace("postgresql+asyncpg", "postgresql")
    conn = await asyncpg.connect(dsn)
    q = (
        "SELECT id, state, bill_number, title, description, confidence_score, source_url, openstates_id "
        "FROM bills WHERE ce_relevant AND policy_stance='weakens' AND stance_source='ai' "
        "ORDER BY confidence_score DESC, id"
    )
    rows = [dict(r) for r in await conn.fetch(q)]
    await conn.close()
    if limit:
        rows = rows[:limit]
    print(f"adjudicating {len(rows)} AI-'weakens' bills with {model}"
          + (" (+full text)" if with_text else " (title+description only)") + " ...")

    # Optionally enrich with full bill text (slow: OpenStates is rate-limited).
    texts = {}
    if with_text:
        from app.ingestion.openstates import OpenStatesClient
        async with OpenStatesClient() as os_client:
            for i, b in enumerate(rows, 1):
                if b["openstates_id"]:
                    try:
                        texts[b["id"]] = await os_client.get_bill_text(b["openstates_id"]) or ""
                    except Exception as e:  # noqa: BLE001
                        print(f"  [text fail] {b['state']} {b['bill_number']}: {e}")
                print(f"  ...fetched text {i}/{len(rows)}", end="\r")
        print()

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=90.0, max_retries=0)
    sem = asyncio.Semaphore(concurrency)
    results = [None] * len(rows)

    async def one(i, b):
        async with sem:
            results[i] = await _adjudicate(client, model, b, texts.get(b["id"], ""))

    await asyncio.gather(*(one(i, b) for i, b in enumerate(rows)))

    agree = sum(1 for r in results if r["stance"] == "weakens")
    errors = sum(1 for r in results if r["stance"] == "error")
    judged = len(rows) - errors
    reclass = {}
    for r in results:
        if r["stance"] not in ("weakens", "error"):
            reclass[r["stance"]] = reclass.get(r["stance"], 0) + 1

    # Write artifacts (sorted: disagreements first, so the worksheet front-loads the suspect calls).
    order = sorted(range(len(rows)), key=lambda i: (results[i]["stance"] == "weakens", -rows[i]["confidence_score"]))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "state", "bill_number", "haiku_stance", "relevance_conf",
                    f"adjudicator_stance({model})", "adjudicator_conf", "adjudicator_rationale",
                    "source_url", "title", "human_verdict"])
        for i in order:
            b, r = rows[i], results[i]
            w.writerow([b["id"], b["state"], b["bill_number"], "weakens",
                        round(b["confidence_score"], 2), r["stance"], round(r["confidence"], 2),
                        r["rationale"], b["source_url"] or "", b["title"] or "", ""])

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(f"# Stance audit — AI-'weakens' bills (adjudicator: {model})\n\n")
        f.write(f"- Population: **{len(rows)}** bills (ce_relevant, policy_stance='weakens', stance_source='ai')\n")
        f.write(f"- Adjudicator agrees 'weakens': **{agree}/{judged}** "
                f"= **{agree/judged*100:.0f}%** (automated proxy for precision)\n")
        if reclass:
            f.write(f"- Adjudicator reclassified to: {reclass}\n")
        if errors:
            f.write(f"- Adjudication errors: {errors}\n")
        f.write("\nFill the **Verdict** column from the actual bill (source link): "
                "`weakens` / `advances` / `neutral` / `unsure`, then run `--score`.\n\n")
        f.write("| Verdict | State | Bill | Rel.conf | Adjudicator | Adj.conf | Rationale | Bill | Source |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for i in order:
            b, r = rows[i], results[i]
            flag = "" if r["stance"] == "weakens" else "⚠ "
            title = (b["title"] or "").replace("|", "\\|")[:80]
            rat = r["rationale"].replace("|", "\\|")[:120]
            src = f"[link]({b['source_url']})" if b["source_url"] else "—"
            f.write(f"|  | {b['state']} | {b['bill_number']} | {b['confidence_score']:.2f} | "
                    f"{flag}{r['stance']} | {r['confidence']:.2f} | {rat} | {title} | {src} |\n")

    print(f"\nPopulation: {len(rows)}  |  adjudicator agrees 'weakens': {agree}/{judged} "
          f"= {agree/judged*100:.0f}%  (proxy)")
    if reclass:
        print(f"adjudicator reclassified to: {reclass}")
    if errors:
        print(f"errors: {errors}")
    print(f"\nWorksheet written:\n  {OUT_CSV}\n  {OUT_MD}\n"
          "Fill the human_verdict column from the source bills, then run --score.")


def _wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def score(csv_path):
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    verdicts = [(r.get("human_verdict") or "").strip().lower() for r in rows]
    labeled = [v for v in verdicts if v in {"weakens", "advances", "neutral", "unsure"}]
    confirmed = sum(1 for v in labeled if v == "weakens")
    decided = [v for v in labeled if v != "unsure"]  # precision excludes "unsure"
    n = len(decided)
    print(f"rows in worksheet:     {len(rows)}")
    print(f"labeled:               {len(labeled)}  (unsure: {len(labeled) - n})")
    if n == 0:
        print("No decided verdicts yet — fill the human_verdict column (weakens/advances/neutral/unsure).")
        return
    lo, hi = _wilson(confirmed, n)
    print(f"confirmed 'weakens':   {confirmed}/{n}")
    print(f"EXACT precision:       {confirmed/n*100:.0f}%   (95% CI {lo*100:.0f}%–{hi*100:.0f}%)")
    mis = {}
    for v in decided:
        if v != "weakens":
            mis[v] = mis.get(v, 0) + 1
    if mis:
        print(f"false 'weakens' were actually: {mis}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true", help="Adjudicate + write worksheet.")
    ap.add_argument("--score", metavar="CSV", help="Compute exact precision from a filled worksheet.")
    ap.add_argument("--model", default=OPUS_MODEL, help=f"Adjudicator model (default {OPUS_MODEL}).")
    ap.add_argument("--with-text", action="store_true", help="Fetch full bill text (slow).")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()

    if args.score:
        score(args.score)
    elif args.run:
        asyncio.run(run(args.model, args.with_text, args.limit, args.concurrency))
    else:
        ap.error("pass --run or --score")


if __name__ == "__main__":
    main()

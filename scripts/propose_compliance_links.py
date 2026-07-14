"""Layer 3: find the authoritative "how to comply" page for weak links — propose, don't apply.

The override layer in build_compliance_pathways.py (PROGRAM_PAGES / BILL_OVERRIDES) captures
links a human has curated. This script feeds that layer at scale: for each enacted law whose
link is *weak* — an agency homepage instead of the specific program page, or a law classified
"no obligation" that may actually carry a producer-registration/reporting duty — it asks Claude
(with the web_search + web_fetch server tools) to find the single most authoritative official
page, then VERIFIES the candidate through the layer-1 auditor's classifier before showing it.

Output is a reviewable diff: ready-to-paste BILL_OVERRIDES entries plus justification and the
verify status. It writes NOTHING to the DB or to build_compliance_pathways.py — a human pastes
the entries they approve. This is the human gate by design: a wrong "where to register" link is
worse than an honest homepage.

"Runs sometimes": run it after new enacted laws land, or on a slow cadence to chip at the long
tail. Bound each run with --limit / --state / --material.

Usage:
  venv/Scripts/python scripts/propose_compliance_links.py --dry-run            # list the work, no API
  venv/Scripts/python scripts/propose_compliance_links.py --limit 8
  venv/Scripts/python scripts/propose_compliance_links.py --state CA --material electronics
  venv/Scripts/python scripts/propose_compliance_links.py --limit 20 --out proposals.txt
"""
import argparse
import json
import sys
import time

import anthropic
import httpx
from sqlalchemy import create_engine, text

from app.config import settings

# Reuse the layer-1 four-bucket classifier so a proposed link is verified the same way the
# existing links are audited (dead candidates are dropped; blocked = correct-but-WAF'd is kept).
from app.links.health import classify

MODEL = "claude-opus-4-8"  # default per house guidance; override with --model (e.g. claude-sonnet-4-6 for cost)

# Per-region framing for the finder. US keeps its own prompt; each foreign region tells Claude what an
# authoritative "where to comply" page looks like there (the éco-organisme / national register), so it
# stops returning the raw statute (wall of text) or a ministry homepage. Regions not listed fall back
# to the generic profile.
REGION_PROFILE = {
    "FR": dict(name="France", lang="French",
               authority="the designated éco-organisme for this filière (e.g. Citeo for packaging/paper, "
                         "Ecologic for WEEE/batteries, Refashion for textiles) or the SYDEREP national "
                         "producer register run by ADEME"),
    "JP": dict(name="Japan", lang="Japanese",
               authority="the designated recycling corporation for this product (e.g. JCPRA for containers "
                         "& packaging) or the specific METI/MOE recycling-law program page"),
    "UK": dict(name="the United Kingdom", lang="English",
               authority="the GOV.UK producer-responsibility registration/report service (e.g. Report "
                         "packaging data) or an approved producer compliance scheme (PCS)"),
    "DE": dict(name="Germany", lang="German",
               authority="the mandatory register — Zentrale Stelle Verpackungsregister (LUCID) for "
                         "packaging, stiftung ear for electrical equipment and batteries"),
    "EU": dict(name="the European Union", lang="English",
               authority="each member state's national producer register (there is no single EU register) "
                         "or the official EU guidance page for this instrument"),
}
GENERIC_PROFILE = dict(name=None, lang="the local language",
                       authority="the national producer register or the designated producer-responsibility "
                                 "organization / compliance scheme")

# Found-URL domain -> a curated foreign entity slug, so the pathway's entity matches the page the
# finder chose (avoids a "Citeo ->" label pointing at the SYDEREP register). Only unambiguous
# single-entity domains are listed. gov.uk is deliberately omitted: it hosts three UK entities
# (uk-epr-packaging / uk-weee / uk-producer-responsibility), so we keep the material-routed baseline
# there. When no domain matches, write_pathway keeps the baseline entity so the link still renders.
# Kept in sync with FOREIGN_ENTITIES in build_compliance_pathways.py.
FOREIGN_DOMAIN_TO_SLUG = {
    "citeo.com": "fr-citeo", "ecologic-france.com": "fr-ecologic", "refashion.fr": "fr-refashion",
    "syderep.ademe.fr": "fr-syderep", "ademe.fr": "fr-syderep",
    "jcpra.or.jp": "jp-jcpra", "meti.go.jp": "jp-meti",
    "verpackungsregister.org": "de-lucid", "stiftung-ear.de": "de-ear", "bmuv.de": "de-bmuv",
}

# JSON shape we ask Claude to return as its final message.
RESULT_SCHEMA_HINT = """Return ONLY a JSON object (no prose, no code fence) of exactly this shape:
{
  "found": true | false,
  "url": "<the single most authoritative official page where a producer registers / reports / complies, or null>",
  "entity_name": "<the PRO or agency that runs it, or null>",
  "entity_type": "pro" | "agency" | null,
  "action_type": "join_pro" | "register_with_state" | "file_individual_plan" | "report_to_program" | "monitor" | "none",
  "action_summary": "<one sentence telling a producer what to do, naming the entity>",
  "confidence": <0.0-1.0>,
  "justification": "<one sentence: why this is the authoritative page>",
  "source_note": "<where you confirmed it — the official domain you trust>"
}
Set found=false ONLY if, after searching, there is genuinely no producer-registration or reporting
obligation for this law. Prefer a .gov page or the statute's officially designated PRO. Prefer the
SPECIFIC program / "producer registration" page over an agency homepage."""


# Which slice of "weak" links to research. homepage-only (a real EPR law whose link is just the
# agency homepage) is the higher-yield slice; none-monitor includes many genuine non-obligations.
WEAK_KIND_SQL = {
    "all": "(p.action_type in ('none','monitor') "
           "or (e.id is not null and (p.registration_url is null or p.registration_url = e.url)))",
    "none-monitor": "p.action_type in ('none','monitor')",
    "homepage": "(e.id is not null and (p.registration_url is null or p.registration_url = e.url))",
}


def collect_targets(engine, regions, state, material, limit, weak_kind):
    """Weak pathways worth researching: not already hand-curated or finder-written (basis not in
    manual/ai_verified), filtered to the requested slice (see WEAK_KIND_SQL). `regions` is None for
    the default US mode (region='US', excluding the federal state='US' row) or an explicit list of
    foreign region codes."""
    # weak_kind is a validated enum (argparse choices); region codes are validated below — safe to interpolate.
    if regions:
        codes = [r for r in regions if r.isalnum() and len(r) <= 4]
        region_clause = "b.region in (" + ",".join(f"'{c}'" for c in codes) + ")"
    else:
        region_clause = "b.region = 'US' and b.state <> 'US'"
    sql = text(f"""
        select b.id, b.region, b.state, b.bill_number, b.title, b.material_categories,
               p.action_type, p.management_model, p.registration_url, p.basis,
               e.name as entity_name, e.url as entity_url
        from compliance_pathway p
        join bills b on b.id = p.bill_id
        left join compliance_entity e on e.id = p.entity_id
        where coalesce(p.basis,'') not in ('manual', 'ai_verified')
          and {region_clause}
          and {WEAK_KIND_SQL[weak_kind]}
          and (:state is null or b.state = :state)
          and (:material is null or b.material_categories ? :material)
        order by (p.action_type in ('none','monitor')) desc, b.region, b.state, b.bill_number
        limit :limit
    """)
    with engine.connect() as c:
        return list(c.execute(sql, {"state": state, "material": material, "limit": limit}))


def build_prompt(t):
    mats = ", ".join(t.material_categories or []) or "unspecified"
    if t.region == "US":
        return (
            f"You are auditing producer-compliance links for U.S. extended-producer-responsibility "
            f"(EPR) laws. Find where a producer must register/report to comply with THIS enacted law.\n\n"
            f"State: {t.state}\n"
            f"Bill: {t.bill_number}\n"
            f"Title: {t.title}\n"
            f"Material(s): {mats}\n"
            f"Current classification: action_type={t.action_type}, model={t.management_model}\n"
            f"Current link (may be wrong, a homepage, or missing): {t.registration_url or '(none)'}\n\n"
            f"Search the web for the authoritative official page — the state agency program page for "
            f"this material, or the statute's designated producer responsibility organization (PRO). "
            f"Note: some laws classified 'no obligation' actually have a producer-registration or "
            f"reporting form (e.g. mercury-added products report to a state/regional clearinghouse). "
            f"Look specifically for 'producer registration' / 'manufacturer reporting' for this material "
            f"in this state.\n\n"
            + RESULT_SCHEMA_HINT
        )
    # Foreign national/EU law: point Claude at the éco-organisme / national register, and forbid the
    # two failure modes we see — returning the statute text or a bare ministry homepage.
    prof = REGION_PROFILE.get(t.region, GENERIC_PROFILE)
    juris = prof["name"] or t.region
    return (
        f"You are auditing producer-compliance links for extended-producer-responsibility (EPR) laws "
        f"OUTSIDE the United States. Find the single page where a producer REGISTERS or REPORTS to "
        f"comply with THIS enacted law.\n\n"
        f"Jurisdiction: {juris}\n"
        f"Act / bill id: {t.bill_number}\n"
        f"Title: {t.title}\n"
        f"Material(s): {mats}\n"
        f"Current link (often the raw statute, a ministry homepage, or missing): "
        f"{t.registration_url or '(none)'}\n\n"
        f"Find the authoritative page: {prof['authority']}.\n"
        f"Hard rules:\n"
        f"- Do NOT return the statute or a legislation portal (e.g. Légifrance, gov.uk/legislation, "
        f"gesetze-im-internet.de, e-gov.go.jp, EUR-Lex) — that is the law itself, not where a producer "
        f"complies.\n"
        f"- Do NOT return a generic ministry/government homepage — return the SPECIFIC "
        f"producer-registration or éco-organisme membership/reporting page.\n"
        f"- The law's text may be in {prof['lang']}; the compliance page may be in {prof['lang']} or "
        f"English. Prefer the official éco-organisme/register domain.\n"
        f"- Set found=false if this act genuinely creates no producer registration/reporting duty "
        f"(e.g. a framework or enabling law with obligations only in later decrees).\n\n"
        + RESULT_SCHEMA_HINT
    )


def research_one(client, t, model, web_tools):
    """Run Claude + web tools; return the parsed JSON candidate (or {'found': False, ...})."""
    messages = [{"role": "user", "content": build_prompt(t)}]
    for _ in range(6):  # bound the server-tool resume loop
        resp = client.messages.create(
            model=model, max_tokens=3000,
            thinking={"type": "adaptive"},
            tools=web_tools,
            messages=messages,
        )
        if resp.stop_reason == "pause_turn":
            # Server tool hit its internal iteration cap — resend to continue.
            messages = [messages[0], {"role": "assistant", "content": resp.content}]
            continue
        break

    text_out = "".join(b.text for b in resp.content if b.type == "text").strip()
    # The final text block should be pure JSON; be tolerant of a stray fence or preamble.
    if "```" in text_out:
        text_out = text_out.split("```")[1].lstrip("json").strip() if "```json" in text_out \
            else text_out.split("```")[1].strip()
    try:
        return json.loads(text_out)
    except json.JSONDecodeError:
        s, e = text_out.find("{"), text_out.rfind("}")
        if s != -1 and e != -1:
            try:
                return json.loads(text_out[s:e + 1])
            except json.JSONDecodeError:
                pass
    return {"found": False, "url": None, "_parse_error": text_out[:200]}


def override_snippet(t, cand, verify):
    """A ready-to-paste override entry (per-bill granularity). US -> BILL_OVERRIDES keyed (state, bn);
    foreign -> FOREIGN_OVERRIDES keyed (region, bn). For foreign we auto-write by default, so this is
    mainly a paper trail / for --no-apply review runs."""
    def q(s):
        return json.dumps(s) if s is not None else "None"
    key = (f'("{t.state}", _norm_bn("{t.bill_number}"))' if t.region == "US"
           else f'("{t.region}", _norm_bn("{t.bill_number}"))')
    dest = "BILL_OVERRIDES" if t.region == "US" else "FOREIGN_OVERRIDES"
    lines = [
        f"    {key}: dict(",
        f"        url={q(cand.get('url'))},",
        f"        action_type={q(cand.get('action_type'))},",
        f"        action_summary={q(cand.get('action_summary'))}),",
    ]
    ent = cand.get("entity_name")
    head = (f"    # [{dest}] {t.region} {t.state or ''} {t.bill_number} — {cand.get('justification','')}\n"
            f"    #   verify: [{verify[0]}] {verify[1]}  |  confidence={cand.get('confidence')}"
            f"  |  suggested entity: {ent or '(none)'} ({cand.get('entity_type') or '-'})")
    return head + "\n" + "\n".join(lines)


def _domain(url):
    """Bare registrable-ish host of a URL, lowercased, no leading www."""
    host = (url or "").split("//", 1)[-1].split("/", 1)[0].lower()
    return host[4:] if host.startswith("www.") else host


def write_pathway(engine, entity_id_by_slug, t, cand, bucket, note):
    """Auto-write a verified foreign link to compliance_pathway (basis='ai_verified'). Upgrades the
    entity to a specific known éco-organisme when the found domain maps to one; otherwise keeps the
    baseline hub entity so the link still renders. Returns the entity slug used (or None)."""
    dom = _domain(cand["url"])
    slug = next((s for d, s in FOREIGN_DOMAIN_TO_SLUG.items() if d in dom), None)
    eid = entity_id_by_slug.get(slug) if slug else None
    set_entity = ", entity_id = :eid" if eid else ""  # only override when we matched a known éco-organisme
    with engine.begin() as c:
        c.execute(text(f"""
            update compliance_pathway
               set registration_url = :url,
                   action_type = :at,
                   action_summary = :sm,
                   confidence = :conf,
                   basis = 'ai_verified'{set_entity}
             where bill_id = :bid
        """), {"url": cand["url"], "at": cand.get("action_type") or "register_with_state",
               "sm": cand.get("action_summary"), "conf": cand.get("confidence"),
               "eid": eid, "bid": t.id})
    return slug


def main():
    # Model-generated text may contain non-cp1252 characters (em dashes, etc.); the Windows
    # console defaults to cp1252 and would crash on print. Force UTF-8 output.
    if hasattr(sys.stdout, "reconfigure"):
        # line_buffering so progress/partial results survive a mid-batch crash (background runs
        # full-buffer otherwise and lose everything on an exception).
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    ap = argparse.ArgumentParser()
    ap.add_argument("--prod-dsn", default=None)
    ap.add_argument("--region", default="US",
                    help="US (default; state-level EPR) or a CSV of foreign region codes, e.g. "
                         "FR,JP,UK,DE,EU. Foreign mode uses the region-aware prompt + auto-write.")
    ap.add_argument("--state", default=None, help="two-letter filter")
    ap.add_argument("--material", default=None, help="material_categories filter, e.g. electronics")
    ap.add_argument("--weak-kind", choices=list(WEAK_KIND_SQL), default="all",
                    help="which weak slice: all | none-monitor | homepage (homepage = higher yield)")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--min-confidence", type=float, default=0.5,
                    help="drop proposals below this confidence")
    ap.add_argument("--apply", action="store_true",
                    help="FOREIGN ONLY: write verified links straight to compliance_pathway "
                         "(basis='ai_verified'). Without it, foreign runs are propose-only.")
    ap.add_argument("--dry-run", action="store_true", help="list targets, make no API calls")
    ap.add_argument("--out", default=None, help="also write the proposals to this file")
    args = ap.parse_args()

    region_arg = args.region.strip().upper()
    is_us = region_arg == "US"
    regions = None if is_us else [c.strip() for c in region_arg.split(",") if c.strip()]
    if args.apply and is_us:
        sys.exit("--apply is foreign-only; US links are curated via BILL_OVERRIDES (paste-to-Python).")

    engine = create_engine(args.prod_dsn or settings.database_url)
    # entity slug -> id, for upgrading a foreign pathway's entity to a matched éco-organisme on write.
    entity_id_by_slug = {}
    if args.apply:
        with engine.connect() as c:
            entity_id_by_slug = {r[0]: r[1] for r in c.execute(
                text("select slug, id from compliance_entity"))}

    targets = collect_targets(engine, regions, args.state, args.material, args.limit, args.weak_kind)
    mode = "US" if is_us else f"foreign {','.join(regions)}" + (" [APPLY]" if args.apply else " [propose]")
    print(f"Weak pathways to research ({mode}): {len(targets)}"
          f"{' (PROD)' if args.prod_dsn else ''}\n")
    for t in targets:
        print(f"  {t.region} {t.state or '':2s} {t.bill_number:24s} "
              f"[{t.action_type or '-':>18s}]  {t.registration_url or '(no link)'}")
    if args.dry_run:
        print("\n--dry-run: no API calls made.")
        return
    if not targets:
        return

    if not settings.anthropic_api_key:
        sys.exit("\nERROR: anthropic_api_key not set (env ANTHROPIC_API_KEY or .env). "
                 "Use --dry-run to scope work without the API.")

    # max_retries rides out transient DNS/connection blips to the API mid-batch.
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=600.0, max_retries=4)
    web_tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    accepted, rejected, snippets = [], [], []
    with httpx.Client() as http:
        for i, t in enumerate(targets, 1):
            print(f"\n[{i}/{len(targets)}] researching {t.state} {t.bill_number} ...")
            try:
                cand = research_one(client, t, args.model, web_tools)
            except anthropic.BadRequestError as e:
                # A 400 is structural (e.g. web tools not enabled on the key) — fail fast, it'll
                # hit every target. Anything transient is caught below and skipped.
                sys.exit(f"\nAPI rejected the request (web tools may not be enabled on this key): "
                         f"{e.message}")
            except (anthropic.APIConnectionError, anthropic.APITimeoutError,
                    anthropic.APIStatusError) as e:
                print(f"    -> API error, skipping this one: {type(e).__name__}")
                rejected.append((t, {"url": None}, f"api error ({type(e).__name__})"))
                time.sleep(args.delay)
                continue
            if not cand.get("found") or not cand.get("url"):
                print(f"    -> no obligation found ({cand.get('source_note') or cand.get('_parse_error','')})")
                rejected.append((t, cand, "not found"))
                time.sleep(args.delay)
                continue
            if (cand.get("confidence") or 0) < args.min_confidence:
                print(f"    -> below confidence floor ({cand.get('confidence')}): {cand['url']}")
                rejected.append((t, cand, "low confidence"))
                time.sleep(args.delay)
                continue

            # Verify the proposed URL the same way we audit existing links.
            bucket, code, final, note = classify(cand["url"], http)
            if bucket == "dead":
                print(f"    -> proposed link is DEAD, dropping: {cand['url']}")
                rejected.append((t, cand, f"dead link ({note})"))
                time.sleep(args.delay)
                continue

            wrote = ""
            if args.apply:
                slug = write_pathway(engine, entity_id_by_slug, t, cand, bucket, note)
                wrote = f"  -> WROTE ai_verified" + (f" (entity={slug})" if slug else " (kept baseline entity)")
            print(f"    [OK] {bucket} [{code}]  {cand['url']}{wrote}")
            accepted.append((t, cand, (bucket, note)))
            snippets.append(override_snippet(t, cand, (bucket, note)))
            time.sleep(args.delay)

    # --- Reviewable diff ---
    report = []
    report.append("\n" + "=" * 72)
    verb = "written to compliance_pathway (basis='ai_verified')" if args.apply else "accepted"
    report.append(f"PROPOSALS — {len(accepted)} {verb}, {len(rejected)} rejected "
                  f"(of {len(targets)} researched)")
    if args.apply:
        report.append("Foreign links were auto-written. Rebuilds won't clobber them (basis guard).")
    else:
        dest = "BILL_OVERRIDES" if is_us else "FOREIGN_OVERRIDES"
        report.append(f"Review each, then paste approved entries into {dest} in "
                      "scripts/build_compliance_pathways.py (or re-run foreign with --apply).")
    report.append("Blocked-bucket links are correct-but-WAF'd (fine to keep); dead links were "
                  "already dropped.")
    report.append("=" * 72)
    if snippets and not args.apply:
        dest = "BILL_OVERRIDES" if is_us else "FOREIGN_OVERRIDES"
        report.append(f"\n{dest} = {{")
        report.append("\n".join(snippets))
        report.append("}")
    if rejected:
        report.append("\n# --- not proposed (verify manually if you disagree) ---")
        for t, cand, why in rejected:
            report.append(f"#   {t.region} {t.state or ''} {t.bill_number}: {why}"
                          + (f"  -> {cand.get('url')}" if cand.get("url") else ""))
    out = "\n".join(report)
    print(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"\nWritten to {args.out}")


if __name__ == "__main__":
    main()

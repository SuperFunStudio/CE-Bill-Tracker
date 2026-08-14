"""Recover real titles for rows whose title is a placeholder, an id, or a page header.

58 ce_relevant rows shipped with a title that identifies nothing:

  EU (28)  title = "Official Journal of the European Union" — eurlex._extract_title reads the act's
           name out of the HTML body, and for these documents the body opens with the OJ masthead
           instead of the act's type line, so the masthead became the title. Refetching does not help;
           the extractor produces the same wrong answer. The authoritative name lives in CELLAR and is
           queried here over SPARQL by CELEX.
  SE (30)  title = the row's own id ("sfs-2021-1000") — riksdagen's .html endpoint returns a fragment
           with no <title> tag, so the adapter's regex missed and it fell back to source_id. Fixed
           forward in app/ingestion/foreign.SwedenRiksdagenClient._fetch_title; this repairs the rows
           that landed before that.

Both fetch from the SAME endpoints the adapters now use, so a repaired row is byte-identical to one
ingested today — this is not a parallel source of truth.

    venv/Scripts/python.exe scripts/repair_law_titles.py \
        --dsn "postgresql://signalscout:PASSWORD@127.0.0.1:5462/signalscout" [--commit] [--only eu|se]

DRY RUN BY DEFAULT: prints old -> new for every row and writes nothing. Idempotent — it only selects
rows that still match a junk pattern, so a repaired row is never revisited. A row whose source can't
supply a title is reported and left exactly as it is.

Swedish titles are stored in Swedish, in both `title` and `title_native` (with title_native_lang='sv'),
matching how the corpus already holds CN and JP law. A Swedish name a reader can search beats an id
that means nothing; translation is a separate concern.
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import asyncpg
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.foreign import SE_META  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; AtlasCircular/1.0; +https://atlascircular.com)"}
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"

# The EN expression title of the work bearing this CELEX id. Asking for the EXPRESSION title (not the
# work) is what returns the act's full official name rather than a bare identifier.
SPARQL_Q = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?t WHERE {{
  ?w cdm:resource_legal_id_celex "{celex}"^^<http://www.w3.org/2001/XMLSchema#string> .
  ?e cdm:expression_belongs_to_work ?w ;
     cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
     cdm:expression_title ?t .
}} LIMIT 1"""

JUNK_SQL = """
 SELECT id, region, bill_number, celex_id, title FROM bills
 WHERE ce_relevant AND (
   title ILIKE 'official journal%%' OR title ILIKE 'publications office%%'
   OR title ~ '^[a-z]{2,5}-\\d{4}-\\d+$'
 )
"""
_WS = re.compile(r"\s+")


async def eu_title(client: httpx.AsyncClient, celex: str) -> str:
    try:
        r = await client.get(SPARQL, params={"query": SPARQL_Q.format(celex=celex),
                                             "format": "application/sparql-results+json"})
        r.raise_for_status()
        rows = r.json()["results"]["bindings"]
    except (httpx.HTTPError, ValueError, KeyError) as e:
        print(f"   ! {celex}: SPARQL failed ({type(e).__name__})")
        return ""
    return _WS.sub(" ", rows[0]["t"]["value"]).strip() if rows else ""


async def se_title(client: httpx.AsyncClient, doc_id: str) -> str:
    try:
        r = await client.get(SE_META.format(id=doc_id))
        r.raise_for_status()
        titel = ((r.json().get("dokumentstatus") or {}).get("dokument") or {}).get("titel")
    except (httpx.HTTPError, ValueError, AttributeError) as e:
        print(f"   ! {doc_id}: riksdagen failed ({type(e).__name__})")
        return ""
    return _WS.sub(" ", titel or "").strip()


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None, help="Target DSN (defaults to app DATABASE_URL).")
    ap.add_argument("--commit", action="store_true", help="Write. Default is a dry run.")
    ap.add_argument("--only", choices=("eu", "se"), default=None, help="Repair one source only.")
    args = ap.parse_args()

    dsn = args.dsn
    if not dsn:
        from app.config import settings
        dsn = settings.database_url

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(JUNK_SQL)
        # Rate-limited politely: these are public research endpoints and the whole job is ~58 requests.
        async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers=UA) as client:
            fixed: list[tuple[int, str, bool]] = []   # (id, title, is_swedish)
            missed = 0
            for r in rows:
                is_eu = r["region"] == "EU"
                if args.only == "eu" and not is_eu:
                    continue
                if args.only == "se" and is_eu:
                    continue
                if is_eu:
                    new = await eu_title(client, r["celex_id"] or r["bill_number"])
                else:
                    new = await se_title(client, r["bill_number"])
                if not new or new.lower() == (r["title"] or "").lower():
                    missed += 1
                    print(f"   - [{r['region']}] {r['bill_number']}: no title available, left as is")
                    continue
                fixed.append((r["id"], new, not is_eu))
                print(f"   [{r['region']}] {r['title'][:40]!r}\n       -> {new[:150]!r}")
                await asyncio.sleep(0.4)

        print(f"\ncandidates {len(rows)} | repairable {len(fixed)} | unrecoverable {missed}")
        if not args.commit:
            print("DRY RUN — nothing written. Re-run with --commit to apply.")
            return

        async with conn.transaction():
            for bill_id, title, swedish in fixed:
                if swedish:
                    await conn.execute(
                        "UPDATE bills SET title=$1, title_native=$1, title_native_lang='sv', "
                        "updated_at=now() WHERE id=$2", title, bill_id)
                else:
                    await conn.execute(
                        "UPDATE bills SET title=$1, updated_at=now() WHERE id=$2", title, bill_id)
        print(f"COMMITTED — {len(fixed)} titles repaired.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

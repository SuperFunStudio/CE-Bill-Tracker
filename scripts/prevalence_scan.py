"""Estimate how prevalent each candidate compliance dimension is in the corpus, to prioritize which
to extract next. For each dimension we count DISTINCT ce_relevant bills whose stored full text mentions
any of a set of English + native-language terms (so non-English bills aren't undercounted).

This is a TOPIC-MENTION proxy, not a provision count: "fee" appearing in text ≠ a structured fee
provision. Treat the numbers as an upper-bound signal for relative prioritization, not ground truth.
Auto-detects the `region` column so it runs on both the multi-region dev DB and the old US-only prod DB.

    python scripts/prevalence_scan.py --dsn "postgresql://signalscout:PW@127.0.0.1:5434/signalscout_dev"
    python scripts/prevalence_scan.py --dsn "postgresql://signalscout:PW@127.0.0.1:5434/signalscout"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402

ENGLISH_REGIONS = ("US", "EU", "UK", "IE", "CA", "AU", "ZA")

# Candidate secondary dimensions -> terms (English first, then native for fr/de/es/ja/zh and a few
# others). Substring match via ILIKE, so keep terms specific enough to limit obvious false positives.
DIMENSIONS: dict[str, list[str]] = {
    "collection_targets": [
        "collection target", "recycling target", "recovery target", "recycling rate",
        "collection rate", "recovery rate", "objectif de collecte", "objectif de recyclage",
        "taux de collecte", "sammelquote", "recyclingquote", "verwertungsquote",
        "objetivo de recogida", "tasa de reciclado", "回収率", "リサイクル率", "再商品化率",
        "回收率", "回收目标",
    ],
    "fee_amounts": [
        "per tonne", "per ton", "/tonne", "per unit of", "eco-contribution", "éco-contribution",
        "redevance", "barème", "beteiligungsentgelt", "gebühr", "tarifa", "importe de",
        "処理費", "料金", "元/吨",
    ],
    "producer_threshold": [
        "de minimis", "small producer", "exemption threshold", "annual turnover", "gross revenue",
        "tonnes per year", "tons per year", "chiffre d'affaires", "umsatzschwelle", "bagatell",
        "umbral", "小規模事業者",
    ],
    "bans_restrictions": [
        "shall not be placed on the market", "is prohibited", "are prohibited", "ban on",
        "restriction on", "il est interdit", "interdiction", "verbot", "verboten", "prohibición",
        "prohibido", "禁止", "販売禁止", "禁止销售",
    ],
    "fee_revenue_use": [
        "shall be used to fund", "reimburse municipalities", "reimburse local", "revenue shall",
        "proceeds shall", "affectation", "zweckbindung",
    ],
    "reuse_refill_targets": [
        "reuse target", "refill", "reusable packaging", "return rate", "réemploi", "réutilisation",
        "mehrweg", "reutilización", "reutilizable", "リユース", "再利用", "重复使用",
    ],
    "labeling": [
        "labelling requirement", "labeling requirement", "marking requirement", "recyclability label",
        "on-pack", "étiquetage", "marquage", "kennzeichnung", "etiquetado", "表示義務", "ラベル",
        "标识", "标签",
    ],
    "pro_structure": [
        "producer responsibility organization", "producer responsibility organisation",
        "stewardship organization", "eco-organisme", "needs assessment", "competing producer",
        "organización de responsabilidad",
    ],
    "compliance_flexibility": [
        "alternative compliance", "tradable", "trading scheme", "credit scheme", "recycling credit",
        "offset",
    ],
    "sunset_review": [
        "sunset", "shall be reviewed", "repealed on", "this act expires", "subject to review",
        "clause de réexamen", "überprüfung", "revisión",
    ],
}


def _normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return dsn if prefix == "postgresql+asyncpg://" else "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


async def _count(db, patterns: list[str], region_clause: str, params: dict) -> int:
    sql = ("SELECT count(DISTINCT b.id) FROM bills b JOIN bill_texts bt ON bt.bill_id = b.id "
           "WHERE b.ce_relevant AND bt.text IS NOT NULL AND bt.text ILIKE ANY(:pats)" + region_clause)
    return await db.scalar(text(sql), {**params, "pats": [f"%{p}%" for p in patterns]}) or 0


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()
    engine = create_async_engine(_normalize_dsn(args.dsn or settings.database_url))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        has_region = (await db.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='bills' AND column_name='region'"))).first() is not None
        denom = await db.scalar(text(
            "SELECT count(*) FROM bills b JOIN bill_texts bt ON bt.bill_id=b.id "
            "WHERE b.ce_relevant AND bt.text IS NOT NULL")) or 0
        print(f"text-ready ce_relevant bills: {denom}   (region column: {has_region})\n")

        if has_region:
            en_clause = " AND b.region = ANY(:en)"
            nonen_clause = " AND NOT (b.region = ANY(:en))"
            hdr = f"{'dimension':<24}{'bills':>7}{'%':>6}{'EN':>7}{'non-EN':>8}"
        else:
            en_clause = nonen_clause = ""
            hdr = f"{'dimension':<24}{'bills':>7}{'%':>6}"
        print(hdr)
        print("-" * len(hdr))

        results = []
        for dim, pats in DIMENSIONS.items():
            total = await _count(db, pats, "", {})
            row = {"dim": dim, "total": total, "pct": (total / denom * 100) if denom else 0}
            if has_region:
                row["en"] = await _count(db, pats, en_clause, {"en": list(ENGLISH_REGIONS)})
                row["nonen"] = await _count(db, pats, nonen_clause, {"en": list(ENGLISH_REGIONS)})
            results.append(row)

        for r in sorted(results, key=lambda x: -x["total"]):
            if has_region:
                print(f"{r['dim']:<24}{r['total']:>7}{r['pct']:>5.0f}%{r['en']:>7}{r['nonen']:>8}")
            else:
                print(f"{r['dim']:<24}{r['total']:>7}{r['pct']:>5.0f}%")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

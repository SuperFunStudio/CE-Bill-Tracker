"""
One-time script to fix mojibake in bill titles and descriptions.

Corrupted rows contain UTF-8 bytes that were stored as Latin-1, producing
sequences like â€" (em dash), â€™ (right single quote), etc.

Re-encoding strategy: row.encode('latin-1').decode('utf-8')
This reverses the original corruption by treating each character as a raw byte
and re-interpreting those bytes as UTF-8.

Usage:
    DATABASE_URL=postgresql://... python scripts/fix_encoding_data.py
    # Add --dry-run to preview without writing
"""
import asyncio
import os
import sys
import argparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _try_fix(value: str | None) -> str | None:
    """Fix known mojibake sequences in bill titles/descriptions."""
    if not value:
        return value
    return value.replace("\u00e2\u20ac\u201d", "\u2014")  # â€" → —


async def fix_encoding(dry_run: bool) -> None:
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(
        url,
        connect_args={"server_settings": {"client_encoding": "utf8"}},
    )

    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT id, title, description FROM bills "
            "WHERE title LIKE '%â%' OR title LIKE '%Ã%' "
            "OR description LIKE '%â%' OR description LIKE '%Ã%'"
        ))
        rows = result.fetchall()
        print(f"Found {len(rows)} rows with suspected mojibake")

fixed_count = 0
        for row in rows:
            new_title = _try_fix(row.title)
            new_desc = _try_fix(row.description)
            if new_title != row.title or new_desc != row.description:
                if dry_run:
                    print(f"  [DRY RUN] id={row.id}: {row.title!r} → {new_title!r}")
                else:
                    await conn.execute(
                        text("UPDATE bills SET title = :t, description = :d WHERE id = :id"),
                        {"t": new_title, "d": new_desc, "id": row.id},
                    )
                fixed_count += 1

        if not dry_run and fixed_count:
            await conn.commit()
            print(f"Fixed {fixed_count} rows.")
        elif dry_run:
            print(f"Would fix {fixed_count} rows (dry run — no changes written).")
        else:
            print("No rows needed fixing.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix mojibake in bill titles/descriptions")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()
    asyncio.run(fix_encoding(dry_run=args.dry_run))

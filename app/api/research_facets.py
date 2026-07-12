"""Facet resolution for the Atlas research engine — turns a natural-language question into structured
filters over the corpus, deterministically (no per-request LLM, so paging is stable and free).

The essential facet is **jurisdiction**: region/country isn't in a bill's (often foreign-language)
body text, so "examples from France" can't be served by full-text search — it must become a
`jurisdiction_id` filter. We resolve places by scanning the question against the `jurisdictions`
alias table ("France"/"French" -> FR node), expand to the subtree ("US" -> all states), and strip the
matched place words out of the residual free text so FTS runs on the substantive terms only.

Dimension + free-text handling stay in app/api/research.py; this module owns the geographic facet.
An LLM router for messy phrasing / follow-ups is a later add (A2) — deterministic is the right v1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Jurisdiction

# Words that shouldn't count as "meaningful" free text when deciding text-search vs a plain listing.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "from", "about", "any",
    "is", "are", "there", "what", "which", "how", "do", "does", "bills", "bill", "law", "laws",
    "records", "record", "examples", "example", "compare", "comparison", "show", "me", "us",  # "us" here is the pronoun; the country is caught as an uppercase code
    "list", "give", "tell", "find", "get", "that", "this", "these", "those", "their", "its",
})


@dataclass
class Facets:
    """Resolved structured interpretation of a question."""
    place_ids: list[int]      # subtree-expanded jurisdiction ids ([] = no geographic filter)
    place_labels: list[str]   # display names of the matched nodes ("France", "United States")
    free_text: str            # the question with matched place aliases removed
    raw_question: str

    def meaningful_terms(self) -> list[str]:
        return [w for w in re.findall(r"[a-z0-9]{3,}", self.free_text.lower()) if w not in _STOPWORDS]


async def _load_nodes(db: AsyncSession):
    return (await db.execute(
        select(Jurisdiction.id, Jurisdiction.name, Jurisdiction.path, Jurisdiction.aliases)
    )).all()


async def resolve_facets(db: AsyncSession, question: str) -> Facets:
    nodes = await _load_nodes(db)
    lower_q = f" {question.lower()} "
    stripped = question
    matched: dict[int, object] = {}  # jurisdiction id -> node row (dedupe)

    for n in nodes:
        for alias in n.aliases:  # stored lowercased
            if len(alias) >= 4:
                pat = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
                if pat.search(lower_q):
                    matched[n.id] = n
                    stripped = pat.sub(" ", stripped)
                    break
            else:
                # 2–3 char codes (US, EU, FR, CA) only match as a standalone UPPERCASE token, so the
                # pronoun "us" or the word "in" can't false-trigger a jurisdiction filter.
                pat = re.compile(r"\b" + re.escape(alias.upper()) + r"\b")
                if pat.search(question):
                    matched[n.id] = n
                    stripped = pat.sub(" ", stripped)
                    break

    matched_paths = {n.path for n in matched.values()}
    place_ids = [
        n.id for n in nodes
        if any(n.path == p or n.path.startswith(p + ".") for p in matched_paths)
    ]
    place_labels = sorted({n.name for n in matched.values()})
    free_text = re.sub(r"\s+", " ", stripped).strip()
    return Facets(place_ids=place_ids, place_labels=place_labels, free_text=free_text,
                  raw_question=question)

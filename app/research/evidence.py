"""External evidence sources for documented-outcome research (NewsAPI + FRED).

These are *corroboration* helpers, not metric extractors. The honest division of labour:

  * Claude web_search/web_fetch  — primary engine; finds agency reports / program stats with the
                                   historical depth that documented outcomes (acres, tonnage, rates)
                                   usually require.
  * NewsAPI  (search_news)       — a recent-movement signal. The free/developer tier only returns
                                   articles from roughly the last month, so it mostly corroborates
                                   *recent* enactments; it is not a historical archive. Use it to
                                   catch "this just produced X" press, then let the model cite the
                                   underlying primary source it points to.
  * FRED     (fred_*)            — macro time-series only. It can NEVER attribute a number to one
                                   law (a state's recycling employment moves for a hundred reasons),
                                   so anything that leans on it must be marked attribution="associated"
                                   and framed as context, not as the headline metric.

Every function fails soft: a missing key or a network blip returns an empty result rather than
raising, so a research run degrades gracefully instead of dying mid-batch.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import settings

NEWSAPI_URL = "https://newsapi.org/v2/everything"
FRED_BASE = "https://api.stlouisfed.org/fred"


@dataclass
class NewsHit:
    title: str
    description: str | None
    url: str
    source: str | None
    published_at: str | None

    def as_line(self) -> str:
        """Compact one-liner to drop into an LLM prompt."""
        when = (self.published_at or "")[:10]
        src = self.source or "?"
        desc = (self.description or "").strip().replace("\n", " ")
        if len(desc) > 220:
            desc = desc[:217] + "..."
        return f"- [{when} · {src}] {self.title.strip()} — {desc} ({self.url})"


def search_news(
    query: str,
    *,
    http: httpx.Client | None = None,
    page_size: int = 8,
    language: str = "en",
) -> list[NewsHit]:
    """Top NewsAPI `everything` hits for a query, most-relevant first. Returns [] on any failure
    (no key, rate-limited, network) so callers never have to guard. NB: free-tier results are capped
    to roughly the last month — treat empty as "no *recent* coverage", not "no coverage ever"."""
    key = settings.newsapi_key
    if not key or not query.strip():
        return []
    params = {
        "q": query,
        "language": language,
        "sortBy": "relevancy",
        "pageSize": max(1, min(page_size, 20)),
        "apiKey": key,
    }
    owns = http is None
    client = http or httpx.Client(timeout=20.0)
    try:
        r = client.get(NEWSAPI_URL, params=params)
        if r.status_code != 200:
            return []
        articles = (r.json() or {}).get("articles") or []
    except (httpx.HTTPError, ValueError):
        return []
    finally:
        if owns:
            client.close()

    hits: list[NewsHit] = []
    for a in articles:
        url = a.get("url")
        title = a.get("title")
        if not url or not title:
            continue
        hits.append(
            NewsHit(
                title=title,
                description=a.get("description"),
                url=url,
                source=((a.get("source") or {}).get("name")),
                published_at=a.get("publishedAt"),
            )
        )
    return hits


@dataclass
class FredSeries:
    series_id: str
    title: str
    units: str | None
    frequency: str | None
    latest_value: str | None
    latest_date: str | None

    def as_line(self) -> str:
        val = f"{self.latest_value} ({self.latest_date})" if self.latest_value else "no obs"
        return f"- FRED {self.series_id}: {self.title} [{self.units or '?'}, {self.frequency or '?'}] latest={val}"


def fred_search(query: str, *, http: httpx.Client | None = None, limit: int = 5) -> list[FredSeries]:
    """Search FRED for series matching a query and return each with its latest observation. Context
    only — see the module docstring on why FRED can't attribute a number to a single law. [] on any
    failure or missing key."""
    key = settings.fred_api_key
    if not key or not query.strip():
        return []
    owns = http is None
    client = http or httpx.Client(timeout=20.0)
    try:
        r = client.get(
            f"{FRED_BASE}/series/search",
            params={
                "search_text": query,
                "api_key": key,
                "file_type": "json",
                "limit": max(1, min(limit, 20)),
                "order_by": "popularity",
                "sort_order": "desc",
            },
        )
        if r.status_code != 200:
            return []
        series = (r.json() or {}).get("seriess") or []
    except (httpx.HTTPError, ValueError):
        return []

    out: list[FredSeries] = []
    try:
        for s in series:
            sid = s.get("id")
            if not sid:
                continue
            latest_val, latest_date = _fred_latest_obs(client, sid, key)
            out.append(
                FredSeries(
                    series_id=sid,
                    title=s.get("title") or sid,
                    units=s.get("units_short") or s.get("units"),
                    frequency=s.get("frequency_short") or s.get("frequency"),
                    latest_value=latest_val,
                    latest_date=latest_date,
                )
            )
    finally:
        if owns:
            client.close()
    return out


def _fred_latest_obs(client: httpx.Client, series_id: str, key: str) -> tuple[str | None, str | None]:
    """Most recent non-missing observation for a series, or (None, None)."""
    try:
        r = client.get(
            f"{FRED_BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
        )
        if r.status_code != 200:
            return None, None
        obs = (r.json() or {}).get("observations") or []
    except (httpx.HTTPError, ValueError):
        return None, None
    if not obs:
        return None, None
    o = obs[0]
    val = o.get("value")
    if val in (None, ".", ""):
        return None, o.get("date")
    return val, o.get("date")

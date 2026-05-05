"""Orchestration service for external book search.

Responsibilities:
- Fan out search/ISBN queries to all configured providers concurrently.
- Deduplicate candidates by ISBN (keep the most complete result per ISBN).
- Cache results in the external_book_results table (24-hour TTL for ISBN,
  1-hour TTL for keyword queries).
- Convert an ExternalBookCandidate to a BookCreate for import.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.external_book_result import ExternalBookResult
from app.schemas.external_book import ExternalBookCandidate
from app.services.external_books import BookProvider, get_all_providers

logger = logging.getLogger(__name__)

_ISBN_CACHE_TTL = timedelta(hours=24)
_SEARCH_CACHE_TTL = timedelta(hours=1)


# ---------------------------------------------------------------------------
# ISBN normalisation
# ---------------------------------------------------------------------------

def clean_isbn(value: str) -> str:
    return "".join(c for c in value if c.isdigit() or c.upper() == "X")


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _search_query_variants(query: str, mode: str | None = None) -> list[str]:
    """Build extra query forms for Chinese title search.

    mode values:
      None / "title"         plain title search
      "title_author"         treat second token as author
      "title_publisher"      treat second token as publisher
    """
    normalized = " ".join(query.split())
    if not normalized:
        return []

    variants = [normalized]
    if _contains_cjk(normalized):
        variants.extend(
            [
                f'"{normalized}"',
                f"intitle:{normalized}",
                f'intitle:"{normalized}"',
                f"{normalized} 中文",
                f"{normalized} 简体中文",
            ]
        )
        parts = normalized.split()
        if len(parts) >= 2:
            title = parts[0]
            rest = " ".join(parts[1:])
            if mode == "title_publisher":
                variants.append(f"intitle:{title} inpublisher:{rest}")
                variants.append(f"{title} {rest}")
            else:
                # default and "title_author" both generate author-scoped variants
                variants.append(f"intitle:{title} inauthor:{rest}")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _fold_for_match(text: str) -> str:
    traditional_to_simplified = str.maketrans(
        {
            "國": "国",
            "鄉": "乡",
            "費": "费",
            "孝": "孝",
            "學": "学",
            "書": "书",
            "臺": "台",
            "台": "台",
            "灣": "湾",
            "傳": "传",
            "簡": "简",
            "體": "体",
            "華": "华",
            "與": "与",
            "論": "论",
            "會": "会",
            "社": "社",
        }
    )
    return "".join(text.lower().translate(traditional_to_simplified).split())


def _title_query(query: str) -> str:
    normalized = " ".join(query.split())
    if _contains_cjk(normalized):
        return normalized.split()[0]
    return normalized


def _rank_candidates(
    candidates: list[ExternalBookCandidate],
    query: str,
) -> list[ExternalBookCandidate]:
    title_query = _fold_for_match(_title_query(query))
    if not title_query:
        return candidates

    def _rank(item: ExternalBookCandidate) -> tuple[int, int, int, int, int]:
        title = _fold_for_match(item.title)
        language = (item.language or "").lower()
        exact = int(title == title_query)
        starts = int(title.startswith(title_query))
        contains = int(title_query in title)
        zh = int(language.startswith("zh") or _contains_cjk(item.title))
        has_isbn = int(bool(item.isbn))
        return (-exact, -starts, -contains, -zh, -has_isbn)

    return sorted(candidates, key=_rank)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _load_cache(db: Session, cache_key: str, ttl: timedelta) -> list[ExternalBookCandidate] | None:
    cutoff = _now() - ttl
    rows = (
        db.query(ExternalBookResult)
        .filter(
            ExternalBookResult.query == cache_key,
            ExternalBookResult.created_at >= cutoff,
        )
        .all()
    )
    if not rows:
        return None
    candidates: list[ExternalBookCandidate] = []
    for row in rows:
        try:
            candidates.append(ExternalBookCandidate.model_validate_json(row.normalized_data))
        except Exception as exc:
            logger.debug("Cache deserialization error for row %s: %s", row.id, exc)
    return candidates if candidates else None


def _save_cache(
    db: Session,
    cache_key: str,
    candidates: list[ExternalBookCandidate],
) -> None:
    for candidate in candidates:
        raw_json = json.dumps(candidate.raw)
        norm_json = candidate.model_dump_json(exclude={"raw"})
        row = ExternalBookResult(
            query=cache_key,
            source=candidate.source,
            source_id=candidate.source_id,
            raw_data=raw_json,
            normalized_data=norm_json,
            created_at=_now(),
        )
        db.add(row)
    try:
        db.commit()
    except Exception as exc:
        logger.warning("Failed to cache search results: %s", exc)
        db.rollback()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(candidates: list[ExternalBookCandidate]) -> list[ExternalBookCandidate]:
    """Keep one candidate per ISBN and collapse exact no-ISBN duplicates."""
    seen_isbn: dict[str, ExternalBookCandidate] = {}
    seen_no_isbn: dict[tuple[str, str, str], ExternalBookCandidate] = {}

    def _score(item: ExternalBookCandidate) -> int:
        return sum(
            1
            for v in (
                item.title, item.author, item.publisher,
                item.publish_year, item.cover_url, item.summary,
                item.pages,
            )
            if v is not None
        )

    for c in candidates:
        if not c.isbn:
            key = (
                c.title.strip().lower(),
                (c.author or "").strip().lower(),
                c.source,
            )
            existing_no_isbn = seen_no_isbn.get(key)
            if existing_no_isbn is None or _score(c) > _score(existing_no_isbn):
                seen_no_isbn[key] = c
            continue
        existing = seen_isbn.get(c.isbn)
        if existing is None:
            seen_isbn[c.isbn] = c
        else:
            if _score(c) > _score(existing):
                seen_isbn[c.isbn] = c

    return list(seen_isbn.values()) + list(seen_no_isbn.values())


# ---------------------------------------------------------------------------
# Provider fan-out
# ---------------------------------------------------------------------------

async def _run_provider_search(
    provider: BookProvider, query: str, limit: int
) -> list[ExternalBookCandidate]:
    try:
        return await provider.search(query, limit)
    except Exception as exc:
        logger.warning("Provider %s search error: %s", provider.name, exc)
        return []


async def _run_provider_isbn(
    provider: BookProvider, isbn: str
) -> list[ExternalBookCandidate]:
    try:
        return await provider.lookup_isbn(isbn)
    except Exception as exc:
        logger.warning("Provider %s isbn error: %s", provider.name, exc)
        return []


async def _fetch_search(
    query: str,
    limit: int,
    providers: list[BookProvider],
    mode: str | None = None,
) -> list[ExternalBookCandidate]:
    query_variants = _search_query_variants(query, mode)
    per_variant_limit = min(max(limit, 10), 40)
    tasks = [
        _run_provider_search(provider, query_variant, per_variant_limit)
        for provider in providers
        for query_variant in query_variants
    ]
    if not tasks:
        return []
    results_per_provider: list[list[ExternalBookCandidate]] = await asyncio.gather(*tasks)
    combined = [c for batch in results_per_provider for c in batch]
    return _rank_candidates(_deduplicate(combined), query)[:limit]


async def _fetch_isbn(
    isbn: str,
    providers: list[BookProvider],
) -> list[ExternalBookCandidate]:
    tasks = [_run_provider_isbn(p, isbn) for p in providers]
    results_per_provider: list[list[ExternalBookCandidate]] = await asyncio.gather(*tasks)
    combined = [c for batch in results_per_provider for c in batch]
    return _deduplicate(combined)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def search_books(
    db: Session,
    query: str,
    limit: int = 10,
    providers: list[BookProvider] | None = None,
    mode: str | None = None,
    provider_filter: str | None = None,
) -> list[ExternalBookCandidate]:
    # Don't use the shared cache when a provider filter is active (partial results)
    use_cache = provider_filter is None
    cache_key = f"query:v3:{mode or 'title'}:{query}"
    if use_cache:
        cached = _load_cache(db, cache_key, _SEARCH_CACHE_TTL)
        if cached is not None:
            return cached[:limit]

    active_providers = providers if providers is not None else get_all_providers()
    if provider_filter:
        active_providers = [p for p in active_providers if p.name == provider_filter]
    candidates = await _fetch_search(query, limit, active_providers, mode=mode)
    if use_cache and candidates:
        _save_cache(db, cache_key, candidates)
    return candidates


async def lookup_isbn(
    db: Session,
    isbn: str,
    providers: list[BookProvider] | None = None,
) -> list[ExternalBookCandidate]:
    clean = clean_isbn(isbn)
    cache_key = f"isbn:{clean}"
    cached = _load_cache(db, cache_key, _ISBN_CACHE_TTL)
    if cached is not None:
        return cached

    active_providers = providers if providers is not None else get_all_providers()
    candidates = await _fetch_isbn(clean, active_providers)
    if candidates:
        _save_cache(db, cache_key, candidates)
    return candidates


def candidate_to_book_create_dict(
    candidate: ExternalBookCandidate,
    category_id: int | None = None,
    location_id: int | None = None,
) -> dict[str, Any]:
    """Map an ExternalBookCandidate to a dict suitable for BookCreate."""
    source_map = {
        "open_library": "isbn_lookup" if candidate.isbn else "title_search",
        "google_books": "isbn_lookup" if candidate.isbn else "title_search",
        "douban": "title_search",  # Douban suggest API does not return ISBNs
    }
    source = source_map.get(candidate.source, "title_search")

    return {
        "title": candidate.title,
        "subtitle": candidate.subtitle,
        "author": candidate.author,
        "translator": None,
        "publisher": candidate.publisher,
        "publish_year": candidate.publish_year,
        "isbn": candidate.isbn,
        "language": candidate.language,
        "pages": candidate.pages,
        "cover_url": candidate.cover_url,
        "summary": candidate.summary,
        "category_id": category_id,
        "location_id": location_id,
        "source": source,
        "tag_names": [],
    }

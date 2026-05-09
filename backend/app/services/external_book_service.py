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
import hashlib
import json
import logging
import uuid
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.external_book_result import ExternalBookResult
from app.schemas.external_book import ExternalBookCandidate
from app.services.external_books import BookProvider, get_all_providers

logger = logging.getLogger(__name__)

_ISBN_CACHE_TTL = timedelta(hours=1)
_SEARCH_CACHE_TTL = timedelta(hours=1)
_COVER_CACHE_DIR = "external-covers"
_TASK_TTL = timedelta(hours=1)
_FAST_RESULT_TIMEOUT_SECONDS = 2.0

_SEARCH_TASKS: dict[str, dict[str, Any]] = {}
_TASKS_LOCK = asyncio.Lock()


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
    provider_order: list[str] | None = None,
) -> list[ExternalBookCandidate]:
    title_query = _fold_for_match(_title_query(query))
    if not title_query:
        return candidates

    provider_priority = {
        provider_name: index for index, provider_name in enumerate(provider_order or [])
    }
    default_priority = len(provider_priority)

    def _rank(item: ExternalBookCandidate) -> tuple[int, int, int, int, int, int]:
        title = _fold_for_match(item.title)
        language = (item.language or "").lower()
        exact = int(title == title_query)
        starts = int(title.startswith(title_query))
        contains = int(title_query in title)
        zh = int(language.startswith("zh") or _contains_cjk(item.title))
        has_isbn = int(bool(item.isbn))
        source_priority = provider_priority.get(item.source, default_priority)
        return (-exact, -starts, -contains, -zh, -has_isbn, source_priority)

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


def _cover_proxy_url(url: str) -> str:
    return f"/api/search/cover?url={quote(url, safe='')}"


def _proxied_cover_url(source: str, url: str | None) -> str | None:
    if not url:
        return None
    if source in {"douban", "nlc", "isbn_work"}:
        return _cover_proxy_url(url)
    return url


def _normalize_cover_urls(candidates: list[ExternalBookCandidate]) -> list[ExternalBookCandidate]:
    normalized: list[ExternalBookCandidate] = []
    for candidate in candidates:
        cover_url = _proxied_cover_url(candidate.source, candidate.cover_url)
        if cover_url == candidate.cover_url:
            normalized.append(candidate)
        else:
            normalized.append(candidate.model_copy(update={"cover_url": cover_url}))
    return normalized


def _provider_config_cache_key(configs: dict[str, dict[str, Any]] | None) -> str:
    if not configs:
        return ""
    fragments: list[str] = []
    for provider in ("google_books", "isbn_work", "douban"):
        config = configs.get(provider, {})
        enabled = bool(config.get("enabled", True))
        has_api_key = bool(config.get("api_key"))
        has_extra = bool(config.get("extra"))
        fragments.append(f"{provider}:{int(enabled)}:{int(has_api_key)}:{int(has_extra)}")
    return "|".join(fragments)


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


async def _run_provider_search_variants(
    provider: BookProvider,
    query_variants: list[str],
    per_variant_limit: int,
) -> tuple[str, list[ExternalBookCandidate]]:
    tasks = [_run_provider_search(provider, query_variant, per_variant_limit) for query_variant in query_variants]
    if not tasks:
        return provider.name, []
    batches = await asyncio.gather(*tasks)
    return provider.name, [candidate for batch in batches for candidate in batch]


async def _run_provider_isbn_named(
    provider: BookProvider,
    isbn: str,
) -> tuple[str, list[ExternalBookCandidate]]:
    return provider.name, await _run_provider_isbn(provider, isbn)


def _apply_provider_order(
    providers: list[BookProvider],
    provider_order: list[str] | None,
) -> list[BookProvider]:
    """Sort providers by user preference while keeping unknown providers active."""
    if not provider_order:
        return providers

    priority = {name: index for index, name in enumerate(provider_order)}
    return sorted(providers, key=lambda provider: priority.get(provider.name, len(priority)))


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
    return _rank_candidates(
        _deduplicate(combined),
        query,
        provider_order=[provider.name for provider in providers],
    )[:limit]


async def _fetch_isbn(
    isbn: str,
    providers: list[BookProvider],
) -> list[ExternalBookCandidate]:
    tasks = [_run_provider_isbn(p, isbn) for p in providers]
    results_per_provider: list[list[ExternalBookCandidate]] = await asyncio.gather(*tasks)
    combined = [c for batch in results_per_provider for c in batch]
    return _deduplicate(combined)


async def _cleanup_search_tasks() -> None:
    cutoff = _now() - _TASK_TTL
    stale = [
        task_id
        for task_id, state in _SEARCH_TASKS.items()
        if state.get("updated_at", cutoff) < cutoff
    ]
    for task_id in stale:
        _SEARCH_TASKS.pop(task_id, None)


async def _create_search_task() -> str:
    async with _TASKS_LOCK:
        await _cleanup_search_tasks()
        task_id = uuid.uuid4().hex
        _SEARCH_TASKS[task_id] = {
            "items": [],
            "is_complete": False,
            "error": "",
            "updated_at": _now(),
        }
        return task_id


async def _update_search_task(
    task_id: str,
    *,
    items: list[ExternalBookCandidate] | None = None,
    is_complete: bool | None = None,
    error: str | None = None,
) -> None:
    async with _TASKS_LOCK:
        state = _SEARCH_TASKS.get(task_id)
        if not state:
            return
        if items is not None:
            state["items"] = _normalize_cover_urls(items)
        if is_complete is not None:
            state["is_complete"] = is_complete
        if error is not None:
            state["error"] = error
        state["updated_at"] = _now()


async def get_search_task(task_id: str) -> tuple[list[ExternalBookCandidate], bool] | None:
    async with _TASKS_LOCK:
        await _cleanup_search_tasks()
        state = _SEARCH_TASKS.get(task_id)
        if not state:
            return None
        return list(state["items"]), bool(state["is_complete"])


def _cache_completed_results(cache_key: str, candidates: list[ExternalBookCandidate]) -> None:
    db = SessionLocal()
    try:
        _save_cache(db, cache_key, candidates)
    finally:
        db.close()


async def _run_progressive_search_task(
    task_id: str,
    *,
    cache_key: str,
    query: str,
    limit: int,
    providers: list[BookProvider],
    mode: str | None,
) -> None:
    try:
        query_variants = _search_query_variants(query, mode)
        per_variant_limit = min(max(limit, 10), 40)
        tasks = [
            asyncio.create_task(_run_provider_search_variants(provider, query_variants, per_variant_limit))
            for provider in providers
        ]
        combined: list[ExternalBookCandidate] = []
        for done in asyncio.as_completed(tasks):
            _provider_name, batch = await done
            combined.extend(batch)
            ranked = _rank_candidates(
                _deduplicate(combined),
                query,
                provider_order=[provider.name for provider in providers],
            )[:limit]
            await _update_search_task(task_id, items=ranked, is_complete=False)
        final = _rank_candidates(
            _deduplicate(combined),
            query,
            provider_order=[provider.name for provider in providers],
        )[:limit]
        if final:
            _cache_completed_results(cache_key, final)
        await _update_search_task(task_id, items=final, is_complete=True)
    except Exception as exc:
        logger.warning("Progressive search task %s failed: %s", task_id, exc)
        await _update_search_task(task_id, is_complete=True, error=str(exc))


async def _run_progressive_isbn_task(
    task_id: str,
    *,
    cache_key: str,
    isbn: str,
    providers: list[BookProvider],
) -> None:
    try:
        tasks = [asyncio.create_task(_run_provider_isbn_named(provider, isbn)) for provider in providers]
        combined: list[ExternalBookCandidate] = []
        for done in asyncio.as_completed(tasks):
            _provider_name, batch = await done
            combined.extend(batch)
            await _update_search_task(task_id, items=_deduplicate(combined), is_complete=False)
        final = _deduplicate(combined)
        if final:
            _cache_completed_results(cache_key, final)
        await _update_search_task(task_id, items=final, is_complete=True)
    except Exception as exc:
        logger.warning("Progressive ISBN task %s failed: %s", task_id, exc)
        await _update_search_task(task_id, is_complete=True, error=str(exc))


async def _wait_for_fast_results(task_id: str, timeout_seconds: float) -> tuple[list[ExternalBookCandidate], bool]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        state = await get_search_task(task_id)
        if state is None:
            return [], True
        items, is_complete = state
        if items or is_complete or asyncio.get_running_loop().time() >= deadline:
            return items, is_complete
        await asyncio.sleep(0.1)


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
    provider_order: list[str] | None = None,
    provider_configs: dict[str, dict[str, Any]] | None = None,
) -> list[ExternalBookCandidate]:
    # Don't use the shared cache when a provider filter is active (partial results)
    use_cache = provider_filter is None
    order_key = ",".join(provider_order or [])
    config_key = _provider_config_cache_key(provider_configs)
    cache_key = f"query:v5:{mode or 'title'}:{order_key}:{config_key}:{query}"
    if use_cache:
        cached = _load_cache(db, cache_key, _SEARCH_CACHE_TTL)
        if cached is not None:
            return _normalize_cover_urls(cached[:limit])

    active_providers = providers if providers is not None else get_all_providers(provider_configs)
    active_providers = _apply_provider_order(active_providers, provider_order)
    if provider_filter:
        active_providers = [p for p in active_providers if p.name == provider_filter]
    candidates = await _fetch_search(query, limit, active_providers, mode=mode)
    if use_cache and candidates:
        _save_cache(db, cache_key, candidates)
    return _normalize_cover_urls(candidates)


async def search_books_progressive(
    db: Session,
    query: str,
    limit: int = 10,
    providers: list[BookProvider] | None = None,
    mode: str | None = None,
    provider_filter: str | None = None,
    provider_order: list[str] | None = None,
    provider_configs: dict[str, dict[str, Any]] | None = None,
    fast_timeout_seconds: float = _FAST_RESULT_TIMEOUT_SECONDS,
) -> tuple[list[ExternalBookCandidate], str | None, bool]:
    use_cache = provider_filter is None
    order_key = ",".join(provider_order or [])
    config_key = _provider_config_cache_key(provider_configs)
    cache_key = f"query:v6:{mode or 'title'}:{order_key}:{config_key}:{query}"
    if use_cache:
        cached = _load_cache(db, cache_key, _SEARCH_CACHE_TTL)
        if cached is not None:
            return _normalize_cover_urls(cached[:limit]), None, True

    active_providers = providers if providers is not None else get_all_providers(provider_configs)
    active_providers = _apply_provider_order(active_providers, provider_order)
    if provider_filter:
        active_providers = [p for p in active_providers if p.name == provider_filter]
    if not active_providers:
        return [], None, True

    task_id = await _create_search_task()
    asyncio.create_task(
        _run_progressive_search_task(
            task_id,
            cache_key=cache_key,
            query=query,
            limit=limit,
            providers=active_providers,
            mode=mode,
        )
    )
    items, is_complete = await _wait_for_fast_results(task_id, fast_timeout_seconds)
    return items, None if is_complete else task_id, is_complete


async def lookup_isbn(
    db: Session,
    isbn: str,
    providers: list[BookProvider] | None = None,
    provider_order: list[str] | None = None,
    provider_configs: dict[str, dict[str, Any]] | None = None,
) -> list[ExternalBookCandidate]:
    clean = clean_isbn(isbn)
    order_key = ",".join(provider_order or [])
    config_key = _provider_config_cache_key(provider_configs)
    cache_key = f"isbn:v3:{order_key}:{config_key}:{clean}"
    cached = _load_cache(db, cache_key, _ISBN_CACHE_TTL)
    if cached is not None:
        return _normalize_cover_urls(cached)

    active_providers = providers if providers is not None else get_all_providers(provider_configs)
    active_providers = _apply_provider_order(active_providers, provider_order)
    candidates = await _fetch_isbn(clean, active_providers)
    if candidates:
        _save_cache(db, cache_key, candidates)
    return _normalize_cover_urls(candidates)


async def lookup_isbn_progressive(
    db: Session,
    isbn: str,
    providers: list[BookProvider] | None = None,
    provider_order: list[str] | None = None,
    provider_configs: dict[str, dict[str, Any]] | None = None,
    fast_timeout_seconds: float = _FAST_RESULT_TIMEOUT_SECONDS,
) -> tuple[list[ExternalBookCandidate], str | None, bool]:
    clean = clean_isbn(isbn)
    order_key = ",".join(provider_order or [])
    config_key = _provider_config_cache_key(provider_configs)
    cache_key = f"isbn:v4:{order_key}:{config_key}:{clean}"
    cached = _load_cache(db, cache_key, _ISBN_CACHE_TTL)
    if cached is not None:
        return _normalize_cover_urls(cached), None, True

    active_providers = providers if providers is not None else get_all_providers(provider_configs)
    active_providers = _apply_provider_order(active_providers, provider_order)
    if not active_providers:
        return [], None, True

    task_id = await _create_search_task()
    asyncio.create_task(
        _run_progressive_isbn_task(
            task_id,
            cache_key=cache_key,
            isbn=clean,
            providers=active_providers,
        )
    )
    items, is_complete = await _wait_for_fast_results(task_id, fast_timeout_seconds)
    return items, None if is_complete else task_id, is_complete


def _cover_headers(url: str) -> dict[str, str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    if "doubanio.com" in url:
        headers["Referer"] = "https://book.douban.com/"
    elif "find.nlc.cn" in url:
        headers["Referer"] = "http://find.nlc.cn/"
    return headers


def _cover_extension(content_type: str) -> str:
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def _sniff_image_content_type(content: bytes, content_type: str) -> str | None:
    if content_type.startswith("image/"):
        return content_type
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"RIFF") and b"WEBP" in content[:16]:
        return "image/webp"
    return None


async def cache_external_cover(url: str) -> tuple[Path, str]:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    base_dir = Path(get_settings().upload_dir) / _COVER_CACHE_DIR
    base_dir.mkdir(parents=True, exist_ok=True)
    for existing in base_dir.glob(f"{digest}.*"):
        content_type = "image/png" if existing.suffix == ".png" else "image/webp" if existing.suffix == ".webp" else "image/jpeg"
        return existing, content_type

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=_cover_headers(url))
        resp.raise_for_status()
        content_type = _sniff_image_content_type(resp.content, resp.headers.get("content-type", ""))
        if not content_type:
            raise ValueError("remote cover is not an image")
        path = base_dir / f"{digest}{_cover_extension(content_type)}"
        path.write_bytes(resp.content)
        return path, content_type


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

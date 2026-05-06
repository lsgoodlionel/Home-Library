"""External book data provider package.

Adding a new provider:
1. Create a module in this package that inherits from BookProvider.
2. Implement `search` and `lookup_isbn`.
3. Add an instance to the list returned by `get_all_providers`.

Current providers and their strengths:
  nlc        — National Library of China; authoritative for Chinese books;
               no API key needed; no cover images.
  isbn_work  — Free Chinese ISBN database; very complete metadata incl.
               classification, translator, series; ISBN lookup only;
               requires ISBN_WORK_API_KEY env var.
  douban     — Douban suggest; good title/author for Chinese books;
               no ISBN/publisher/summary.
  google_books — Full metadata for most books; best for non-Chinese titles.
  open_library — Open, free; best for English-language titles.
"""

from .base import BookProvider
from .douban_books import DoubanBooksProvider
from .google_books import GoogleBooksProvider
from .isbn_work import IsbnWorkProvider
from .nlc import NLCProvider
from .open_library import OpenLibraryProvider

__all__ = [
    "BookProvider",
    "DoubanBooksProvider",
    "GoogleBooksProvider",
    "IsbnWorkProvider",
    "NLCProvider",
    "OpenLibraryProvider",
    "get_all_providers",
]


def get_all_providers() -> list[BookProvider]:
    """Return all configured providers in priority order.

    Search order rationale:
    - NLC first: authoritative Chinese records, no key needed
    - isbn_work: richest Chinese metadata when ISBN_WORK_API_KEY is set
                 (silently skipped when key is absent)
    - Douban: fills title/author/cover gaps for Chinese books
    - Google Books: comprehensive metadata esp. for non-Chinese titles
    - Open Library: free fallback, strong on English titles
    """
    return [
        NLCProvider(),
        IsbnWorkProvider(),
        DoubanBooksProvider(),
        GoogleBooksProvider(),
        OpenLibraryProvider(),
    ]

"""External book data provider package.

Adding a new provider:
1. Create a module in this package that inherits from BookProvider.
2. Implement `search` and `lookup_isbn`.
3. Add an instance to the list returned by `get_all_providers`.
"""

from .base import BookProvider
from .douban_books import DoubanBooksProvider
from .google_books import GoogleBooksProvider
from .open_library import OpenLibraryProvider

__all__ = [
    "BookProvider",
    "DoubanBooksProvider",
    "GoogleBooksProvider",
    "OpenLibraryProvider",
    "get_all_providers",
]


def get_all_providers() -> list[BookProvider]:
    # Douban first: best coverage for Chinese titles; Google/OpenLibrary for others
    return [DoubanBooksProvider(), GoogleBooksProvider(), OpenLibraryProvider()]

"""Abstract interface for external book data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.external_book import ExternalBookCandidate


class BookProvider(ABC):
    """Base class for external book search providers.

    Each provider must implement `search` and `lookup_isbn`.
    Failures in one provider must not propagate to callers; the orchestration
    service handles exception isolation.
    """

    name: str

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[ExternalBookCandidate]:
        """Search by title and/or author keyword."""
        ...

    @abstractmethod
    async def lookup_isbn(self, isbn: str) -> list[ExternalBookCandidate]:
        """Look up a specific ISBN. Returns a list (may be empty)."""
        ...

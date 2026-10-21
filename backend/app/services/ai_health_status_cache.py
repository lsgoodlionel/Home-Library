from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import Callable

from app.schemas.ai import AIHealthResponse
from app.services.ai_providers.base import AIProviderModelList


class AIHealthStatusCache:
    def __init__(self, *, max_entries: int = 128) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple[int, str], AIHealthResponse] = OrderedDict()
        self._lock = Lock()

    def get(self, user_id: int, fingerprint: str) -> AIHealthResponse:
        with self._lock:
            return self._entries.get((user_id, fingerprint), AIHealthResponse())

    def put(self, user_id: int, fingerprint: str, status: AIHealthResponse) -> None:
        key = (user_id, fingerprint)
        with self._lock:
            self._entries[key] = status
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate_user(self, user_id: int) -> None:
        with self._lock:
            for key in [key for key in self._entries if key[0] == user_id]:
                del self._entries[key]

    def invalidate_all(self) -> None:
        with self._lock:
            self._entries.clear()


ai_health_status_cache = AIHealthStatusCache()


class ProviderModelCache:
    def __init__(
        self,
        *,
        max_entries: int = 128,
        ttl_seconds: float = 300.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[
            tuple[int, str, str],
            tuple[float, AIProviderModelList],
        ] = OrderedDict()
        self._lock = Lock()

    def get(
        self,
        user_id: int,
        provider: str,
        fingerprint: str,
    ) -> AIProviderModelList | None:
        key = (user_id, provider, fingerprint)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, models = entry
            if self._clock() - stored_at >= self._ttl_seconds:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return models

    def put(
        self,
        user_id: int,
        provider: str,
        fingerprint: str,
        models: AIProviderModelList,
    ) -> None:
        if not isinstance(models, AIProviderModelList):
            raise TypeError("models must be an AIProviderModelList")
        key = (user_id, provider, fingerprint)
        with self._lock:
            self._entries[key] = (self._clock(), models)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate_user(self, user_id: int) -> None:
        with self._lock:
            for key in [key for key in self._entries if key[0] == user_id]:
                del self._entries[key]

    def invalidate_all(self) -> None:
        with self._lock:
            self._entries.clear()


provider_model_cache = ProviderModelCache()

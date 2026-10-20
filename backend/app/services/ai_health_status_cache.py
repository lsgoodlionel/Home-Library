from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from app.schemas.ai import AIHealthResponse


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

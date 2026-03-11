from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class CacheEntry:
    value: dict[str, object]
    expires_at: float


class TtlCache:
    def __init__(self, ttl_seconds: int, max_items: int) -> None:
        self._ttl_seconds: int = ttl_seconds
        self._max_items: int = max_items
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()

    def get(self, key: str) -> dict[str, object] | None:
        now: float = time.time()
        entry: CacheEntry | None = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return entry.value

    def set(self, key: str, value: dict[str, object]) -> None:
        now: float = time.time()
        self._entries[key] = CacheEntry(value=value, expires_at=now + self._ttl_seconds)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_items:
            self._entries.popitem(last=False)

    def summary(self) -> dict[str, object]:
        now: float = time.time()
        expired_keys: list[str] = [
            key for key, entry in self._entries.items() if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)
        return {
            "ttl_seconds": self._ttl_seconds,
            "max_items": self._max_items,
            "items": len(self._entries),
        }

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class PoolEntry:
    value: str
    cooldown_until: float = 0.0
    reserved_until: float = 0.0
    successes: int = 0
    failures: int = 0
    last_error: str | None = None


class RoundRobinPool:
    def __init__(self, name: str, values: list[str]) -> None:
        if not values:
            raise ValueError(f"{name}: values must not be empty")

        self._name: str = name
        self._entries: list[PoolEntry] = [PoolEntry(value=x) for x in values]
        self._cursor: int = 0
        self._lock: threading.Lock = threading.Lock()

    def acquire(self) -> tuple[int, str] | None:
        now: float = time.time()
        with self._lock:
            total: int = len(self._entries)
            for offset in range(total):
                idx: int = (self._cursor + offset) % total
                entry: PoolEntry = self._entries[idx]
                if entry.cooldown_until <= now and entry.reserved_until <= now:
                    self._cursor = (idx + 1) % total
                    return idx, entry.value
        return None

    def reserve(self, index: int, seconds: float) -> None:
        now: float = time.time()
        if seconds <= 0:
            return

        with self._lock:
            entry: PoolEntry = self._entries[index]
            proposed_until: float = now + seconds
            if proposed_until > entry.reserved_until:
                entry.reserved_until = proposed_until

    def next_available_in(self) -> float | None:
        now: float = time.time()
        with self._lock:
            wait_values: list[float] = []
            for entry in self._entries:
                available_at: float = max(entry.cooldown_until, entry.reserved_until)
                wait_values.append(max(available_at - now, 0.0))

        if not wait_values:
            return None
        return min(wait_values)

    def mark_success(self, index: int) -> None:
        with self._lock:
            entry: PoolEntry = self._entries[index]
            entry.successes += 1
            entry.last_error = None

    def mark_failure(self, index: int, cooldown_seconds: float, error: str) -> None:
        now: float = time.time()
        with self._lock:
            entry: PoolEntry = self._entries[index]
            entry.failures += 1
            entry.last_error = error
            proposed_until: float = now + max(cooldown_seconds, 0.0)
            if proposed_until > entry.cooldown_until:
                entry.cooldown_until = proposed_until

    def summary(self) -> dict[str, object]:
        now: float = time.time()
        with self._lock:
            total: int = len(self._entries)
            available: int = sum(
                1
                for entry in self._entries
                if entry.cooldown_until <= now and entry.reserved_until <= now
            )

            items: list[dict[str, object]] = []
            for idx, entry in enumerate(self._entries):
                cooldown_remaining: float = max(entry.cooldown_until - now, 0.0)
                reserved_remaining: float = max(entry.reserved_until - now, 0.0)
                items.append(
                    {
                        "index": idx,
                        "cooldown_remaining_seconds": round(cooldown_remaining, 3),
                        "reserved_remaining_seconds": round(reserved_remaining, 3),
                        "successes": entry.successes,
                        "failures": entry.failures,
                        "last_error": entry.last_error,
                    }
                )

            return {
                "name": self._name,
                "total": total,
                "available": available,
                "cursor": self._cursor,
                "items": items,
            }

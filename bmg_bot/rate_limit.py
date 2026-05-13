from __future__ import annotations

import asyncio
import time
from collections import deque


class TokenBucket:
    """Thread-safe async token bucket (capacity tokens, refill `rate` per second)."""

    def __init__(self, *, capacity: float, refill_per_sec: float) -> None:
        self.capacity = float(capacity)
        self.rate = max(0.001, float(refill_per_sec))
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, cost: float = 1.0) -> float:
        """Wait until `cost` tokens available; returns seconds waited."""
        waited = 0.0
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= cost:
                    self._tokens -= cost
                    return waited
                need = cost - self._tokens
                sleep_for = need / self.rate
            await asyncio.sleep(sleep_for)
            waited += sleep_for


class SlidingWindowCounter:
    """Counts events in a sliding time window (for memory-bounded flood tracking)."""

    def __init__(self, *, window_sec: float, max_entries_per_key: int = 256) -> None:
        self.window_sec = window_sec
        self.max_entries = max_entries_per_key
        self._data: dict[int, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def add(self, key: int) -> int:
        now = time.monotonic()
        cutoff = now - self.window_sec
        async with self._lock:
            dq = self._data.get(key)
            if dq is None:
                dq = deque()
                self._data[key] = dq
            dq.append(now)
            while dq and dq[0] < cutoff:
                dq.popleft()
            while len(dq) > self.max_entries:
                dq.popleft()
            return len(dq)

    async def prune_global(self, *, max_keys: int) -> None:
        """Drop oldest keys when dict grows too large."""
        async with self._lock:
            if len(self._data) <= max_keys:
                return
            items = sorted(self._data.items(), key=lambda kv: kv[1][0] if kv[1] else 0)
            overflow = len(self._data) - max_keys
            for k, _ in items[:overflow]:
                self._data.pop(k, None)

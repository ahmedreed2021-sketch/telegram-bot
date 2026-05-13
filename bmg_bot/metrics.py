from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class RuntimeMetrics:
    """Lightweight in-process counters for health and tuning (bounded memory)."""

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    updates_total: int = 0
    handler_errors: int = 0
    jobs_enqueued: int = 0
    jobs_completed: int = 0
    jobs_dead: int = 0
    jobs_retried: int = 0
    flood_waits: int = 0
    telegram_retries: int = 0
    start_commands: int = 0
    start_throttled: int = 0
    relay_batches: int = 0
    relay_messages: int = 0
    last_enqueue_ts: float = 0.0
    last_complete_ts: float = 0.0
    queue_depth_hint: int = 0

    async def bump(self, **deltas: int) -> None:
        async with self._lock:
            for k, v in deltas.items():
                setattr(self, k, getattr(self, k, 0) + v)

    async def note_enqueue(self, n: int = 1) -> None:
        async with self._lock:
            self.jobs_enqueued += n
            self.last_enqueue_ts = time.time()

    async def note_complete(self, n: int = 1) -> None:
        async with self._lock:
            self.jobs_completed += n
            self.last_complete_ts = time.time()

    async def set_queue_depth_hint(self, n: int) -> None:
        async with self._lock:
            self.queue_depth_hint = n

    async def snapshot(self) -> dict[str, int | float]:
        async with self._lock:
            return {
                "updates_total": self.updates_total,
                "handler_errors": self.handler_errors,
                "jobs_enqueued": self.jobs_enqueued,
                "jobs_completed": self.jobs_completed,
                "jobs_dead": self.jobs_dead,
                "jobs_retried": self.jobs_retried,
                "flood_waits": self.flood_waits,
                "telegram_retries": self.telegram_retries,
                "start_commands": self.start_commands,
                "start_throttled": self.start_throttled,
                "relay_batches": self.relay_batches,
                "relay_messages": self.relay_messages,
                "queue_depth_hint": self.queue_depth_hint,
                "last_enqueue_ts": self.last_enqueue_ts,
                "last_complete_ts": self.last_complete_ts,
                "monotonic_now": time.monotonic(),
            }

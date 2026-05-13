from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError

if TYPE_CHECKING:
    from bmg_bot.metrics import RuntimeMetrics

log = logging.getLogger(__name__)

T = TypeVar("T")


async def call_with_telegram_retry(
    op: Callable[[], Awaitable[T]],
    *,
    metrics: RuntimeMetrics | None = None,
    max_attempts: int = 12,
    base_label: str = "telegram",
) -> T:
    """Retry Telegram calls with FloodWait / network backoff (crash-safe loop)."""
    attempt = 0
    while True:
        try:
            return await op()
        except TelegramRetryAfter as e:
            attempt += 1
            wait = float(getattr(e, "retry_after", 1.0)) + random.uniform(0.05, 0.35)
            if metrics:
                await metrics.bump(flood_waits=1, telegram_retries=1)
            log.warning(
                "%s: FloodWait retry_after=%s attempt=%s/%s sleeping=%.2fs",
                base_label,
                getattr(e, "retry_after", None),
                attempt,
                max_attempts,
                wait,
            )
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(wait)
        except (TelegramNetworkError, TelegramServerError, asyncio.TimeoutError, OSError) as e:
            attempt += 1
            backoff = min(2 ** min(attempt, 8), 60.0) + random.uniform(0, 0.5)
            if metrics:
                await metrics.bump(telegram_retries=1)
            log.warning(
                "%s: network/server error %s attempt=%s/%s sleep=%.2fs",
                base_label,
                e,
                attempt,
                max_attempts,
                backoff,
            )
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(backoff)

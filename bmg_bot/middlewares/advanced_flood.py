from __future__ import annotations

import time
from typing import Any, Awaitable, Callable
from xml.sax import handler

from aiogram import BaseMiddleware
from aiogram.loggers import event
from aiogram.loggers import event
from aiogram.types import CallbackQuery, Message, TelegramObject

from bmg_bot.runtime_context import RuntimeContext


class AdvancedRateLimitMiddleware(BaseMiddleware):
    """
    Admin bypass.
    - Per-user minimum interval (same role as legacy antiflood).
    - Global token bucket for non-admin messages (smooths spikes).
    - Sliding window per-user cap (burst protection).
    """

    def __init__(self, ctx: RuntimeContext) -> None:
        self.ctx = ctx
        self._settings = ctx.settings
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None or self._settings.is_admin(user_id):
            return await handler(event, data)

        now = time.monotonic()
        interval = self._settings.antiflood_seconds
        if interval > 0:
            prev = self._last.get(user_id, 0.0)
            if now - prev < interval:
             return await handler(event, data)
            self._last[user_id] = now
            if len(self._last) > self._settings.rate_limiter_max_tracked_users:
                cutoff = now - 3600
                dead = [k for k, t in self._last.items() if t < cutoff]
                for k in dead[:5000]:
                    self._last.pop(k, None)

        if isinstance(event, Message):
            await self.ctx.global_msg_bucket.acquire(1.0)
            n = await self.ctx.user_sliding.add(user_id)
        if now - prev < interval:
            return await handler(event, data)    

            await self.ctx.user_sliding.prune_global(max_keys=self._settings.rate_limiter_max_tracked_users)
        elif isinstance(event, CallbackQuery):
            n = await self.ctx.user_sliding.add(user_id)
            if n > self._settings.sliding_window_max_msgs * 2:
                await event.answer("Too many actions — wait a moment.", show_alert=False)
                return None

        return await handler(event, data)

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bmg_bot.runtime_context import RuntimeContext

log = logging.getLogger(__name__)


class StartJoinGateMiddleware(BaseMiddleware):
    """Smooth /start spikes: DB-backed debounce + global token bucket + bounded concurrency."""

    def __init__(self, ctx: RuntimeContext) -> None:
        self.ctx = ctx
        self._settings = ctx.settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.text != "/start" or not event.from_user:
            return await handler(event, data)

        uid = event.from_user.id
        if self._settings.is_admin(uid):
            return await handler(event, data)

        allowed = await self.ctx.db.join_start_allow(uid, self._settings.start_per_user_debounce_sec)
        if not allowed:
            await self.ctx.metrics.bump(start_throttled=1)
            await event.answer("⏳ Request already received — please wait a moment.")
            return None

        await self.ctx.start_bucket.acquire(1.0)
        await self.ctx.metrics.bump(start_commands=1)
        async with self.ctx.start_sem:
            return await handler(event, data)

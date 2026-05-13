from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bmg_bot.runtime_context import RuntimeContext


class EventCountMiddleware(BaseMiddleware):
    """Count handled message/callback events (approximation of inbound load)."""

    def __init__(self, ctx: RuntimeContext) -> None:
        self.ctx = ctx

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)):
            await self.ctx.metrics.bump(updates_total=1)
        return await handler(event, data)

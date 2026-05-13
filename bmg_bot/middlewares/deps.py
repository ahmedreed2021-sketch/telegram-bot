from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bmg_bot.runtime_context import RuntimeContext


class RepoMiddleware(BaseMiddleware):
    def __init__(self, ctx: RuntimeContext) -> None:
        self.ctx = ctx

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["ctx"] = self.ctx
        data["repo"] = self.ctx.repo
        data["settings"] = self.ctx.settings
        data["archive"] = self.ctx.archive
        data["db"] = self.ctx.db
        data["metrics"] = self.ctx.metrics
        data["outbound"] = self.ctx.outbound
        return await handler(event, data)

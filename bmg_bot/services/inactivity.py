from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot

    from bmg_bot.repository import LobbyRepository

log = logging.getLogger(__name__)

MIN_WEEKLY_POSTS = 25
CHECK_INTERVAL = 3600


async def inactivity_watch_loop(bot: Bot, repo: LobbyRepository) -> None:
    """Enforce lobby rule: fewer than 25 posts in any rolling 7-day window after the first week."""
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)
            now = time.time()
            for user_id in await repo.list_member_ids():
                joined = await repo.fetch_joined_at(user_id)
                if joined is None:
                    continue
                if now - joined < 7 * 86400:
                    continue
                count = repo.activity_window_count(user_id)
                if count >= MIN_WEEKLY_POSTS:
                    continue
                await repo.remove_user(user_id)
                try:
                    await bot.send_message(
                        user_id,
                        "❌ You were removed for not meeting the minimum activity "
                        f"({MIN_WEEKLY_POSTS} posts per 7 days) in the lobby.",
                    )
                except Exception:
                    log.debug("Could not notify kicked user %s", user_id, exc_info=True)
                log.info("Removed inactive user %s (7d activity=%s)", user_id, count)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Inactivity watch error")
